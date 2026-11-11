#!/usr/bin/env python3
"""PreToolUse hook for Bash: keep shell commands on the paved road.

Everything that touches Splunk goes through `splk`, so results land in the run
log and behave the same for humans, Claude and CI. This hook denies the
shortcuts that bypass it, and asks before anything disruptive.
"""

import os
import re
import shlex
import subprocess

from _common import get_logger, pre_tool_decision, read_event, run_safely

log = get_logger("guard_bash")

# (pattern, decision, reason). First match wins. Patterns are case-insensitive
# and written to catch both POSIX and PowerShell spellings.
RULES = [
    # Direct REST calls to splunkd bypass splk's logging, token handling and run log.
    (r"\b(curl|wget|invoke-webrequest|invoke-restmethod|iwr|irm)\b.*:8089",
     "deny", "Talk to Splunk through splk (splk search / deploy / doctor), not raw REST on 8089."),
    # Restarting or stopping splunkd outside splk.
    (r"\bsplunk(\.exe)?\s+(restart|stop)\b|server/control/restart",
     "deny", "Restarts go through `splk deploy --restart`, which asks first and waits for splunkd."),
    # Copying straight into $SPLUNK_HOME/etc/apps skips packaging and AppInspect.
    (r"\b(cp|copy|xcopy|robocopy|copy-item|mv|move|rsync)\b.*etc[/\\]+apps",
     "deny", "Deploy with `splk deploy <app>` so the package is built and versioned."),
    # Reading the token file would put a secret into the transcript.
    (r"\b(cat|type|get-content|gc|more|less|head|tail)\b[^|;&]*\.env\b(?!\.example)",
     "deny", ".env holds the Splunk token; do not print it. splk loads it itself."),
    # History rewrites and direct pushes to main.
    (r"\bgit\s+push\b.*(--force\b|-f\b|--force-with-lease\b)",
     "deny", "No force pushes. Push a new commit instead."),
    (r"\bgit\s+push\b.*\b(origin\s+)?(main|master)\b",
     "deny", "Never push to main; push the branch and open a PR."),
    # PowerShell file writes corrupt UTF-8 (ANSI codepage) or add a BOM (5.1).
    (r"\b(set-content|out-file|add-content)\b",
     "deny", "Do not write repository files with PowerShell: it corrupts UTF-8 or adds a BOM. "
             "Use the file tools, or Python with encoding='utf-8'."),
    # Bulk deletes of things that matter.
    (r"\brm\s+-[a-z]*r[a-z]*f?\s+(/|~|\.|apps\b|\.git\b|tests\b|tools\b)(\s|$|/)",
     "deny", "Recursive delete of a top-level path. Delete specific files instead."),
    (r"\bremove-item\b.*-recurse.*\b(apps|\.git|tests|tools)\b",
     "deny", "Recursive delete of a top-level path. Delete specific files instead."),
    # A restart through splk is allowed, but the person decides.
    (r"\bsplk\b.*\s--restart\b",
     "ask", "This may restart splunkd on the target. Confirm before it runs."),
]

COMPILED = [(re.compile(p, re.IGNORECASE), d, r) for p, d, r in RULES]


# --------------------------------------------------------------- commit author
# The owner's rule: no AI tool names and no Co-Authored-By trailers. A commit
# authored as an AI identity breaks it even with a clean message, because
# GitHub's squash merge appends "Co-authored-by: <author>" for every commit
# author other than the merger (PR #9 shipped to main that way).
AI_EMAIL = re.compile(r"@(anthropic|openai)\.com\b|copilot|\bclaude\b", re.IGNORECASE)
AI_NAME = re.compile(r"\b(claude|copilot|chatgpt|codex|gemini|devin|cursor)\b", re.IGNORECASE)
GIT_COMMIT = re.compile(r"\bgit\b(?:\s+(?:-C\s+\S+|-c\s+\S+|--\S+))*\s+commit\b", re.IGNORECASE)
TRAILER = re.compile(r"co-authored-by\s*:", re.IGNORECASE)
AUTHOR_REASON = (
    "Commit author is an AI identity ({0}). GitHub's squash merge turns it into a "
    "Co-authored-by trailer on main. Set the owner's identity first, for example "
    "`git config user.name \"<name>\"` and `git config user.email <id>+<login>@users.noreply.github.com`."
)


def _tokens(command):
    """Split a shell command; fall back to whitespace if quoting is unbalanced."""
    try:
        return shlex.split(command, posix=True)
    except ValueError:
        return command.split()


def _git_config(key, cwd):
    """Read one git config value as git would resolve it in cwd; "" if unset or git fails."""
    try:
        proc = subprocess.run(["git", "config", "--get", key], cwd=cwd or None,
                              capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError) as exc:
        log.debug("git config %s failed: %s", key, exc)
        return ""
    return proc.stdout.strip()


def commit_author(command, cwd=None, environ=None, config=None):
    """Return (name, email) a `git commit` in this command would be authored as.

    Precedence follows git: --author, then GIT_AUTHOR_* in the command or the
    environment, then `-c user.*`, then git config. `config` is injectable so
    tests do not depend on the machine's git setup.
    """
    environ = os.environ if environ is None else environ
    config = config or _git_config
    tokens = _tokens(command)
    name = email = None
    repo_dir = cwd
    inline = {}
    for i, tok in enumerate(tokens):
        nxt = tokens[i + 1] if i + 1 < len(tokens) else ""
        if tok.startswith("--author="):
            # "Name <email>": either part may identify the tool.
            match = re.match(r"\s*(.*?)\s*<([^>]*)>", tok[len("--author="):])
            if match:
                return match.group(1), match.group(2)
            return tok[len("--author="):], ""
        if tok == "--author" and nxt:
            match = re.match(r"\s*(.*?)\s*<([^>]*)>", nxt)
            return (match.group(1), match.group(2)) if match else (nxt, "")
        if re.match(r"GIT_AUTHOR_(NAME|EMAIL)=", tok):
            key, _, value = tok.partition("=")
            inline[key] = value
        if tok == "-c" and nxt.lower().startswith(("user.name=", "user.email=")):
            key, _, value = nxt.partition("=")
            inline[key.lower()] = value
        if tok == "-C" and nxt:
            repo_dir = nxt if cwd is None or os.path.isabs(nxt) else os.path.join(cwd, nxt)
    name = (inline.get("GIT_AUTHOR_NAME") or environ.get("GIT_AUTHOR_NAME")
            or inline.get("user.name") or config("user.name", repo_dir))
    email = (inline.get("GIT_AUTHOR_EMAIL") or environ.get("GIT_AUTHOR_EMAIL")
             or inline.get("user.email") or config("user.email", repo_dir))
    return name or "", email or ""


def check_commit(command, cwd=None, environ=None, config=None):
    """Deny a git commit that carries a trailer or would be authored by an AI identity."""
    if not GIT_COMMIT.search(command):
        return None, None
    if TRAILER.search(command):
        return "deny", "No Co-Authored-By trailers in commit messages (owner's rule)."
    name, email = commit_author(command, cwd, environ, config)
    if AI_NAME.search(name) or AI_EMAIL.search(email):
        return "deny", AUTHOR_REASON.format("%s <%s>" % (name, email))
    return None, None


def decide(command, cwd=None, environ=None, config=None):
    """Return (decision, reason) for a command, or (None, None) to defer."""
    for pattern, decision, reason in COMPILED:
        if pattern.search(command):
            return decision, reason
    return check_commit(command, cwd, environ, config)


def main():
    event = read_event()
    command = (event.get("tool_input") or {}).get("command", "")
    # The event's cwd is where the agent's shell runs, so git resolves config there.
    decision, reason = decide(command, cwd=event.get("cwd"))
    if decision is None:
        return  # Exit 0 with no output: the normal permission flow applies.
    log.info("%s: %s | %s", decision, reason, command[:300])
    pre_tool_decision(decision, reason)


if __name__ == "__main__":
    run_safely(main, log)
