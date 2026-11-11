"""Append-only record of every splk stage result.

Each stage (build, unit, inspect, deploy, live) writes one JSON line to
``.agent/runs/YYYY-MM-DD.jsonl``. This is the raw evidence the self-improvement
loop works from: the Stop hook reads it to spot a failure that was later fixed,
and the learner agent reads it during a retro. It is never loaded into
the agent's context wholesale.
"""

import datetime
import json
import os

from splk import paths
from splk.logs import get_logger

log = get_logger("runlog")


def _now():
    return datetime.datetime.now()


def record(command, app, stage, ok, summary, details=None, runs_dir=None):
    """Append one stage result. Never raises: logging must not break a run."""
    runs_dir = runs_dir or paths.RUNS_DIR
    now = _now()
    entry = {
        "ts": now.strftime("%Y-%m-%dT%H:%M:%S"),
        "epoch": round(now.timestamp(), 3),
        "command": command,
        "app": app,
        "stage": stage,
        "ok": bool(ok),
        "summary": summary,
        # Failing check names, test ids, error text: whatever lets a later
        # reader identify *what* failed without re-running it.
        "details": details or [],
    }
    try:
        os.makedirs(runs_dir, exist_ok=True)
        path = os.path.join(runs_dir, now.strftime("%Y-%m-%d") + ".jsonl")
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError as exc:
        log.warning("Could not write run log: %s", exc)
    return entry


def read_since(epoch, runs_dir=None):
    """Return every entry at or after ``epoch``, oldest first."""
    runs_dir = runs_dir or paths.RUNS_DIR
    if not os.path.isdir(runs_dir):
        return []
    entries = []
    for name in sorted(os.listdir(runs_dir)):
        if not name.endswith(".jsonl"):
            continue
        with open(os.path.join(runs_dir, name), "r", encoding="utf-8") as handle:
            for line in handle:
                try:
                    entry = json.loads(line)
                except ValueError:
                    continue  # A torn write must not hide the rest.
                if entry.get("epoch", 0) >= epoch:
                    entries.append(entry)
    entries.sort(key=lambda e: e.get("epoch", 0))
    return entries


def fixed_failures(entries):
    """(app, stage) pairs that failed and then passed later in ``entries``.

    These are exactly the moments worth a retro: something broke, the agent
    changed something, and it stopped breaking.
    """
    failed_at = {}
    fixed = []
    for entry in entries:
        key = (entry.get("app"), entry.get("stage"))
        if not entry.get("ok"):
            failed_at.setdefault(key, entry)
        elif key in failed_at:
            fixed.append((key, failed_at.pop(key), entry))
    return fixed
