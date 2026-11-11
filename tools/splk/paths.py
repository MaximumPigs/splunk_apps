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
