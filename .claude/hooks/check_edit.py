#!/usr/bin/env python3
"""PostToolUse hook for Edit/Write: fast checks on the file just changed.

* .py   must compile, and code in apps/, tools/ or hooks should use logging
* .conf / .meta  basic lint: LF endings, valid stanza headers, key = value
               lines, no duplicate keys within a stanza

Problems are fed straight back to Claude (decision: block), so they get fixed
in the same turn instead of surfacing later in AppInspect or a failed search.
"""

import os
import re

from _common import emit, get_logger, read_event, rel, run_safely

log = get_logger("check_edit")

STANZA_RE = re.compile(r"^\[[^\[\]]*\]$")
KEY_RE = re.compile(r"^[^=\s][^=]*?\s*=")
# Paths where new Python must log (the repo standard), not just print.
LOGGING_REQUIRED = re.compile(r"^(apps/[^/]+/bin|tools|\.claude/hooks)/")


def lint_conf(path):
    """Return a list of human-readable problems in a .conf/.meta file."""
    with open(path, "rb") as handle:
        raw = handle.read()
    problems = []
    if b"\r\n" in raw:
        problems.append("CRLF line endings; Splunk apps ship LF only (see .gitattributes)")
    text = raw.decode("utf-8", "replace").replace("\r\n", "\n")
    stanza, seen = "default", {}
    continued = False
    for number, line in enumerate(text.split("\n"), 1):
        stripped = line.strip()
        if continued:
            # Previous line ended with a backslash: this is part of its value.
            continued = stripped.endswith("\\")
            continue
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("["):
            if not STANZA_RE.match(stripped):
                problems.append("line %d: malformed stanza header %r" % (number, stripped[:80]))
            stanza = stripped
            seen = {}
            continue
        if not KEY_RE.match(stripped):
            problems.append("line %d: expected `key = value`, got %r" % (number, stripped[:80]))
            continue
        key = stripped.split("=", 1)[0].strip()
        if key in seen:
            problems.append("line %d: duplicate key %r in %s (first at line %d); Splunk keeps "
                            "only the last" % (number, key, stanza, seen[key]))
        seen.setdefault(key, number)
        continued = stripped.endswith("\\")
    return problems


def check_python(path, relative):
    """Compile errors block; a missing logging import is a nudge, not a block."""
    problems, notes = [], []
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        source = handle.read()
    try:
        # compile() checks syntax without writing a .pyc anywhere.
        compile(source, path, "exec")
    except SyntaxError as exc:
        problems.append("does not compile: line %s: %s" % (exc.lineno, exc.msg))
    if LOGGING_REQUIRED.match(relative):
        # splunklib search commands log via self.logger, which is fine too.
        if "logging" not in source and "self.logger" not in source and "get_logger" not in source:
            notes.append("%s has no logging; repo standard is logging, not print" % relative)
    return problems, notes


def main():
    event = read_event()
    tool_input = event.get("tool_input") or {}
    path = tool_input.get("file_path") or ""
    if not path or not os.path.isfile(path):
        return
    relative = rel(path)
    problems, notes = [], []
    if path.endswith(".py"):
        problems, notes = check_python(path, relative)
    elif path.endswith((".conf", ".meta")):
        problems = lint_conf(path)
    else:
        return

    for note in notes:
        log.info("note %s", note)
    if problems:
        log.info("block %s: %s", relative, problems)
        emit({
            "decision": "block",
            "reason": "%s:\n- %s" % (relative, "\n- ".join(problems)),
        })
    elif notes:
        emit({"hookSpecificOutput": {"hookEventName": "PostToolUse",
                                     "additionalContext": "\n".join(notes)}})


if __name__ == "__main__":
    run_safely(main, log)
