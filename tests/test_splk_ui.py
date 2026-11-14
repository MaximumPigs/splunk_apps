"""Tests for splk's browser layer (tools/splk/ui.py).

The pure helpers run everywhere. The browser tests drive a real Chromium
against a fake Splunk Web (login form, redirect, session cookie, a page that
renders late and logs a console error); they skip where Playwright or its
browser is not installed, which includes CI.
"""

import http.server
import os
import threading
import urllib.parse

import pytest

from splk import cli, config, stages
from splk import ui as splk_ui

USER, PASSWORD = "admin", "changeme-dev"
# A second account, for sessions opened with new_user_page().
OTHER_USER, OTHER_PASSWORD = "viewer", "viewer-dev"


def _target(**overrides):
    spec = dict(name="local", host="localhost", verify_tls=False, web_url="http://127.0.0.1:8000/")
    spec.update(overrides)
    return config.Target(**spec)


# ------------------------------------------------------------------ helpers

def test_web_url_strips_trailing_slash_and_adds_locale():
    assert splk_ui.web_url(_target(), "/app/x/") == "http://127.0.0.1:8000/en-US/app/x/"
    assert splk_ui.web_url(_target(web_locale="de-DE"), "account/login") == \
        "http://127.0.0.1:8000/de-DE/account/login"


def test_view_path_quotes_and_adds_theme():
    assert splk_ui.view_path("easyadmin") == "/app/easyadmin/"
    assert splk_ui.view_path("easyadmin", "role_management", "dark") == \
        "/app/easyadmin/role_management?theme=dark"
    assert splk_ui.view_path("a b", "c/d") == "/app/a%20b/c%2Fd"


def test_parse_page_spec():
    assert splk_ui.parse_page_spec("easyadmin") == (None, "easyadmin", None)
    assert splk_ui.parse_page_spec("easyadmin/role_management") == (None, "easyadmin", "role_management")
    assert splk_ui.parse_page_spec("/manager/launcher/apps/local") == ("/manager/launcher/apps/local", None, None)
    with pytest.raises(config.ConfigError):
        splk_ui.parse_page_spec("")


def test_is_login_url():
    assert splk_ui.is_login_url("http://h:8000/en-US/account/login?return_to=%2Fen-US%2Fapp%2Fx")
    assert not splk_ui.is_login_url("http://h:8000/en-US/app/launcher/home")


def test_credentials_name_missing_variables_but_never_values():
    target = _target()
    with pytest.raises(config.ConfigError) as err:
        splk_ui.web_credentials(target, environ={"SPLUNK_WEB_USERNAME": "admin"})
    assert "$SPLUNK_WEB_PASSWORD" in str(err.value) and "admin" not in str(err.value)
    env = {"SPLUNK_WEB_USERNAME": USER, "SPLUNK_WEB_PASSWORD": PASSWORD}
    assert splk_ui.web_credentials(target, environ=env) == (USER, PASSWORD)


def test_target_without_web_url_is_a_config_error():
    with pytest.raises(config.ConfigError):
        splk_ui.require_web(_target(web_url=None))


def test_repo_target_declares_splunk_web():
    target = config.resolve_target(require_token=False, environ={})
    assert target.web_url == "http://localhost:8000"


def test_slug():
    assert splk_ui.slug("/manager/launcher/apps local") == "manager-launcher-apps-local"
    assert splk_ui.slug("test_x[dark]") == "test_x-dark"


def test_ui_stage_passes_when_app_has_no_ui_tests(tmp_path, monkeypatch):
    monkeypatch.setattr(stages.paths, "UI_TESTS_DIR", str(tmp_path))
    monkeypatch.setattr(stages.runlog, "record", lambda *a, **k: None)
    result = stages.ui_tests("noapp", _target())
    assert result.ok and "no UI tests" in result.summary


def test_ui_stage_needs_web_url(tmp_path, monkeypatch):
    (tmp_path / "someapp").mkdir()
    monkeypatch.setattr(stages.paths, "UI_TESTS_DIR", str(tmp_path))
    monkeypatch.setattr(stages.runlog, "record", lambda *a, **k: None)
    monkeypatch.setattr(stages.importlib.util, "find_spec", lambda name: object())
    result = stages.ui_tests("someapp", _target(web_url=None))
    assert not result.ok and "web_url" in result.summary


def test_cli_parses_ui_options():
    args = cli.build_parser().parse_args(["shot", "easyadmin/role_management", "--theme", "dark", "--headed"])
    assert (args.page, args.theme, args.headed, args.func) == (
        "easyadmin/role_management", "dark", True, cli.cmd_shot)
    args = cli.build_parser().parse_args(["test", "--ui", "easyadmin"])
    assert args.ui and args.app == ["easyadmin"]


def test_review_is_recorded_in_the_run_log(tmp_path, monkeypatch):
    """`splk review` writes a stage entry the Stop hook and retro can read."""
    from splk import runlog
    monkeypatch.setattr(runlog.paths, "RUNS_DIR", str(tmp_path))
    monkeypatch.setattr(cli, "setup_logging", lambda verbose=False: __import__("logging").getLogger("t"))
    assert cli.main(["review", "security", "easyadmin", "fail", "--summary", "1 high",
                     "--detail", "[HIGH] x.py:1 y"]) == 0
    assert cli.main(["review", "security", "easyadmin", "pass", "--summary", "clean"]) == 0
    entries = runlog.read_since(0, runs_dir=str(tmp_path))
    assert [(e["stage"], e["app"], e["ok"]) for e in entries] == [
        ("security", "easyadmin", False), ("security", "easyadmin", True)]
    assert entries[0]["details"] == ["[HIGH] x.py:1 y"]
    # A failed review later passed is a fixed failure, so retro picks it up.
    assert [key for key, _, _ in runlog.fixed_failures(entries)] == [("easyadmin", "security")]


# --------------------------------------------------- browser vs fake Splunk Web

LOGIN_PAGE = """<html><body><form method="post" action="/en-US/account/login">
<input type="hidden" name="return_to" value="{return_to}">
<input type="text" name="username"><input type="password" name="password">
<input type="submit" value="Sign In"></form><p class="error">{error}</p></body></html>"""

VIEW_PAGE = """<html><head><title>Fake view</title></head><body><div id="root">Loading</div>
<script>
  console.error("fake console error");
  setTimeout(function () { document.getElementById("root").innerHTML = "<table class='ready'><tr><td>rendered</td></tr></table>"; }, 300);
</script></body></html>"""


class FakeSplunkWeb(http.server.BaseHTTPRequestHandler):
    """Just enough of Splunk Web: redirect to login, form sign-in, session cookie."""

    logins = 0

    def log_message(self, *args):  # Keep test output quiet.
        pass

    def _send(self, status, body="", headers=None):
        self.send_response(status)
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/en-US/account/login":
            query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            return self._send(200, LOGIN_PAGE.format(return_to=query.get("return_to", ["/en-US/app/launcher/home"])[0],
                                                     error=""))
        if "session=ok-" not in (self.headers.get("Cookie") or ""):
            return self._send(303, headers={"Location": "/en-US/account/login?return_to=" +
                                            urllib.parse.quote(self.path, safe="")})
        return self._send(200, VIEW_PAGE)

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        form = urllib.parse.parse_qs(self.rfile.read(length).decode("utf-8"))
        accounts = {USER: PASSWORD, OTHER_USER: OTHER_PASSWORD}
        user = (form.get("username") or [""])[0]
        if user in accounts and form.get("password") == [accounts[user]]:
            type(self).logins += 1
            # The cookie names the user, so a test can tell sessions apart.
            return self._send(303, headers={"Location": form.get("return_to", ["/en-US/app/launcher/home"])[0],
                                            "Set-Cookie": "session=ok-%s; Path=/" % user})
        return self._send(200, LOGIN_PAGE.format(return_to="", error="Invalid username or password."))


@pytest.fixture
def fake_web(tmp_path):
    pytest.importorskip("playwright")
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), FakeSplunkWeb)
    FakeSplunkWeb.logins = 0
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield _target(web_url="http://127.0.0.1:%d" % server.server_address[1])
    server.shutdown()


def _open_web(target, tmp_path, password=PASSWORD):
    env = dict(os.environ, SPLUNK_WEB_USERNAME=USER, SPLUNK_WEB_PASSWORD=password)
    web = splk_ui.SplunkWeb(target, headed=False, environ=env, state_dir=str(tmp_path), timeout_ms=5000)
    try:
        return web.__enter__()
    except Exception as exc:  # noqa: BLE001 - no browser binary on this machine
        pytest.skip("Chromium not available: %s" % str(exc).splitlines()[0])


def test_browser_signs_in_caches_session_and_records_errors(fake_web, tmp_path):
    web = _open_web(fake_web, tmp_path)
    try:
        page = web.new_page()
        web.open_view(page, "easyadmin", "role_management", ready_selector="#root table.ready")
        assert page.title() == "Fake view"
        assert web.page_log(page).console_errors == ["fake console error"]
        shot = web.screenshot(page, str(tmp_path / "shots" / "view.png"))
        assert os.path.getsize(shot) > 0
        assert os.path.isfile(splk_ui.state_file(fake_web, str(tmp_path)))
    finally:
        web.__exit__(None, None, None)
    assert FakeSplunkWeb.logins == 1

    # A second session reuses the cached cookies: no new sign-in.
    web = _open_web(fake_web, tmp_path)
    try:
        web.open_view(web.new_page(), "easyadmin", "role_management", ready_selector="#root table.ready")
    finally:
        web.__exit__(None, None, None)
    assert FakeSplunkWeb.logins == 1


def test_browser_reports_wrong_password(fake_web, tmp_path):
    web = _open_web(fake_web, tmp_path, password="wrong")
    try:
        with pytest.raises(splk_ui.UiError) as err:
            web.open_view(web.new_page(), "easyadmin")
        assert "sign-in failed" in str(err.value) and "wrong" not in str(err.value)
    finally:
        web.__exit__(None, None, None)


def test_browser_reports_page_that_never_readies(fake_web, tmp_path):
    web = _open_web(fake_web, tmp_path)
    try:
        with pytest.raises(splk_ui.UiError) as err:
            web.open_view(web.new_page(), "easyadmin", ready_selector="#never")
        assert "#never" in str(err.value)
    finally:
        web.__exit__(None, None, None)


def test_second_user_signs_in_in_the_same_browser_without_touching_the_cache(fake_web, tmp_path):
    """new_user_page() is a separate cookie jar, and never replaces the owner's cached session."""
    web = _open_web(fake_web, tmp_path)
    try:
        web.open_view(web.new_page(), "easyadmin", "role_management", ready_selector="#root table.ready")
        state = splk_ui.state_file(fake_web, str(tmp_path))
        with open(state, encoding="utf-8") as handle:
            cached = handle.read()

        page = web.new_user_page(OTHER_USER, OTHER_PASSWORD)
        web.open_view(page, "easyadmin", "role_management", ready_selector="#root table.ready")
        assert FakeSplunkWeb.logins == 2
        assert [c["value"] for c in page.context.cookies()] == ["ok-" + OTHER_USER]
        assert [c["value"] for c in web.context.cookies()] == ["ok-" + USER]
        with open(state, encoding="utf-8") as handle:
            assert handle.read() == cached

        with pytest.raises(splk_ui.UiError) as err:
            web.new_user_page(OTHER_USER, "wrong")
        assert OTHER_USER in str(err.value) and "wrong" not in str(err.value)
    finally:
        web.__exit__(None, None, None)
