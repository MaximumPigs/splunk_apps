#!/usr/bin/env python3
"""PostToolUse hook for Edit/Write: fast checks on the file just changed.

* any text file  no UTF-8 byte-order mark, no PowerShell-style mojibake
* splunkbase/<app>/**  ASCII only (the listing is pasted into a third-party form)
* .py   must compile; app, script, tool and hook code must also parse under
        Python 3.9 grammar, and should use logging
* .conf / .meta  basic lint: LF endings, valid stanza headers, key = value
               lines, no duplicate keys within a stanza

Problems are fed straight back to Claude (decision: block), so they get fixed
in the same turn instead of surfacing later in AppInspect or a failed search.
"""

import ast
import os
import re

from _common import emit, get_logger, read_event, rel, run_safely

log = get_logger("check_edit")

STANZA_RE = re.compile(r"^\[[^\[\]]*\]$")
KEY_RE = re.compile(r"^[^=\s][^=]*?\s*=")
# Paths where new Python must log (the repo standard), not just print.
LOGGING_REQUIRED = re.compile(r"^(apps/[^/]+/bin|tools|\.claude/hooks)/")
# Code that must run on Splunk's 3.9 runtime or the 3.9 CI leg.
PY39_REQUIRED = re.compile(r"^(apps/[^/]+/bin|scripts|tools|\.claude/hooks)/")
# Listing copy pasted into Splunkbase's form: ASCII only.
ASCII_ONLY = re.compile(r"^splunkbase/[^/]+/")
TEXT_SUFFIXES = (".py", ".conf", ".meta", ".md", ".json", ".manifest", ".xml",
                 ".yml", ".yaml", ".txt", ".spec", ".csv", ".toml", ".spl.txt")
# What UTF-8 punctuation looks like after a cp1252 round trip, e.g. an em dash
# read by PowerShell's Get-Content and written back. Built from escapes so this
# file itself stays ASCII.
MOJIBAKE = ("\u00e2\u20ac", "\u00c3\u00a9", "\u00c2\u00a0")


def lint_text(raw, relative):
    """Encoding problems that look fine in a terminal but corrupt the repo."""
    problems = []
    if raw.startswith(b"\xef\xbb\xbf"):
        problems.append("starts with a UTF-8 byte-order mark (PowerShell 5.1 -Encoding utf8 "
                        "adds one); write files with the file tools or Python instead")
    text = raw.decode("utf-8", "replace")
    if any(marker in text for marker in MOJIBAKE):
        problems.append("contains mojibake (e.g. an em dash turned into three characters): "
                        "the file was round-tripped through a non-UTF-8 codepage")
    if ASCII_ONLY.match(relative):
        for number, line in enumerate(text.split("\n"), 1):
            bad = sorted({ch for ch in line if ord(ch) > 127})
            if bad:
                problems.append("line %d: non-ASCII %s; listing files are ASCII only"
                                % (number, " ".join("U+%04X" % ord(ch) for ch in bad)))
                if len(problems) >= 10:
                    break
    return problems


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
    if not problems and PY39_REQUIRED.match(relative):
        try:
            # Grammar-level check only: catches match statements and other
            # 3.10+ syntax, not stdlib calls added later (CI's 3.9 leg does that).
            ast.parse(source, filename=path, feature_version=(3, 9))
        except SyntaxError as exc:
            problems.append("not valid Python 3.9 syntax at line %s: %s" % (exc.lineno, exc.msg))
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
    if path.endswith(TEXT_SUFFIXES) or ASCII_ONLY.match(relative):
        with open(path, "rb") as handle:
            problems.extend(lint_text(handle.read(), relative))
    if path.endswith(".py"):
        more, notes = check_python(path, relative)
        problems.extend(more)
    elif path.endswith((".conf", ".meta")):
        problems.extend(lint_conf(path))
    if not problems and not notes:
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
