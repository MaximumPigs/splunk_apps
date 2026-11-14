"""Tests for the coding agent's hook scripts in .claude/hooks/.

Hooks are the environment's guaranteed safety layer, so their decisions are
tested like any other code: the pure functions directly, and each script once
end to end through stdin/stdout exactly as the agent runtime calls it.
"""

import json
import os
import subprocess
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOKS_DIR = os.path.join(REPO_ROOT, ".claude", "hooks")
sys.path.insert(0, HOOKS_DIR)

import check_edit  # noqa: E402
import guard_bash  # noqa: E402
import guard_files  # noqa: E402
import stop_retro  # noqa: E402


def run_hook(name, event, project_dir):
    """Invoke a hook script as the agent runtime would; return (exit code, parsed stdout)."""
    env = dict(os.environ, CLAUDE_PROJECT_DIR=project_dir)
    proc = subprocess.run(
        [sys.executable, os.path.join(HOOKS_DIR, name)],
        input=json.dumps(event), capture_output=True, text=True, env=env, timeout=30,
    )
    return proc.returncode, (json.loads(proc.stdout) if proc.stdout.strip() else None)


# ----------------------------------------------------------------- guard_bash

@pytest.mark.parametrize("command", [
    "curl -k -H 'Authorization: Bearer x' https://localhost:8089/services/apps/local",
    "Invoke-RestMethod -Uri https://localhost:8089/services/server/info",
    "/opt/splunk/bin/splunk restart",
    "splunk.exe stop",
    "cp -r apps/fillcontinuous /opt/splunk/etc/apps/",
    "cat .env",
    "Get-Content .env",
    "git push --force origin feature",
    "git push origin main",
    "rm -rf apps",
])
def test_bash_denies_bypasses(command):
    decision, reason = guard_bash.decide(command)
    assert decision == "deny", command
    assert reason


@pytest.mark.parametrize("command", [
    "splk dev fillcontinuous",
    "splk search \"| makeresults\"",
    "pytest -q",
    "cat .env.example",
    "git push -u origin feature/my-branch",
    "rm -rf build/reports",
])
def test_bash_allows_paved_road(command):
    assert guard_bash.decide(command) == (None, None), command


def test_bash_asks_before_restart():
    assert guard_bash.decide("splk deploy fillcontinuous --restart")[0] == "ask"


def test_bash_hook_end_to_end(tmp_path):
    code, out = run_hook("guard_bash.py", {"tool_input": {"command": "splunk restart"}}, str(tmp_path))
    assert code == 0
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    code, out = run_hook("guard_bash.py", {"tool_input": {"command": "ls"}}, str(tmp_path))
    assert (code, out) == (0, None)


# ---------------------------------------------------------------- guard_files

@pytest.mark.parametrize("path", [
    "apps/fillcontinuous/local/app.conf",
    "apps/fillcontinuous/metadata/local.meta",
    "apps/fillcontinuous/lib/splunklib/client.py",
    ".env",
    "dist/fillcontinuous-1.0.0.spl",
])
def test_files_denied(path):
    assert guard_files.blocked_reason(path)


@pytest.mark.parametrize("path", [
    "apps/fillcontinuous/default/app.conf",
    "apps/fillcontinuous/bin/fillcontinuous_core.py",
    ".env.example",
    "tools/splk/cli.py",
])
def test_files_allowed(path):
    assert guard_files.blocked_reason(path) is None


# ---------------------------------------------------------------- check_edit

def test_conf_lint_finds_problems(tmp_path):
    conf = tmp_path / "bad.conf"
    conf.write_bytes(b"[good]\na = 1\na = 2\n[broken\nnot a key value\n")
    problems = check_edit.lint_conf(str(conf))
    assert any("duplicate key 'a'" in p for p in problems)
    assert any("malformed stanza" in p for p in problems)
    assert any("expected `key = value`" in p for p in problems)


def test_conf_lint_flags_crlf_and_accepts_continuations(tmp_path):
    conf = tmp_path / "x.conf"
    conf.write_bytes(b"[s]\r\nsearch = index=a \\\r\n| stats count\r\n")
    problems = check_edit.lint_conf(str(conf))
    assert problems == ["CRLF line endings; Splunk apps ship LF only (see .gitattributes)"]


def test_repo_conf_files_are_clean():
    """Every committed .conf/.meta passes the same lint the hook applies."""
    found = []
    for root, _dirs, files in os.walk(os.path.join(REPO_ROOT, "apps")):
        for name in files:
            if name.endswith((".conf", ".meta")):
                path = os.path.join(root, name)
                found.extend("%s: %s" % (path, p) for p in check_edit.lint_conf(path))
    assert found == []


def test_check_edit_blocks_syntax_error(tmp_path):
    bad = tmp_path / "tools" / "x.py"
    bad.parent.mkdir()
    bad.write_text("def f(:\n")
    code, out = run_hook("check_edit.py", {"tool_input": {"file_path": str(bad)}}, str(tmp_path))
    assert code == 0
    assert out["decision"] == "block"
    assert "does not compile" in out["reason"]


def test_check_edit_nudges_missing_logging(tmp_path):
    script = tmp_path / "tools" / "y.py"
    script.parent.mkdir()
    script.write_text("print('hi')\n")
    _code, out = run_hook("check_edit.py", {"tool_input": {"file_path": str(script)}}, str(tmp_path))
    assert "no logging" in out["hookSpecificOutput"]["additionalContext"]


# ------------------------------------------------------------- stop_retro

def _runs(project, lines):
    runs = os.path.join(project, ".agent", "runs")
    os.makedirs(runs)
    with open(os.path.join(runs, "2026-01-01.jsonl"), "w") as handle:
        for line in lines:
            handle.write(json.dumps(line) + "\n")


def test_stop_hook_asks_for_retro_once(tmp_path):
    """A fix in this session blocks the stop once; the second stop is allowed.
    """
    project = str(tmp_path)
    sessions = os.path.join(project, ".agent", "sessions")
    os.makedirs(sessions)
    with open(os.path.join(sessions, "s1.json"), "w") as handle:
        json.dump({"started": 100}, handle)
    _runs(project, [
        {"epoch": 200, "app": "a", "stage": "live", "ok": False, "summary": "1 failed"},
        {"epoch": 300, "app": "a", "stage": "live", "ok": True, "summary": "1 passed"},
    ])

    code, out = run_hook("stop_retro.py", {"session_id": "s1"}, project)
    assert code == 0 and out["decision"] == "block"
    assert "retro" in out["reason"]

    code, out = run_hook("stop_retro.py", {"session_id": "s1"}, project)
    assert (code, out) == (0, None)


def test_stop_hook_respects_stop_hook_active(tmp_path):
    code, out = run_hook("stop_retro.py", {"session_id": "s1", "stop_hook_active": True}, str(tmp_path))
    assert (code, out) == (0, None)


def _session(project, started=100):
    sessions = os.path.join(project, ".agent", "sessions")
    os.makedirs(sessions)
    with open(os.path.join(sessions, "s1.json"), "w") as handle:
        json.dump({"started": started}, handle)


def test_stop_hook_asks_for_debrief_after_deploys_without_failures(tmp_path):
    """No stage went red, but an app was deployed: the session still gets a debrief."""
    project = str(tmp_path)
    _session(project)
    _runs(project, [{"epoch": 200 + i, "app": "easyadmin", "stage": "deploy", "ok": True, "summary": "ok"}
                    for i in range(3)])
    code, out = run_hook("stop_retro.py", {"session_id": "s1"}, project)
    assert code == 0 and out["decision"] == "block"
    assert "debrief" in out["reason"] and "easyadmin (3 deploys)" in out["reason"]
    # Asked once; the second stop goes through.
    assert run_hook("stop_retro.py", {"session_id": "s1"}, project) == (0, None)


def test_followups_debrief_skipped_once_something_was_learned():
    entries = [{"epoch": 200, "app": "a", "stage": "deploy", "ok": True}]
    assert stop_retro.followups([], entries, learned_at=300, started=100, unreviewed=[]) == []
    due = stop_retro.followups([], entries, learned_at=50, started=100, unreviewed=[])
    assert [key for key, _ in due] == ["debrief:a"]
    # Fewer than three deploys: no "took several iterations" nudge.
    assert "iterations" not in due[0][1]


def test_followups_fix_replaces_debrief_and_security_is_separate():
    fixed = [(("a", "live"), {"summary": "1 failed"}, {"epoch": 300})]
    entries = [{"epoch": 250, "app": "a", "stage": "deploy", "ok": True}]
    due = stop_retro.followups(fixed, entries, learned_at=0, started=100, unreviewed=["apps/a/bin/a.py"])
    assert [key for key, _ in due] == ["fix:a/live", "security:apps/a/bin/a.py"]
    assert "splunk-security-review" in due[1][1]


@pytest.mark.parametrize("path, expected", [
    ("apps/easyadmin/bin/easyadmin_rest.py", True),
    ("apps/easyadmin/appserver/static/easyadmin_roles.js", True),
    ("apps/easyadmin/metadata/default.meta", True),
    ("apps/fillcontinuous/lib/splunklib/client.py", False),
    ("apps/easyadmin/README.md", False),
    ("tools/splk/ui.py", True),
    (".claude/hooks/guard_bash.py", True),
    ("tests/test_x.py", False),
])
def test_security_review_covers_code_not_docs_or_vendored(path, expected):
    assert stop_retro.is_code(path) is expected


def test_unreviewed_code_is_code_edited_this_session_after_the_last_review():
    changed = ["apps/a/bin/a.py", "apps/a/bin/b.py", "apps/a/README.md"]
    mtimes = {"apps/a/bin/a.py": 500, "apps/a/bin/b.py": 50, "apps/a/README.md": 500}
    # b.py predates the session; README is not code.
    assert stop_retro.unreviewed_code(changed, mtimes, started=100, reviewed_at=0) == ["apps/a/bin/a.py"]
    assert stop_retro.unreviewed_code(changed, mtimes, started=100, reviewed_at=600) == []


def test_last_review_reads_security_entries():
    entries = [{"epoch": 10, "stage": "security", "ok": False}, {"epoch": 20, "stage": "deploy"},
               {"epoch": 15, "stage": "security", "ok": True}]
    assert stop_retro.last_review(entries) == 15
    assert stop_retro.last_review([]) == 0


@pytest.mark.parametrize("path, expected", [
    ("apps/easyadmin/appserver/static/easyadmin_roles.css", True),
    ("apps/easyadmin/default/data/ui/views/role_management.xml", True),
    ("apps/easyadmin/default/data/ui/nav/default.xml", True),
    ("apps\\easyadmin\\appserver\\static\\easyadmin_roles.js", True),
    ("apps/easyadmin/bin/easyadmin_rest.py", False),
    ("apps/easyadmin/default/restmap.conf", False),
    ("tests/ui/easyadmin/ux.toml", False),
])
def test_ux_review_covers_what_users_see(path, expected):
    assert stop_retro.is_ui(path) is expected


def test_ux_review_is_due_for_ui_changed_after_the_last_ux_review():
    changed = ["apps/a/appserver/static/a.js", "apps/a/bin/a.py"]
    mtimes = {"apps/a/appserver/static/a.js": 500, "apps/a/bin/a.py": 500}
    assert stop_retro.unreviewed_ui(changed, mtimes, started=100, reviewed_at=0) == ["apps/a/appserver/static/a.js"]
    assert stop_retro.unreviewed_ui(changed, mtimes, started=100, reviewed_at=600) == []
    # The automated audit (stage "ux") is not a review; only "ux-review" counts.
    entries = [{"epoch": 700, "stage": "ux", "ok": True}, {"epoch": 300, "stage": "ux-review", "ok": True}]
    assert stop_retro.last_review(entries, stop_retro.UX_REVIEW_STAGE) == 300
    due = stop_retro.followups([], [], learned_at=0, started=100, unreviewed=[],
                               ui_unreviewed=["apps/a/appserver/static/a.js"])
    assert [key for key, _ in due] == ["ux:apps/a/appserver/static/a.js"]
    assert "splunk-ux-review" in due[0][1]


# ------------------------------------------------- encoding and 3.9 checks

def test_text_lint_rejects_bom_and_mojibake():
    assert any("byte-order mark" in p for p in check_edit.lint_text(b"\xef\xbb\xbfx = 1\n", "tools/a.py"))
    # An em dash after a cp1252 round trip, as PowerShell's Get-Content leaves it.
    corrupted = "a \u2014 b".encode("utf-8").decode("cp1252").encode("utf-8")
    assert any("mojibake" in p for p in check_edit.lint_text(corrupted, "README.md"))


def test_listing_files_must_be_ascii():
    dashed = "Fills gaps \u2014 fast".encode("utf-8")
    assert check_edit.lint_text(dashed, "splunkbase/fillcontinuous/listing.md") == [
        "line 1: non-ASCII U+2014; listing files are ASCII only"]
    # Ordinary docs, including the splunkbase/ README, may use UTF-8.
    assert check_edit.lint_text(dashed, "splunkbase/README.md") == []
    assert check_edit.lint_text(dashed, "README.md") == []


def test_python_39_grammar_enforced_for_app_code(tmp_path):
    script = tmp_path / "apps" / "x" / "bin" / "x_core.py"
    script.parent.mkdir(parents=True)
    script.write_text("import logging\nmatch 1:\n    case 1:\n        pass\n")
    _code, out = run_hook("check_edit.py", {"tool_input": {"file_path": str(script)}}, str(tmp_path))
    assert out["decision"] == "block"
    # On a 3.10+ interpreter the 3.9 grammar check catches it; on 3.9 itself
    # plain compilation already fails. Either way the edit is blocked.
    assert "Python 3.9" in out["reason"] or "does not compile" in out["reason"]


def test_bash_denies_powershell_file_writes():
    assert guard_bash.decide("Set-Content -Path README.md -Value $x")[0] == "deny"
    assert guard_bash.decide("$text | Out-File apps/x/default/app.conf -Encoding utf8")[0] == "deny"


def _config(values):
    """Fake git config lookup, so tests never depend on this machine's identity."""
    return lambda key, cwd: values.get(key, "")


AI_CONFIG = _config({"user.name": "Claude", "user.email": "noreply@anthropic.com"})
OWNER_CONFIG = _config({"user.name": "MaximumPigs", "user.email": "1+maximumpigs@users.noreply.github.com"})


@pytest.mark.parametrize("command", [
    "git commit -m 'Fix chunking'",
    "git -C /d/splunk_apps commit -F /tmp/msg.txt",
    "git commit --amend --no-edit",
])
def test_bash_denies_commit_authored_by_ai_identity(command):
    decision, reason = guard_bash.decide(command, environ={}, config=AI_CONFIG)
    assert decision == "deny", command
    assert "Co-authored-by" in reason


@pytest.mark.parametrize("command", [
    "git commit --author='Claude <noreply@anthropic.com>' -m x",
    "GIT_AUTHOR_EMAIL=noreply@anthropic.com git commit -m x",
    "git -c user.name=Claude commit -m x",
    "git commit -m 'Fix' -m 'Co-Authored-By: Someone <a@b.c>'",
])
def test_bash_denies_ai_author_overrides_and_trailers(command):
    assert guard_bash.decide(command, environ={}, config=OWNER_CONFIG)[0] == "deny", command


@pytest.mark.parametrize("command", [
    "git commit -m 'Fix chunking'",
    "git -C /d/splunk_apps commit -F /tmp/msg.txt",
    "git commit --author='MaximumPigs <1+maximumpigs@users.noreply.github.com>' -m x",
    "git log --author=claude",
    "git status",
])
def test_bash_allows_commit_by_owner_identity(command):
    assert guard_bash.decide(command, environ={}, config=OWNER_CONFIG) == (None, None), command


def test_bash_commit_author_env_beats_config():
    environ = {"GIT_AUTHOR_NAME": "Claude", "GIT_AUTHOR_EMAIL": "noreply@anthropic.com"}
    assert guard_bash.decide("git commit -m x", environ=environ, config=OWNER_CONFIG)[0] == "deny"


def test_bash_commit_author_end_to_end(tmp_path):
    """Real git config in a real repo, through the hook as the runtime calls it."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "Claude"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "noreply@anthropic.com"], check=True)
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_AUTHOR_")}
    event = {"cwd": str(repo), "tool_input": {"command": "git commit -m x"}}
    proc = subprocess.run([sys.executable, os.path.join(HOOKS_DIR, "guard_bash.py")],
                          input=json.dumps(event), capture_output=True, text=True,
                          env=dict(env, CLAUDE_PROJECT_DIR=str(tmp_path)), timeout=30)
    assert json.loads(proc.stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "MaximumPigs"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "1+maximumpigs@users.noreply.github.com"],
                   check=True)
    proc = subprocess.run([sys.executable, os.path.join(HOOKS_DIR, "guard_bash.py")],
                          input=json.dumps(event), capture_output=True, text=True,
                          env=dict(env, CLAUDE_PROJECT_DIR=str(tmp_path)), timeout=30)
    assert proc.stdout.strip() == ""


def test_repo_text_files_are_clean():
    """Every tracked text file passes the same encoding lint the hook applies."""
    tracked = subprocess.run(["git", "ls-files"], cwd=REPO_ROOT, capture_output=True, text=True).stdout.split()
    found = []
    for relative in tracked:
        if relative.endswith(check_edit.TEXT_SUFFIXES) or check_edit.ASCII_ONLY.match(relative):
            with open(os.path.join(REPO_ROOT, relative), "rb") as handle:
                found.extend("%s: %s" % (relative, p) for p in check_edit.lint_text(handle.read(), relative))
    assert found == []
