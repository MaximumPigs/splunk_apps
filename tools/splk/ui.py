"""Splunk Web in a real browser: the engine behind UI tests and `splk shot`.

Some behaviour only exists in a browser: themes, layout, a dashboard's
JavaScript, what a page actually renders. `splk search` and the REST client
cannot observe any of it, which is how easyadmin's dark mode was documented as
working before anyone had seen it. This module lets the agent look for itself,
unattended, against the target's Splunk Web.

Design notes:

* Playwright, not Selenium: it ships its own browser builds (no driver to
  match to a Chrome version), waits for elements automatically, and records
  traces that replay a failed test step by step.
* Splunk Web does not accept auth tokens, so the browser signs in through the
  login form with a username and password from the environment (normally the
  gitignored .env). The signed-in session is cached in .agent/ui/ so a test run
  signs in once, not once per test.
* Playwright is imported lazily, so the rest of splk (and CI, which never runs
  browser tests) works without it installed.
"""

import os
import urllib.parse

from splk import config, paths
from splk.logs import get_logger

log = get_logger("ui")

# Cached browser sessions (cookies), one file per target. Under .agent/, which
# is gitignored: these are sign-in cookies for the dev instance.
STATE_DIR = os.path.join(paths.AGENT_DIR, "ui")
# Screenshots, traces and other evidence from browser runs.
REPORTS_DIR = os.path.join(paths.BUILD_DIR, "reports", "ui")

# Splunk Web's sign-in page, under the locale prefix.
LOGIN_PATH = "/account/login"
# Optional path to a Chromium binary, for machines where Playwright's own
# browser download is not available (a CI image or sandbox with Chromium
# preinstalled). Unset means Playwright's bundled browser.
EXECUTABLE_ENV = "SPLK_BROWSER_EXECUTABLE"
# Set to 1 to show the browser window (splk --headed sets it for test runs).
HEADED_ENV = "SPLK_UI_HEADED"

# A desktop-sized viewport, so screenshots match what a person sees.
VIEWPORT = {"width": 1440, "height": 900}

INSTALL_HINT = 'Playwright is not installed: pip install -e ".[ui]" then python -m playwright install chromium'


class UiError(Exception):
    """The browser could not do what was asked (sign-in failed, page never readied)."""


# ------------------------------------------------------------- pure helpers

def require_web(target):
    """Fail with a usage error when the target does not declare Splunk Web."""
    if not target.web_url:
        raise config.ConfigError(
            "Target %r has no web_url in config/targets.toml; browser tests need Splunk Web's "
            "address (e.g. web_url = \"http://localhost:8000\")" % target.name)


def web_credentials(target, environ=None):
    """Return (username, password) for Splunk Web, or raise ConfigError naming what is missing.

    The values are never logged: only the variable names appear in messages.
    """
    environ = os.environ if environ is None else environ
    user = environ.get(target.web_user_env)
    password = environ.get(target.web_password_env)
    missing = [name for name, value in ((target.web_user_env, user), (target.web_password_env, password))
               if not value]
    if missing:
        raise config.ConfigError(
            "Splunk Web sign-in needs %s (set in .env; see .env.example)" % " and ".join("$" + m for m in missing))
    return user, password


def web_url(target, path):
    """Absolute Splunk Web URL for ``path`` (which starts with "/"), under the locale prefix."""
    if not path.startswith("/"):
        path = "/" + path
    return "%s/%s%s" % (target.web_url, target.web_locale, path)


def view_path(app, view=None, theme=None):
    """Splunk Web path of an app's view; no view means the app's default page.

    ``theme`` adds ?theme=light|dark, which is how a Classic dashboard is told
    its theme (it ignores the user's preference on its own).
    """
    path = "/app/%s/" % urllib.parse.quote(app, safe="")
    if view:
        path += urllib.parse.quote(view, safe="")
    if theme:
        path += "?" + urllib.parse.urlencode({"theme": theme})
    return path


def parse_page_spec(spec):
    """Turn `splk shot`'s page argument into a Splunk Web path.

    ``app``           -> the app's default view
    ``app/view``      -> that view
    ``/any/path``     -> used as is (under the locale prefix), e.g. /manager/launcher/apps/local
    """
    if spec.startswith("/"):
        return spec, None, None
    app, _, view = spec.partition("/")
    if not app:
        raise config.ConfigError("Empty page spec; use <app>, <app>/<view> or /path")
    return None, app, view or None


def is_login_url(url):
    """True when ``url`` is Splunk Web's sign-in page (where it redirects anonymous visitors)."""
    return LOGIN_PATH in urllib.parse.urlparse(url).path


def state_file(target, state_dir=None):
    """Where the signed-in browser session for ``target`` is cached."""
    return os.path.join(state_dir or STATE_DIR, "%s-state.json" % target.name)


def slug(text):
    """File-name-safe version of a page spec or test name, for screenshot paths."""
    keep = [c if c.isalnum() or c in "-_." else "-" for c in text.strip("/")]
    return "".join(keep).strip("-") or "page"


# ------------------------------------------------------------------ browser

class PageLog(object):
    """Console errors and uncaught exceptions a page produced.

    These are often the only sign that a dashboard's JavaScript broke: the
    page still loads, the panel just stays empty.
    """

    def __init__(self):
        self.console_errors = []
        self.page_errors = []

    def attach(self, page):
        page.on("console", self._on_console)
        page.on("pageerror", self._on_page_error)

    def _on_console(self, message):
        if message.type == "error":
            self.console_errors.append(message.text)
            log.debug("console error: %s", message.text)

    def clear(self):
        """Forget earlier entries, so the log describes only the page opened next."""
        del self.console_errors[:]
        del self.page_errors[:]

    def _on_page_error(self, error):
        self.page_errors.append(str(error))
        log.debug("page error: %s", error)

    def as_dict(self):
        return {"console_errors": list(self.console_errors), "page_errors": list(self.page_errors)}


class SplunkWeb(object):
    """A signed-in browser session on one target's Splunk Web.

    Use as a context manager::

        with SplunkWeb(target) as web:
            page = web.new_page()
            web.open_view(page, "easyadmin", "role_management", theme="dark")
            web.screenshot(page, "build/reports/ui/shot.png")
    """

    def __init__(self, target, headed=None, environ=None, state_dir=None, timeout_ms=30000):
        require_web(target)
        self.target = target
        self.environ = os.environ if environ is None else environ
        self.headed = (self.environ.get(HEADED_ENV) == "1") if headed is None else bool(headed)
        self.state_path = state_file(target, state_dir)
        self.timeout_ms = timeout_ms
        self.logs = {}  # id(page) -> PageLog
        self._playwright = None
        self._browser = None
        self.context = None

    # -------------------------------------------------------------- lifecycle

    def __enter__(self):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise UiError(INSTALL_HINT)
        self._playwright = sync_playwright().start()
        launch = {"headless": not self.headed}
        executable = self.environ.get(EXECUTABLE_ENV)
        if executable:
            launch["executable_path"] = executable
        log.debug("Launching Chromium (headless=%s, executable=%s)", launch["headless"], executable or "bundled")
        self._browser = self._playwright.chromium.launch(**launch)
        options = {
            "viewport": VIEWPORT,
            # Same switch as the REST client: a dev instance's self-signed
            # certificate is accepted only when the target says so.
            "ignore_https_errors": not self.target.verify_tls,
        }
        if os.path.isfile(self.state_path):
            # Reuse the cached sign-in; if it has expired, open() signs in again.
            options["storage_state"] = self.state_path
        self.context = self._browser.new_context(**options)
        self.context.set_default_timeout(self.timeout_ms)
        return self

    def __exit__(self, *exc_info):
        # Close in reverse order; each step is best-effort so one failure does
        # not leave a browser process behind.
        for closer in (getattr(self.context, "close", None), getattr(self._browser, "close", None),
                       getattr(self._playwright, "stop", None)):
            if closer is None:
                continue
            try:
                closer()
            except Exception as exc:  # noqa: BLE001 - cleanup must not mask the real error
                log.debug("Browser cleanup step failed: %s", exc)
        return False

    # ------------------------------------------------------------------ pages

    def new_page(self):
        """Open a tab whose console errors are recorded (see page_log)."""
        page = self.context.new_page()
        page_log = PageLog()
        page_log.attach(page)
        self.logs[id(page)] = page_log
        return page

    def page_log(self, page):
        """The PageLog for a page opened with new_page()."""
        return self.logs.setdefault(id(page), PageLog())

    def url(self, path):
        return web_url(self.target, path)

    def login(self, page):
        """Sign in through Splunk Web's login form and cache the session.

        Fields are found by name, and the submit control by type, rather than
        by ids or classes that change between Splunk Web versions.
        """
        user, password = web_credentials(self.target, self.environ)
        log.info("Signing in to Splunk Web at %s as %s", self.target.web_url, user)
        page.goto(self.url(LOGIN_PATH), wait_until="domcontentloaded")
        page.fill('input[name="username"]', user)
        page.fill('input[name="password"]', password)
        # Click the form's submit control when there is one; Enter alone does
        # not submit a form that has several fields and no submit control.
        submit = page.locator('form button[type="submit"], form input[type="submit"]')
        if submit.count():
            submit.first.click()
        else:
            page.press('input[name="password"]', "Enter")
        try:
            page.wait_for_url(lambda url: not is_login_url(url))
        except Exception:  # noqa: BLE001 - Playwright's TimeoutError; reported below
            raise UiError(
                "Splunk Web sign-in failed: still on the login page after submitting the form. "
                "Check $%s and $%s, and that the account is not locked out."
                % (self.target.web_user_env, self.target.web_password_env))
        os.makedirs(os.path.dirname(self.state_path), exist_ok=True)
        self.context.storage_state(path=self.state_path)
        log.debug("Cached Splunk Web session in %s", self.state_path)

    def _goto(self, page, url):
        """page.goto, turning a network failure into one clear UiError.

        Playwright raises its own Error with a multi-line call log for a
        refused connection; callers (and the run log) need one line naming
        the address, which is almost always Splunk Web not running.
        """
        try:
            page.goto(url, wait_until="load")
        except Exception as exc:  # noqa: BLE001 - Playwright's Error/TimeoutError
            first = (str(exc).strip().splitlines() or ["unknown error"])[0]
            raise UiError("Could not load %s (%s). Is Splunk Web running at %s?"
                          % (url, first, self.target.web_url))

    def open(self, page, path, ready_selector=None, settle_ms=0):
        """Navigate to a Splunk Web path, signing in first if Splunk asks.

        ``ready_selector`` waits for something the page renders once it is
        usable (a dashboard's panel content, say). Without it, the wait ends
        at the load event, before most dashboard JavaScript has run, so pass
        one whenever the assertion depends on rendered content.
        """
        target_url = self.url(path)
        log.debug("Opening %s", target_url)
        self.page_log(page).clear()
        self._goto(page, target_url)
        if is_login_url(page.url):
            self.login(page)
            # Splunk's return_to redirect already loaded the page once; only
            # errors from the load below should be reported.
            self.page_log(page).clear()
            self._goto(page, target_url)
            if is_login_url(page.url):
                raise UiError("Signed in, but Splunk Web sent %s back to the login page" % path)
        if ready_selector:
            try:
                page.wait_for_selector(ready_selector, state="visible")
            except Exception:  # noqa: BLE001 - Playwright's TimeoutError
                raise UiError("Page %s never showed %r within %ds"
                              % (path, ready_selector, self.timeout_ms // 1000))
        if settle_ms:
            # Splunk renders panels asynchronously after load; a short settle
            # makes screenshots show the finished page, not a spinner.
            page.wait_for_timeout(settle_ms)
        return page

    def open_view(self, page, app, view=None, theme=None, ready_selector=None, settle_ms=0):
        """Open an app's view (optionally forcing a theme). See open()."""
        return self.open(page, view_path(app, view, theme), ready_selector, settle_ms)

    def screenshot(self, page, path, full_page=True):
        """Save a PNG of the page and return its path (the agent can open it to look)."""
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        page.screenshot(path=path, full_page=full_page)
        log.info("Screenshot: %s", paths.display(path))
        return path
