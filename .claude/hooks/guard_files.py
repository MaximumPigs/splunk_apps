#!/usr/bin/env python3
"""PreToolUse hook for Edit/Write: protect files that must not be hand-edited.

Each entry explains *why*, because the reason is what Claude reads back and
what stops it trying the same thing a different way.
"""

import os
import re

from _common import get_logger, pre_tool_decision, read_event, rel, run_safely

log = get_logger("guard_files")

PROTECTED = [
    (r"^apps/[^/]+/local(/|$)|(^|/)local\.meta$",
     "local/ and local.meta are runtime state written by Splunk; AppInspect fails a package "
     "containing them. Put defaults in default/ instead."),
    (r"^apps/[^/]+/lib/splunklib/",
     "splunklib is vendored. Change it only with scripts/vendor_splunklib.py."),
    (r"^\.env$",
     ".env holds secrets and is never edited by Claude. Ask the person to update it."),
    (r"^(dist|build)/",
     "Generated output. Change the source and rebuild with splk."),
    # .agent/loop/handoff/ is the one exception: `splk loop` steps hand their
    # plan and PR text to the supervisor there. Loop state, the supervisor's
    # inputs (inbox/), run logs and step records stay protected, because they
    # are the evidence of what happened and the owner's words.
    (r"^\.agent/(?!loop/handoff/[^/]+$)",
     "Generated output. Change the source and rebuild with splk."),
    (r"^packages/",
     "Packages are built by `splk loop` from apps/; change the app instead."),
]

# Unattended `splk loop` steps (SPLK_LOOP=1) also may not change what guards
# and drives them: a hook edit would disable the guard for the rest of the
# step. Promotions into hooks go through an interactive session.
LOOP_PROTECTED = [
    # Also what decides "green" (cli, stages, testing: `splk dev`'s exit code
    # is the loop's verdict) and the prompts later steps run under.
    # All of tools/splk/ (the supervisor runs it from this tree) and the
    # packager (it decides what goes into the committed .spl). Tooling items
    # that need these are done in an interactive session.
    (r"^\.claude/(hooks/|loop/|settings[^/]*\.json$)|^config/loop\.toml$|"
     r"^tools/splk/|^scripts/package_app\.py$",
     "Unattended loop steps may not change the hooks, settings, prompts, the loop or what "
     "decides green; finish blocked and say what needs changing."),
]

# NTFS is case-insensitive: .AGENT/ is the same folder as .agent/.
COMPILED = [(re.compile(p, re.IGNORECASE), reason) for p, reason in PROTECTED]
LOOP_COMPILED = [(re.compile(p, re.IGNORECASE), reason) for p, reason in LOOP_PROTECTED]


def blocked_reason(path, environ=None):
    """Return the reason a repo-relative path is protected, or None."""
    env = os.environ if environ is None else environ
    rules = COMPILED + (LOOP_COMPILED if env.get("SPLK_LOOP") == "1" else [])
    for pattern, reason in rules:
        if pattern.search(path):
            return reason
    return None


def main():
    event = read_event()
    tool_input = event.get("tool_input") or {}
    path = tool_input.get("file_path") or tool_input.get("path") or ""
    if not path:
        return
    relative = rel(path)
    reason = blocked_reason(relative)
    if reason:
        log.info("deny %s: %s", relative, reason)
        pre_tool_decision("deny", reason)


if __name__ == "__main__":
    run_safely(main, log)
