"""Well-known locations inside the repository.

Everything is resolved from this file's position rather than the current
working directory, so ``splk`` behaves the same from any subdirectory.
"""

import os

# tools/splk/paths.py -> tools/splk -> tools -> repo root
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

APPS_DIR = os.path.join(REPO_ROOT, "apps")
SCRIPTS_DIR = os.path.join(REPO_ROOT, "scripts")
TESTS_DIR = os.path.join(REPO_ROOT, "tests")
LIVE_TESTS_DIR = os.path.join(TESTS_DIR, "live")
CONFIG_DIR = os.path.join(REPO_ROOT, "config")
DIST_DIR = os.path.join(REPO_ROOT, "dist")
BUILD_DIR = os.path.join(REPO_ROOT, "build")

# Machine-local agent state. Gitignored: it holds logs and raw run records,
# which are evidence for the learning loop, not source.
AGENT_DIR = os.path.join(REPO_ROOT, ".agent")
LOG_DIR = os.path.join(AGENT_DIR, "logs")
RUNS_DIR = os.path.join(AGENT_DIR, "runs")

TARGETS_FILE = os.path.join(CONFIG_DIR, "targets.toml")
ENV_FILE = os.path.join(REPO_ROOT, ".env")
MANUAL_CHECKS_FILE = os.path.join(REPO_ROOT, ".appinspect.manualcheck.yaml")
EXPECTED_FAILURES_FILE = os.path.join(REPO_ROOT, ".appinspect.expect.yaml")


def display(path):
    """Repo-relative path for messages, or the absolute path if that fails.

    os.path.relpath raises ValueError on Windows when the path and the repo are
    on different drives (a temp dir on C: with the repo on D:), and a display
    string must never be the thing that fails a stage.
    """
    try:
        return os.path.relpath(path, REPO_ROOT)
    except ValueError:
        return os.path.abspath(path)
