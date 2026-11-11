#!/usr/bin/env python3
"""PreToolUse hook for Bash: keep shell commands on the paved road.

Everything that touches Splunk goes through `splk`, so results land in the run
log and behave the same for humans, Claude and CI. This hook denies the
shortcuts that bypass it, and asks before anything disruptive.
"""

import re

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


def decide(command):
    """Return (decision, reason) for a command, or (None, None) to defer."""
    for pattern, decision, reason in COMPILED:
        if pattern.search(command):
            return decision, reason
    return None, None


def main():
    event = read_event()
    command = (event.get("tool_input") or {}).get("command", "")
    decision, reason = decide(command)
    if decision is None:
        return  # Exit 0 with no output: the normal permission flow applies.
    log.info("%s: %s | %s", decision, reason, command[:300])
    pre_tool_decision(decision, reason)


if __name__ == "__main__":
    run_safely(main, log)
