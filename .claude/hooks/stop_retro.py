#!/usr/bin/env python3
"""Stop hook: don't let a session end with its learning or security review undone.

Before Claude finishes, this checks the session for four follow-ups and, if
any is due, blocks the stop once with one message asking for them:

* **retro (fix)**: a splk stage failed and later passed for the same app and
  stage, and nothing was recorded since. The original trigger.
* **retro (debrief)**: an app was deployed this session but no lesson or
  playbook pattern was written. Work that never went red still teaches
  something (easyadmin's dark mode took three attempts and no stage failed),
  so every session that ships app changes gets a debrief. Apps deployed three
  or more times are named: repeated deploys are the clearest sign of
  iteration worth a pattern.
* **security review**: code changed this session after the last
  `splunk-security-review` result was recorded (`splk review security ...`).
* **UX review**: something a person sees (a view, page script or stylesheet)
  changed this session after the last `splunk-ux-review` result was recorded
  (`splk review ux ...`). The automated `ux` stage catches accessibility and
  errors; layout, wording and states need the reviewer's eyes.

The file keeps the name stop_retro.py because .claude/settings.json refers to
it, and changing that file is a safety change made only by the person.

Asks at most once per distinct set of follow-ups (tracked in .agent/sessions/),
and never when Claude Code says a Stop hook is already driving the continuation.
"""

import json
import os
import re
import subprocess

from _common import AGENT_DIR, REPO_ROOT, SESSIONS_DIR, emit, get_logger, read_event, run_safely

log = get_logger("stop_followups")

# The two learning stores: lessons (what went wrong) and the playbook (what works).
LEARNING_DIRS = (
    os.path.join(REPO_ROOT, ".claude", "agent-memory", "learner"),
    os.path.join(REPO_ROOT, ".claude", "skills", "splunk-playbook"),
)
# The run log stages that `splk review security` and `splk review ux` record.
SECURITY_STAGE = "security"
UX_REVIEW_STAGE = "ux-review"

# Deploys of one app in one session that suggest iteration worth a pattern.
ITERATION_THRESHOLD = 3

# Code a security review must cover. Vendored libraries are excluded: they are
# verified by hash when vendored, not reviewed line by line.
CODE_PREFIXES = ("apps/", "tools/", "scripts/", ".claude/hooks/", ".github/workflows/")
CODE_EXTENSIONS = (".py", ".js", ".conf", ".meta", ".xml", ".html", ".yml", ".yaml", ".toml", ".sh", ".ps1")

# What a person sees in Splunk Web: views and navigation, and the static files
# (page JavaScript, CSS, images, templates) that draw them.
UI_PATH_RE = re.compile(r"^apps/[^/]+/(appserver/|default/data/ui/)")


# ------------------------------------------------------------ pure decisions

def newest_mtime(directories):
    """Most recent modification time of any file under the given directories."""
    newest = 0.0
    for directory in directories:
        for root, _dirs, files in os.walk(directory):
            for name in files:
                newest = max(newest, os.path.getmtime(os.path.join(root, name)))
    return newest


def pending_fixes(fixed, learned_at):
    """(app, stage) keys whose fix came after the last learning write."""
    return [(key, failed) for key, failed, passed in fixed if passed.get("epoch", 0) > learned_at]


def last_review(entries, stage=SECURITY_STAGE):
    """Epoch of the most recent recorded review of this kind, pass or fail; 0 if none."""
    times = [e.get("epoch", 0) for e in entries if e.get("stage") == stage]
    return max(times) if times else 0.0


def deploys_by_app(entries):
    """Successful deploy count per app, from run log entries."""
    counts = {}
    for entry in entries:
        if entry.get("stage") == "deploy" and entry.get("ok"):
            counts[entry.get("app")] = counts.get(entry.get("app"), 0) + 1
    return counts


def is_ui(path):
    """True for app files that change what a person sees in Splunk Web."""
    return bool(UI_PATH_RE.match(path.replace("\\", "/")))


def unreviewed_ui(changed, mtimes, started, reviewed_at):
    """Changed UI files edited this session after the last UX review."""
    return sorted(p for p in changed if is_ui(p) and mtimes.get(p, 0) > max(started, reviewed_at))


def is_code(path):
    """True for repository files a security review should look at."""
    path = path.replace("\\", "/")
    if "/lib/" in path and path.startswith("apps/"):
        return False  # vendored dependencies
    return path.startswith(CODE_PREFIXES) and path.endswith(CODE_EXTENSIONS)


def unreviewed_code(changed, mtimes, started, reviewed_at):
    """Changed code files edited this session after the last security review."""
    return sorted(p for p in changed if is_code(p) and mtimes.get(p, 0) > max(started, reviewed_at))


def followups(fixed, entries, learned_at, started, unreviewed, ui_unreviewed=()):
    """Return [(key, sentence)] for every follow-up due. Keys dedupe the nag."""
    due = []
    fixes = pending_fixes(fixed, learned_at)
    if fixes:
        summary = "; ".join("%s/%s first failed with: %s" % (k[0], k[1], f.get("summary", "")[:120])
                            for k, f in fixes)
        due.append(("fix:" + ",".join(sorted("%s/%s" % k for k, _ in fixes)),
                    "This session fixed a failing stage (%s). Run the `retro` skill to record the "
                    "lesson." % summary))
    deploys = deploys_by_app(entries)
    if deploys and learned_at < started and not fixes:
        busy = sorted("%s (%d deploys)" % (app, n) for app, n in deploys.items() if n >= ITERATION_THRESHOLD)
        detail = (" %s took several iterations: record what made it take that many tries, and the "
                  "approach that finally worked, as a playbook pattern." % ", ".join(busy)) if busy else ""
        due.append(("debrief:" + ",".join(sorted(deploys)),
                    "This session deployed %s but recorded nothing in the lessons or the playbook. "
                    "Run the `retro` skill to debrief what worked as well as what failed.%s"
                    % (", ".join(sorted(deploys)), detail)))
    if unreviewed:
        shown = ", ".join(unreviewed[:8]) + (" and %d more" % (len(unreviewed) - 8) if len(unreviewed) > 8 else "")
        due.append(("security:" + ",".join(unreviewed),
                    "Code changed since the last security review (%s). Run the `splunk-security-review` "
                    "skill and fix what it reports, or tell the person which findings remain." % shown))
    if ui_unreviewed:
        shown = ", ".join(ui_unreviewed[:8]) + (
            " and %d more" % (len(ui_unreviewed) - 8) if len(ui_unreviewed) > 8 else "")
        due.append(("ux:" + ",".join(ui_unreviewed),
                    "What users see changed since the last UX review (%s). Run the `splunk-ux-review` "
                    "skill and fix what it reports, or tell the person which findings remain." % shown))
    return due


# ------------------------------------------------------------- git plumbing

def _git(args):
    """Run git in the repo; return stdout lines, or [] if git fails (fail open)."""
    try:
        proc = subprocess.run(["git"] + args, cwd=REPO_ROOT, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError) as exc:
        log.debug("git %s failed: %s", args, exc)
        return []
    return [line for line in proc.stdout.splitlines() if line.strip()] if proc.returncode == 0 else []


def changed_files():
    """Files changed on this branch against main, plus uncommitted and untracked ones."""
    changed = set(_git(["diff", "--name-only", "origin/main...HEAD"]))
    for line in _git(["status", "--porcelain", "--untracked-files=all"]):
        # "XY path" or "XY old -> new" for renames.
        changed.add(line[3:].split(" -> ")[-1].strip('"'))
    return changed


def file_mtimes(paths):
    mtimes = {}
    for path in paths:
        full = os.path.join(REPO_ROOT, path)
        if os.path.isfile(full):
            mtimes[path] = os.path.getmtime(full)
    return mtimes


# ---------------------------------------------------------------------- main

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
    started = state.get("started", 0)

    from splk import runlog
    entries = runlog.read_since(started, runs_dir=os.path.join(AGENT_DIR, "runs"))
    changed = changed_files()
    reviewed_at = last_review(entries)
    mtimes = file_mtimes(changed)
    due = followups(
        fixed=runlog.fixed_failures(entries),
        entries=entries,
        learned_at=newest_mtime(LEARNING_DIRS),
        started=started,
        unreviewed=unreviewed_code(changed, mtimes, started, reviewed_at),
        ui_unreviewed=unreviewed_ui(changed, mtimes, started, last_review(entries, UX_REVIEW_STAGE)),
    )
    prompted = set(state.get("followups_prompted_for") or [])
    new = [(key, text) for key, text in due if key not in prompted]
    if not new:
        return

    state["followups_prompted_for"] = sorted(prompted | {key for key, _ in new})
    with open(state_path, "w", encoding="utf-8") as handle:
        json.dump(state, handle)
    log.info("blocking stop for follow-ups: %s", [key for key, _ in new])
    emit({
        "decision": "block",
        "reason": "Before finishing:\n- " + "\n- ".join(text for _, text in new) +
                  "\nIf one does not apply, say why in one line and finish.",
    })


if __name__ == "__main__":
    run_safely(main, log)
