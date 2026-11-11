"""Tests for the Claude Code hook scripts in .claude/hooks/.

Hooks are the environment's guaranteed safety layer, so their decisions are
tested like any other code: the pure functions directly, and each script once
end to end through stdin/stdout exactly as Claude Code calls it.
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
    """Invoke a hook script as Claude Code would; return (exit code, parsed stdout)."""
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
    "git push -u origin claude/my-branch",
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
