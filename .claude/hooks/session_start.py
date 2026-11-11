#!/usr/bin/env python3
"""SessionStart hook: give Claude the live state of the environment up front.

Injects, in a few lines:
* whether the Splunk target answers, and its version (3s timeout, never blocks)
* stage failures from the last 24h that have not passed since
* the head of the learner's lesson index, so known pitfalls are in view

Also records the session's start time, which the Stop hook uses to scope
"failures fixed during this session".
"""

import json
import os
import time

from _common import AGENT_DIR, REPO_ROOT, SESSIONS_DIR, add_context, get_logger, read_event, run_safely

log = get_logger("session_start")

LESSON_INDEX = os.path.join(REPO_ROOT, ".claude", "agent-memory", "learner", "MEMORY.md")
LESSON_LINES = 25


def target_status():
    """One line on the default target. Any failure is reported, not raised."""
    try:
        from splk import config
        from splk.rest import SplunkClient
        config.load_env_file()
        target = config.resolve_target()
        info = SplunkClient(target, timeout=3).server_info()
        return "Splunk target %s: up, version %s" % (target.name, info.get("version"))
    except Exception as exc:  # noqa: BLE001 - status line only
        return "Splunk target: NOT ready (%s). Run `splk doctor`." % str(exc)[:200]


def open_failures():
    """Stage failures in the last 24h with no later pass for the same app+stage."""
    try:
        from splk import runlog
        entries = runlog.read_since(time.time() - 86400, runs_dir=os.path.join(AGENT_DIR, "runs"))
    except Exception:  # noqa: BLE001
        return []
    latest = {}
    for entry in entries:
        latest[(entry.get("app"), entry.get("stage"))] = entry
    return ["%s %s: %s" % (e["app"], e["stage"], e.get("summary", "")[:160])
            for e in latest.values() if not e.get("ok")]


def lesson_head():
    if not os.path.isfile(LESSON_INDEX):
        return ""
    with open(LESSON_INDEX, "r", encoding="utf-8") as handle:
        return "".join(handle.readlines()[:LESSON_LINES]).strip()


def main():
    event = read_event()
    session_id = event.get("session_id") or "unknown"
    try:
        os.makedirs(SESSIONS_DIR, exist_ok=True)
        with open(os.path.join(SESSIONS_DIR, "%s.json" % session_id), "w", encoding="utf-8") as handle:
            json.dump({"started": time.time(), "source": event.get("source")}, handle)
    except OSError as exc:
        log.warning("could not record session start: %s", exc)

    parts = [target_status()]
    failures = open_failures()
    if failures:
        parts.append("Unresolved stage failures (last 24h):\n- " + "\n- ".join(failures))
    lessons = lesson_head()
    if lessons:
        parts.append("Lesson index (learner memory, top entries):\n" + lessons)
    log.info("session %s started; %d open failure(s)", session_id, len(failures))
    add_context("SessionStart", "\n\n".join(parts))


if __name__ == "__main__":
    run_safely(main, log)
