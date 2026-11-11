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


def test_repo_text_files_are_clean():
    """Every tracked text file passes the same encoding lint the hook applies."""
    tracked = subprocess.run(["git", "ls-files"], cwd=REPO_ROOT, capture_output=True, text=True).stdout.split()
    found = []
    for relative in tracked:
        if relative.endswith(check_edit.TEXT_SUFFIXES) or check_edit.ASCII_ONLY.match(relative):
            with open(os.path.join(REPO_ROOT, relative), "rb") as handle:
                found.extend("%s: %s" % (relative, p) for p in check_edit.lint_text(handle.read(), relative))
    assert found == []
