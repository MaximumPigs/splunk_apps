#!/usr/bin/env python3
"""Stop hook: don't let a fixed failure go unlearned.

If, during this session, a splk stage failed and later passed for the same app
and stage, and no lesson has been written since, block the stop once and ask
Claude to run the retro skill. That is the trigger for the learning loop.

Nags at most once per set of fixes (tracked in .agent/sessions/), and never
when Claude Code says a Stop hook is already driving the continuation.
"""

import json
import os

from _common import AGENT_DIR, REPO_ROOT, SESSIONS_DIR, emit, get_logger, read_event, run_safely

log = get_logger("stop_retro")

LESSONS_DIR = os.path.join(REPO_ROOT, ".claude", "agent-memory", "learner")


def newest_lesson_mtime():
    """Most recent modification time of anything in the learner's memory."""
    newest = 0.0
    for root, _dirs, files in os.walk(LESSONS_DIR):
        for name in files:
            newest = max(newest, os.path.getmtime(os.path.join(root, name)))
    return newest


def main():
    event = read_event()
    if event.get("stop_hook_active"):
        return  # Already continuing because of a Stop hook: avoid loops.
    session_id = event.get("session_id") or "unknown"
    state_path = os.path.join(SESSIONS_DIR, "%s.json" % session_id)
    if not os.path.isfile(state_path):
        return  # No SessionStart record: nothing to scope by.
    with open(state_path, "r", encoding="utf-8") as handle:
        state = json.load(handle)

    from splk import runlog
    fixed = runlog.fixed_failures(runlog.read_since(state.get("started", 0), runs_dir=os.path.join(AGENT_DIR, "runs")))
    if not fixed:
        return
    # Only fixes that happened after the newest lesson still need one.
    lesson_time = newest_lesson_mtime()
    pending = [(key, failed) for key, failed, passed in fixed if passed.get("epoch", 0) > lesson_time]
    keys = sorted("%s/%s" % key for key, _ in pending)
    if not keys or keys == state.get("retro_prompted_for"):
        return

    state["retro_prompted_for"] = keys
    with open(state_path, "w", encoding="utf-8") as handle:
        json.dump(state, handle)

    summary = "; ".join("%s/%s first failed with: %s" % (k[0], k[1], f.get("summary", "")[:120])
                        for k, f in pending)
    log.info("blocking stop for retro: %s", keys)
    emit({
        "decision": "block",
        "reason": ("This session fixed a failing stage (%s). Run the `retro` skill to record what "
                   "broke and how it was fixed, then finish." % summary),
    })


if __name__ == "__main__":
    run_safely(main, log)
