"""Fixtures for UI tests: tests that drive Splunk Web in a real browser.

UI tests are not collected at all unless ``SPLK_UI=1`` is set, which
``splk test --ui <app>`` and ``splk dev <app>`` do. Not collecting (rather than
skipping) matters: test modules may import Playwright, which plain ``pytest``
and CI do not install.

Layout: ``tests/ui/<app>/test_*.py``. Evidence for every test lands in
``build/reports/ui/<app>/``: screenshots the test takes on purpose, plus a
screenshot and a Playwright trace (``python -m playwright show-trace <zip>``)
for every failure.
"""

import logging
import os

import pytest

from splk import config
from splk import ui as splk_ui

log = logging.getLogger("splk.ui")

UI_DIR = os.path.dirname(os.path.abspath(__file__))

if os.environ.get("SPLK_UI") != "1":
    # Everything below this directory is invisible to plain pytest.
    collect_ignore_glob = ["*"]


def _app_of(item):
    """The app a test belongs to: the directory under tests/ui/ it lives in."""
    rel = os.path.relpath(str(item.fspath), UI_DIR)
    return rel.replace("\\", "/").split("/")[0]


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Keep each phase's report on the item so fixtures can tell a failure from a pass."""
    outcome = yield
    report = outcome.get_result()
    setattr(item, "rep_" + report.when, report)


@pytest.fixture(scope="session")
def target():
    """The Splunk target named by SPLK_TARGET (or the default). No token needed."""
    config.load_env_file()
    try:
        target = config.resolve_target(require_token=False)
        splk_ui.require_web(target)
        splk_ui.web_credentials(target)
    except config.ConfigError as exc:
        pytest.fail("UI target misconfigured: %s" % exc)
    return target


@pytest.fixture(scope="session")
def web(target):
    """One signed-in browser for the whole run, with tracing ready per test."""
    try:
        with splk_ui.SplunkWeb(target) as session:
            # Snapshots let a failing step be replayed with the DOM as it was.
            session.context.tracing.start(screenshots=True, snapshots=True)
            yield session
            session.context.tracing.stop()
    except splk_ui.UiError as exc:
        pytest.fail(str(exc))


@pytest.fixture
def artifacts(request):
    """Directory for this test's screenshots and traces: build/reports/ui/<app>/."""
    path = os.path.join(splk_ui.REPORTS_DIR, _app_of(request.node))
    os.makedirs(path, exist_ok=True)
    return path


@pytest.fixture
def page(web, request, artifacts):
    """A fresh tab. On failure, saves a screenshot and a trace of this test."""
    web.context.tracing.start_chunk()
    tab = web.new_page()
    yield tab
    name = splk_ui.slug(request.node.name)
    failed = getattr(request.node, "rep_call", None) is not None and request.node.rep_call.failed
    if failed:
        shot = os.path.join(artifacts, "%s-FAILED.png" % name)
        trace = os.path.join(artifacts, "%s-trace.zip" % name)
        try:
            web.screenshot(tab, shot)
        except Exception as exc:  # noqa: BLE001 - evidence is best-effort
            log.warning("Could not screenshot failed test: %s", exc)
        web.context.tracing.stop_chunk(path=trace)
        log.error("UI test failed; screenshot %s, trace %s", shot, trace)
    else:
        web.context.tracing.stop_chunk()
    tab.close()


@pytest.fixture
def open_view(web, page):
    """Open an app view in the test's tab and return the tab.

    Usage: ``open_view("easyadmin", "role_management", theme="dark", ready="#root table")``.
    Pass ``ready`` (a CSS selector) whenever an assertion depends on what the
    dashboard's JavaScript renders: the load event fires long before that.
    """
    def run(app, view=None, theme=None, ready=None, settle_ms=0):
        log.info("Opening %s/%s (theme=%s)", app, view or "", theme or "as Splunk chooses")
        try:
            return web.open_view(page, app, view, theme=theme, ready_selector=ready, settle_ms=settle_ms)
        except splk_ui.UiError as exc:
            pytest.fail(str(exc))
    return run


@pytest.fixture
def shot(web, artifacts):
    """Save a named screenshot as evidence and return its path, so the agent can look at it."""
    def run(tab, name, full_page=True):
        return web.screenshot(tab, os.path.join(artifacts, "%s.png" % splk_ui.slug(name)), full_page)
    return run


@pytest.fixture
def page_log(web):
    """Console errors and uncaught exceptions for a tab: ``page_log(tab).page_errors``."""
    return web.page_log
