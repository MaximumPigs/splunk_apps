"""Fixtures for live tests: tests that run SPL on a real Splunk target.

Live tests are skipped unless ``SPLK_LIVE=1`` is set, which ``splk test --live``
and ``splk dev`` do for you. That keeps plain ``pytest`` and CI offline.

Layout: one directory per app, ``tests/live/<app>/test_*.py``, so ``splk dev
<app>`` runs only that app's live tests.

Live tests may change anything on the dev target through the ``sandbox``
fixture. Users, roles and app permissions are snapshotted around every test
and put back afterwards, pass or fail; see ``splk.testing``.
"""

import logging
import os

import pytest

from splk import config, paths, stages
from splk.rest import SplunkClient, SplunkError
# Every live test runs inside the environment guard, and may use ``sandbox`` to
# create and change users, roles and app permissions: see splk.testing.
from splk.testing import _environment_guard, _sandbox_session, sandbox, sandbox_client  # noqa: F401

log = logging.getLogger("splk.live")

LIVE_DIR = os.path.dirname(os.path.abspath(__file__))


def pytest_collection_modifyitems(config, items):
    """Skip every test under tests/live/ unless live mode is switched on."""
    if os.environ.get("SPLK_LIVE") == "1":
        return
    skip = pytest.mark.skip(reason="live test: run via `splk test --live <app>` or set SPLK_LIVE=1")
    for item in items:
        if str(item.fspath).startswith(LIVE_DIR):
            item.add_marker(skip)


@pytest.fixture(scope="session")
def target():
    """The Splunk target named by SPLK_TARGET (or the default), with its token."""
    config.load_env_file()
    try:
        return config.resolve_target()
    except config.ConfigError as exc:
        pytest.fail("Live target misconfigured: %s" % exc)


@pytest.fixture(scope="session")
def splunk(target):
    """A REST client for the target, checked once per session.

    Failing here (rather than in each test) gives one clear error when the
    instance is down or the token is wrong.
    """
    client = SplunkClient(target)
    try:
        info = client.server_info()
    except SplunkError as exc:
        pytest.fail("Cannot reach %s: %s" % (target.describe(), exc))
    log.info("Live tests against Splunk %s at %s", info.get("version"), target.base_url)
    return client


@pytest.fixture
def search(splunk):
    """Run SPL and return rows; logs the query so failures are reproducible.

    Usage: ``rows = search('| makeresults | eval x=1')``
    """
    def run(spl, earliest="-24h", latest="now"):
        log.info("SPL: %s", spl)
        rows = splunk.oneshot(spl, earliest=earliest, latest=latest)
        log.info("-> %d row(s)", len(rows))
        return rows
    return run


@pytest.fixture
def seed(splunk, target):
    """Index raw events into the target's test index and wait until searchable.

    Usage::

        marker = seed(["127.0.0.1 - - [01/Jan/2026:00:00:00 +0000] \\"GET / HTTP/1.1\\" 200"],
                      sourcetype="acme:web")
        rows = search('index=%s source="%s" | table status' % (target.test_index, marker))

    Each call tags its events with a unique ``source`` (returned as the marker)
    so tests never see each other's data, and nothing needs deleting.
    """
    import time
    import uuid

    if not splunk.index_exists(target.test_index):
        pytest.fail("Test index %r does not exist on %s. Create it once in Splunk Web "
                    "(Settings > Indexes) as a dev-only index." % (target.test_index, target.name))

    def run(events, sourcetype, timeout=60):
        marker = "splk:live:%s" % uuid.uuid4().hex[:12]
        for raw in events:
            splunk.submit_event(raw, index=target.test_index, sourcetype=sourcetype, source=marker)
        # Indexing is asynchronous: poll until every event is searchable.
        deadline = time.time() + timeout
        spl = 'search index=%s source="%s" | stats count' % (target.test_index, marker)
        while time.time() < deadline:
            rows = splunk.oneshot(spl, earliest="0", latest="+1d")
            if rows and int(rows[0].get("count", 0)) >= len(events):
                log.info("Seeded %d event(s) as %s", len(events), marker)
                return marker
            time.sleep(1)
        pytest.fail("Seed events not searchable within %ds (source=%s)" % (timeout, marker))
    return run


@pytest.fixture
def expected_version():
    """Return the version an app declares in apps/<app>/default/app.conf."""
    def lookup(app):
        packager = stages._package_app_module()
        return packager.read_app_version(os.path.join(paths.APPS_DIR, app))
    return lookup
