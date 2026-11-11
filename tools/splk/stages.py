"""The individual stages of the dev loop.

Each stage returns a ``StageResult`` and records it in the run log, so the CLI
can chain them (``splk dev``) or run one alone (``splk inspect``) with the
same behaviour and the same evidence trail.
"""

import importlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

from splk import paths, runlog
from splk.logs import get_logger
from splk.rest import SplunkClient, SplunkError

log = get_logger("stages")


class StageResult(object):
    """Outcome of one stage: pass/fail, a one-line summary, and specifics."""

    def __init__(self, stage, app, ok, summary, details=None, artifact=None):
        self.stage = stage
        self.app = app
        self.ok = ok
        self.summary = summary
        self.details = details or []
        # A file the stage produced (package path, report path), if any.
        self.artifact = artifact

    def as_dict(self):
        return {
            "stage": self.stage, "app": self.app, "ok": self.ok,
            "summary": self.summary, "details": self.details, "artifact": self.artifact,
        }


def _finish(command, result):
    """Log a stage result to the console and the run log, then return it."""
    level = log.info if result.ok else log.error
    level("[%s] %s: %s", result.stage, "PASS" if result.ok else "FAIL", result.summary)
    for line in result.details[:20]:
        log.info("    %s", line)
    runlog.record(command, result.app, result.stage, result.ok, result.summary, result.details)
    return result


def _package_app_module():
    """Import scripts/package_app.py, the repo's existing packager.

    Reusing it (rather than re-implementing packaging) keeps one definition of
    what goes into a .spl, already covered by tests/test_package_app.py.
    """
    if paths.SCRIPTS_DIR not in sys.path:
        sys.path.insert(0, paths.SCRIPTS_DIR)
    return importlib.import_module("package_app")


def discover_apps():
    """Every directory under apps/ that has default/app.conf, as CI does."""
    return _package_app_module().discover_apps()


# --------------------------------------------------------------------- build

def build(app, command="build", outdir=None):
    """Package ``apps/<app>`` into ``dist/<app>-<version>.spl``."""
    packager = _package_app_module()
    try:
        package = packager.build_package(app, outdir or paths.DIST_DIR)
    except SystemExit as exc:  # The packager reports problems via SystemExit.
        return _finish(command, StageResult("build", app, False, str(exc)))
    return _finish(command, StageResult(
        "build", app, True, "Built %s" % os.path.relpath(package, paths.REPO_ROOT), artifact=package,
    ))


# ---------------------------------------------------------------- unit tests

def junit_failures(junit_path):
    """Return ``file::name: message`` for every failed or errored test case."""
    if not os.path.isfile(junit_path):
        return []
    failures = []
    for case in ET.parse(junit_path).getroot().iter("testcase"):
        for tag in ("failure", "error"):
            node = case.find(tag)
            if node is not None:
                message = (node.get("message") or "").strip().splitlines()
                failures.append("%s::%s: %s" % (
                    case.get("classname", "?"), case.get("name", "?"),
                    message[0][:200] if message else tag,
                ))
    return failures


def _pytest(stage, app, args, command, env=None):
    """Run pytest in a subprocess and turn its JUnit report into a result."""
    # Without this check a missing pytest surfaces as "No module named pytest"
    # buried in stderr; say what to install instead.
    if importlib.util.find_spec("pytest") is None:
        return _finish(command, StageResult(
            stage, app, False, 'pytest is not installed in this environment: pip install -e ".[dev]"',
        ))
    junit = os.path.join(paths.BUILD_DIR, "reports", "%s-%s.xml" % (stage, app or "all"))
    os.makedirs(os.path.dirname(junit), exist_ok=True)
    cmd = [sys.executable, "-m", "pytest", "-q", "--junitxml", junit] + args
    log.debug("Running: %s", " ".join(cmd))
    proc = subprocess.run(cmd, cwd=paths.REPO_ROOT, env=env, capture_output=True, text=True)
    # pytest prints its final summary last; keep that line for the run log.
    tail = [line for line in proc.stdout.strip().splitlines() if line.strip()]
    summary = tail[-1] if tail else "pytest exit %d" % proc.returncode
    # Exit 5 means no tests were collected: not a failure for an app that has
    # no live tests yet, but worth saying so plainly.
    if proc.returncode == 5:
        return _finish(command, StageResult(stage, app, True, "no tests collected"))
    if proc.returncode != 0 and not os.path.isfile(junit):
        log.debug("pytest stderr: %s", proc.stderr)
    details = junit_failures(junit)
    if proc.returncode != 0 and not details:
        details = (proc.stderr or proc.stdout).strip().splitlines()[-10:]
    return _finish(command, StageResult(stage, app, proc.returncode == 0, summary, details, artifact=junit))


def unit_tests(app=None, command="test"):
    """Run the offline suite (everything under tests/ except tests/live)."""
    return _pytest("unit", app, ["tests", "--ignore", paths.LIVE_TESTS_DIR], command)


def live_tests(app, target, command="test"):
    """Run tests/live/<app> against ``target``.

    The target name is passed through the environment; the live conftest
    resolves it with the same config code splk uses.
    """
    app_dir = os.path.join(paths.LIVE_TESTS_DIR, app)
    if not os.path.isdir(app_dir):
        return _finish(command, StageResult(
            "live", app, False, "No live tests at tests/live/%s; add some with the write-live-test skill" % app,
        ))
    env = dict(os.environ)
    env["SPLK_TARGET"] = target.name
    env["SPLK_LIVE"] = "1"
    return _pytest("live", app, [app_dir], command, env=env)


# ---------------------------------------------------------------- AppInspect

def _yaml_top_level_keys(path):
    """Top-level keys of the repo's AppInspect YAML files, without PyYAML.

    Those files only ever hold ``check_name:`` lines with an indented comment
    underneath, so a line-based read is exact and avoids a dependency.
    """
    if not os.path.isfile(path):
        return set()
    keys = set()
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            match = re.match(r"^([A-Za-z0-9_]+):\s*$", line.rstrip())
            if match:
                keys.add(match.group(1))
    return keys


def summarise_appinspect(report, reviewed_manual=frozenset(), waived=frozenset()):
    """Reduce an AppInspect JSON report to (ok, summary, details).

    The run fails on any failure or error not waived in .appinspect.expect.yaml,
    and on any manual check not reviewed in .appinspect.manualcheck.yaml. That
    mirrors what the CI action enforces, so local green means CI green.
    """
    problems, unreviewed, counts = [], [], {}
    for app_report in report.get("reports", []):
        for group in app_report.get("groups", []):
            for check in group.get("checks", []):
                result = check.get("result")
                counts[result] = counts.get(result, 0) + 1
                name = check.get("name", "?")
                # First non-empty message line, enough to identify the problem.
                texts = [(m.get("message") or "").strip() for m in (check.get("messages") or [])]
                first = next((t.splitlines()[0][:200] for t in texts if t), "")
                if result in ("failure", "error") and name not in waived:
                    problems.append("%s %s: %s" % (result.upper(), name, first))
                elif result == "manual_check" and name not in reviewed_manual:
                    unreviewed.append("UNREVIEWED manual_check %s: %s" % (name, first))
                elif result == "future_failure":
                    # Not blocking today, but it will be: surface it early.
                    log.warning("future_failure %s: %s", name, first)
    ok = not problems and not unreviewed
    summary = ", ".join("%s=%d" % (k, counts[k]) for k in sorted(counts)) or "no checks reported"
    return ok, summary, problems + unreviewed


def inspect(app, package, command="inspect"):
    """Run the AppInspect CLI over the full check set (no tag filter).

    The full set is deliberate: a cloud-only run once let through a package
    Splunkbase rejected (check_for_updates_disabled is not tagged cloud).
    """
    exe = shutil.which("splunk-appinspect")
    if not exe:
        return _finish(command, StageResult(
            "inspect", app, False, 'splunk-appinspect is not installed: pip install -e ".[dev]"',
        ))
    report_path = os.path.join(paths.BUILD_DIR, "reports", "appinspect-%s.json" % app)
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    cmd = [exe, "inspect", package, "--mode", "test", "--data-format", "json", "--output-file", report_path]
    log.debug("Running: %s", " ".join(cmd))
    proc = subprocess.run(cmd, cwd=paths.REPO_ROOT, capture_output=True, text=True)
    if not os.path.isfile(report_path):
        tail = (proc.stderr or proc.stdout).strip().splitlines()[-10:]
        return _finish(command, StageResult("inspect", app, False, "AppInspect produced no report", tail))
    with open(report_path, "r", encoding="utf-8") as handle:
        report = json.load(handle)
    ok, summary, details = summarise_appinspect(
        report,
        reviewed_manual=_yaml_top_level_keys(paths.MANUAL_CHECKS_FILE),
        waived=_yaml_top_level_keys(paths.EXPECTED_FAILURES_FILE),
    )
    return _finish(command, StageResult("inspect", app, ok, summary, details, artifact=report_path))


# -------------------------------------------------------------------- deploy

def _server_path(target, package):
    """Copy the package where splunkd can read it, and return splunkd's path."""
    if not target.stage_dir:
        # Same filesystem: splunkd reads straight from dist/.
        return os.path.abspath(package)
    os.makedirs(target.stage_dir, exist_ok=True)
    staged = os.path.join(target.stage_dir, os.path.basename(package))
    shutil.copyfile(package, staged)
    server_dir = target.server_stage_dir or target.stage_dir
    # Join with "/" when splunkd's view is POSIX-style (Docker, WSL).
    sep = "/" if "/" in server_dir else os.sep
    return server_dir.rstrip("/\\") + sep + os.path.basename(package)


def deploy(app, package, target, restart=False, command="deploy", client=None):
    """Install or upgrade ``package`` on ``target`` and make it take effect.

    Order: install via REST, verify the installed version, reload apps, then
    check for splunkd's 'restart required' message. A restart only happens if
    the target allows it AND ``restart`` was passed; otherwise the stage fails
    and says a restart is needed, so nothing disruptive happens implicitly.
    """
    client = client or SplunkClient(target)
    packager = _package_app_module()
    expected = packager.read_app_version(os.path.join(paths.APPS_DIR, app))
    server_path = _server_path(target, package)
    try:
        client.install_package(server_path)
        installed = client.app_info(app) or {}
        version = installed.get("version")
        if version != expected:
            return _finish(command, StageResult("deploy", app, False,
                "Installed version is %s, expected %s; overwrite may not have applied" % (version, expected)))
        try:
            client.reload_apps()
        except SplunkError as exc:
            # A failed reload is not fatal: some changes still apply, and the
            # restart check below decides whether more is needed.
            log.warning("App reload failed: %s", exc)
        if client.restart_required():
            if restart and target.allow_restart:
                client.restart()
            else:
                why = ("pass --restart" if target.allow_restart
                       else "target %s has allow_restart = false" % target.name)
                return _finish(command, StageResult("deploy", app, False,
                    "Installed %s %s but splunkd needs a restart (%s)" % (app, version, why)))
    except SplunkError as exc:
        return _finish(command, StageResult("deploy", app, False, str(exc)))
    return _finish(command, StageResult(
        "deploy", app, True, "Installed %s %s on %s" % (app, expected, target.name),
    ))
