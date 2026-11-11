#!/usr/bin/env python3
"""PreToolUse hook for Edit/Write: protect files that must not be hand-edited.

Each entry explains *why*, because the reason is what Claude reads back and
what stops it trying the same thing a different way.
"""

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
    (r"^(dist|build|\.agent)/",
     "Generated output. Change the source and rebuild with splk."),
]

COMPILED = [(re.compile(p), reason) for p, reason in PROTECTED]


def blocked_reason(path):
    """Return the reason a repo-relative path is protected, or None."""
    for pattern, reason in COMPILED:
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
