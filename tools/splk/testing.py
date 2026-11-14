"""pytest fixtures that let live and UI tests change the target safely.

Imported into ``tests/live/conftest.py`` and ``tests/ui/conftest.py``; tests
use only the ``sandbox`` fixture. What happens around every test:

1. Session start: ``sweep`` deletes ``splktest_*`` objects a killed run left
   behind, and a snapshot saved by a run that died mid-test is repaired if
   it is under an hour old (older, its differences are only reported).
2. Before each test: users, roles and the repo's app permissions are
   snapshotted (and the snapshot is saved to disk, for step 1 of a later run).
3. The test runs, creating and changing things through ``sandbox``.
4. After it, pass or fail: ``sandbox.cleanup()`` deletes what was created and
   writes back what was changed.
5. Then the guard snapshots again. Any remaining difference (something
   changed outside the sandbox, or a cleanup step failed) is repaired where
   that is safe, and the test errors in teardown naming each difference.
6. Session end: the whole target is compared with its state at session start
   and the run errors if anything differs. Only sandbox leftovers are
   deleted here: a change between tests is reported, not reverted, since it
   may be someone else's.

So a passing run proves both the feature and the restore.
"""

import os

import pytest

from splk import paths
from splk import sandbox as sb
from splk.logs import get_logger
from splk.rest import SplunkClient, SplunkError

log = get_logger("sandbox")

# A snapshot left by a killed run is repaired automatically only this soon
# afterwards (seconds). Later, someone may have changed the target on
# purpose since, so the differences are reported instead.
STALE_REPAIR_SECONDS = 3600


def _apps():
    """Every app in the repository: their permissions are snapshotted."""
    if not os.path.isdir(paths.APPS_DIR):
        return ()
    return tuple(sorted(name for name in os.listdir(paths.APPS_DIR)
                        if os.path.isfile(os.path.join(paths.APPS_DIR, name, "default", "app.conf"))))


@pytest.fixture(scope="session")
def sandbox_client(target):
    """An admin REST client for setting up and putting back state.

    Uses the target's token, which UI tests otherwise do not need: a UI test
    that changes anything needs it to put things back.
    """
    if not target.token:
        pytest.fail("Target %s has no token ($%s): needed to put the target back after a test "
                    "that changes it" % (target.name, target.token_env))
    client = SplunkClient(target)
    try:
        client.server_info()
    except SplunkError as exc:
        pytest.fail("Cannot reach %s: %s" % (target.describe(), exc))
    return client


@pytest.fixture(scope="session")
def _sandbox_session(sandbox_client, target):
    """Recover from earlier runs, then hold the whole-session baseline."""
    pending = sb.pending_path(paths.AGENT_DIR, target.name)
    stale = sb.load_pending(pending)
    if stale is not None:
        # A previous run died mid-test. Put back what that test changed, but
        # only while the snapshot is fresh: an old one would revert changes
        # someone has made legitimately since, with the admin token.
        current = sb.snapshot(sandbox_client, _apps())
        age = sb.pending_age(pending)
        if age <= STALE_REPAIR_SECONDS:
            log.warning("A previous run stopped mid-test %ds ago; repairing the target "
                        "against its snapshot", age)
            for problem in sb.repair(sandbox_client, stale, current):
                log.error("Could not repair after the interrupted run: %s", problem)
        else:
            log.warning("A previous run stopped mid-test %ds ago; too long ago to repair "
                        "safely. Differences since then (check them by hand):", age)
            for difference in sb.diff(stale, current):
                log.warning("  %s", sb.describe(difference))
        sb.clear_pending(pending)
    for kind, name in sb.sweep(sandbox_client):
        log.warning("Swept leftover %s %s", kind, name)

    baseline = sb.snapshot(sandbox_client, _apps())
    yield baseline

    final = sb.snapshot(sandbox_client, _apps())
    differences = sb.diff(baseline, final)
    if differences:
        # Every test was already checked and repaired, so what is left
        # happened between tests: most likely someone working on the target
        # during the run. Delete only leftover sandbox objects; report the
        # rest rather than revert another person's change.
        leftovers = sb.sweep(sandbox_client)
        lines = [sb.describe(d) for d in differences]
        lines += ["deleted leftover %s %s" % item for item in leftovers]
        pytest.fail("The target differs from its state at the start of the run "
                    "(not reverted: check whether these were made by someone else):\n  "
                    + "\n  ".join(lines))
    log.info("Target is as it was at the start of the run")


@pytest.fixture(autouse=True)
def _environment_guard(request, _sandbox_session, sandbox_client, target):
    """Snapshot before every test; after it, repair and report any difference.

    Autouse and set up before the test's own fixtures, so it tears down after
    them: it sees the target once ``sandbox`` has cleaned up.
    """
    pending = sb.pending_path(paths.AGENT_DIR, target.name)
    before = sb.snapshot(sandbox_client, _apps())
    sb.save_pending(pending, before)
    yield
    after = sb.snapshot(sandbox_client, _apps())
    differences = sb.diff(before, after)
    if not differences:
        sb.clear_pending(pending)
        return
    for difference in differences:
        log.error("%s left a change behind: %s", request.node.nodeid, sb.describe(difference))
    problems = sb.repair(sandbox_client, before, after)
    # Repairs are checked, not assumed.
    remaining = sb.diff(before, sb.snapshot(sandbox_client, _apps()))
    if not remaining:
        sb.clear_pending(pending)
    lines = [sb.describe(d) for d in differences]
    lines += ["unrepaired: " + p for p in problems]
    lines += ["still different: " + sb.describe(d) for d in remaining]
    pytest.fail("Test changed the target outside the sandbox (repaired where possible):\n  "
                + "\n  ".join(lines), pytrace=False)


@pytest.fixture
def sandbox(sandbox_client):
    """Create and change users, roles and app permissions; all undone after the test.

    See ``splk.sandbox.Sandbox``. Cleanup runs whether the test passed or not.
    """
    ledger = sb.Sandbox(sandbox_client)
    yield ledger
    try:
        ledger.cleanup()
    except sb.SandboxError as exc:
        # The guard then reports and repairs what is still different.
        pytest.fail("Sandbox cleanup was incomplete: %s" % exc, pytrace=False)
