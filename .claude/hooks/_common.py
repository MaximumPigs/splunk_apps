"""Shared plumbing for the Claude Code hook scripts in this directory.

Every hook reads one JSON object on stdin (the event Claude Code sends) and
answers either with an exit code or with one JSON object on stdout. Hooks are
the only *guaranteed* layer of the environment: CLAUDE.md and rules are
guidance Claude can miss, a hook always runs.

Rules for hooks here:
* stdlib only, Python 3.9+ (they run on the developer's machine, often Windows)
* never crash the session: on an internal error, log it and allow the action
* log every decision to .agent/logs/hooks.log for the learning loop
"""

import json
import logging
import logging.handlers
import os
import sys

HOOKS_DIR = os.path.dirname(os.path.abspath(__file__))
# .claude/hooks -> .claude -> repo root, unless Claude Code tells us otherwise.
REPO_ROOT = os.environ.get("CLAUDE_PROJECT_DIR") or os.path.dirname(os.path.dirname(HOOKS_DIR))
# splk is imported from the checkout these hooks live in, not from
# CLAUDE_PROJECT_DIR, so the hook and the tool it calls are always one version.
TOOLS_DIR = os.path.join(os.path.dirname(os.path.dirname(HOOKS_DIR)), "tools")
if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)
AGENT_DIR = os.path.join(REPO_ROOT, ".agent")
SESSIONS_DIR = os.path.join(AGENT_DIR, "sessions")


def get_logger(name):
    """File logger at .agent/logs/hooks.log. Never writes to stdout/stderr.

    stdout is reserved for the JSON answer and stderr for exit-2 reasons, so
    stray log output there would corrupt what Claude Code receives.
    """
    logger = logging.getLogger("hooks.%s" % name)
    if logger.handlers:
        return logger
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    try:
        log_dir = os.path.join(AGENT_DIR, "logs")
        os.makedirs(log_dir, exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(
            os.path.join(log_dir, "hooks.log"), maxBytes=1024 * 1024, backupCount=3, encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        logger.addHandler(handler)
    except OSError:
        logger.addHandler(logging.NullHandler())
    return logger


def read_event():
    """Parse the hook event from stdin; an unreadable event becomes {}."""
    try:
        return json.load(sys.stdin)
    except ValueError:
        return {}


def emit(payload):
    """Write the single JSON answer and exit 0, as Claude Code expects."""
    sys.stdout.write(json.dumps(payload))
    sys.stdout.flush()
    sys.exit(0)


def pre_tool_decision(decision, reason):
    """Answer a PreToolUse event with allow / deny / ask and a reason."""
    emit({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision,
            "permissionDecisionReason": reason,
        }
    })


def add_context(event_name, text):
    """Inject extra context into the conversation (SessionStart and similar)."""
    emit({"hookSpecificOutput": {"hookEventName": event_name, "additionalContext": text}})


def rel(path):
    """Repo-relative path with forward slashes, for matching on any OS."""
    try:
        path = os.path.relpath(os.path.abspath(path), REPO_ROOT)
    except ValueError:  # Different drive on Windows: not inside the repo.
        pass
    return path.replace("\\", "/")


def run_safely(main, logger):
    """Run a hook's main(), failing open if the hook itself is broken.

    A buggy hook must not lock Claude out of the repo; the error is logged so
    the learning loop can see it.
    """
    try:
        main()
    except SystemExit:
        raise
    except Exception:  # noqa: BLE001 - deliberate catch-all, see docstring
        logger.exception("hook crashed; allowing the action")
        sys.exit(0)
