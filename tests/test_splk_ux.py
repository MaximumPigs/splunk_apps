"""Tests for the UX audit (tools/splk/ux.py) behind `splk ux` and the ux stage.

The pure helpers run everywhere. The browser tests drive Chromium against a
fake Splunk Web whose pages have known accessibility problems, an app script
that logs an error, a theme that only switches with ?theme=, and a strict
Content Security Policy like Splunk Web's; they skip where Playwright or its
browser is missing, which includes CI.
"""

import http.server
import json
import logging
import os
import threading
import urllib.parse

import pytest

from splk import cli, config, stages
from splk import ux

log = logging.getLogger("test_splk_ux")

USER, PASSWORD = "admin", "changeme-dev"


# ------------------------------------------------------------------ helpers

def _make_app(tmp_path, app="demo", views=("good", "bad")):
    """An app directory with the given views; returns apps_dir."""
    view_dir = tmp_path / "apps" / app / "default" / "data" / "ui" / "views"
    view_dir.mkdir(parents=True)
    for name in views:
        (view_dir / ("%s.xml" % name)).write_text("<dashboard version=\"1.1\"/>\n")
    return str(tmp_path / "apps")


def _write_config(tmp_path, app, text):
    ui_dir = tmp_path / "ui"
    (ui_dir / app).mkdir(parents=True, exist_ok=True)
    (ui_dir / app / "ux.toml").write_text(text)
    return str(ui_dir)


def test_discover_views_lists_xml_files_sorted(tmp_path):
    apps_dir = _make_app(tmp_path, views=("zeta", "alpha"))
    assert ux.discover_views("demo", apps_dir) == ["alpha", "zeta"]
    assert ux.has_views("demo", apps_dir)
    assert not ux.has_views("missing", apps_dir)


def test_config_defaults_and_view_overrides(tmp_path):
    ui_dir = _write_config(tmp_path, "demo", '[defaults]\nsettle_ms = 10\n'
                                             '[views.good]\nscope = "#root"\nready = "#root p"\n')
    cfg = ux.load_config("demo", ui_dir)
    good = ux.view_settings(cfg, "good")
    assert (good["scope"], good["ready"], good["settle_ms"]) == ("#root", "#root p", 10)
    assert ux.view_settings(cfg, "other")["scope"] == "body"


def test_missing_config_means_defaults(tmp_path):
    assert ux.load_config("demo", str(tmp_path)) == {"defaults": {}, "views": {}, "waive": []}


@pytest.mark.parametrize("text, message", [
    ('[[waive]]\nrule = "color-contrast"\n', "needs both rule and reason"),
    ('[[waive]]\nrule = "x"\nreason = "  "\n', "needs both rule and reason"),
    ('[views.good]\nselector = "#x"\n', "unknown key(s) selector"),
    ('[extra]\n', "unknown section(s) extra"),
])
def test_config_rejects_bad_keys_and_unexplained_waivers(tmp_path, text, message):
    with pytest.raises(ux.UxConfigError) as err:
        ux.load_config("demo", _write_config(tmp_path, "demo", text))
    assert message in str(err.value)


@pytest.mark.parametrize("color, theme", [
    ("rgb(255, 255, 255)", "light"),
    ("rgb(30, 34, 40)", "dark"),
    ("rgba(0, 0, 0, 0)", None),
    ("rgb(17 20 24 / 1)", "dark"),
    ("transparent", None),
    ("rgb(128, 128, 128)", "light"),
])
def test_theme_of_background(color, theme):
    assert ux.theme_of(color) == theme


def _finding(rule="color-contrast", impact="serious", targets=(".a",)):
    return {"rule": rule, "impact": impact, "help": "h", "help_url": "", "targets": list(targets), "example": ""}


def test_flatten_violations_sorts_by_impact_and_joins_targets():
    raw = {"violations": [
        {"id": "minor-rule", "impact": "minor", "help": "m", "nodes": [{"target": [".x"]}]},
        {"id": "image-alt", "impact": "critical", "help": "Images need alt", "helpUrl": "u",
         "nodes": [{"target": ["iframe", "img"], "failureSummary": "Fix any of the following:\n  no alt"}]},
    ]}
    findings = ux.flatten_violations(raw)
    assert [f["rule"] for f in findings] == ["image-alt", "minor-rule"]
    assert findings[0]["targets"] == ["iframe img"]
    assert findings[0]["example"] == "no alt"


def test_waiver_must_cover_every_failing_node():
    waivers = [{"rule": "color-contrast", "target": ".ea-badge", "reason": "r"}]
    assert ux.waiver_for(_finding(targets=[".ea-badge"]), "v", "light", waivers)
    # A new failing element is not hidden by an old, narrower waiver.
    assert ux.waiver_for(_finding(targets=[".ea-badge", ".ea-new"]), "v", "light", waivers) is None
    assert ux.waiver_for(_finding(rule="label"), "v", "light", waivers) is None
    scoped = [{"rule": "color-contrast", "view": "other", "reason": "r"}]
    assert ux.waiver_for(_finding(), "v", "light", scoped) is None
    themed = [{"rule": "color-contrast", "theme": "dark", "reason": "r"}]
    assert ux.waiver_for(_finding(), "v", "light", themed) is None
    assert ux.waiver_for(_finding(), "v", "dark", themed)


def test_own_console_errors_are_the_apps_static_files_only():
    entries = [{"text": "splunk noise", "url": "http://h/en-US/static/js/common.js"},
               {"text": "boom", "url": "http://h/en-US/static/app/demo/demo.js"},
               {"text": "Failed to load /en-US/static/app/demo/missing.css", "url": ""}]
    assert [e["text"] for e in ux.own_console_errors("demo", entries)] == [
        "boom", "Failed to load /en-US/static/app/demo/missing.css"]


def _result(**overrides):
    result = {"view": "v", "theme": "light", "rendered_theme": "light", "screenshot": "/x.png",
              "page_errors": [], "console": [], "violations": []}
    result.update(overrides)
    return result


def test_summarise_blocks_on_serious_errors_and_reports_the_rest():
    results = [
        _result(violations=[_finding(impact="serious"), _finding(rule="region", impact="moderate")]),
        _result(theme="dark", rendered_theme="light", page_errors=["TypeError: x"],
                console=[{"text": "noise", "url": "http://h/static/js/splunk.js"}]),
        _result(view="w", error="Page never showed '#root'"),
        _result(view="s", skipped=True),
    ]
    ok, summary, details = ux.summarise("demo", results, [])
    assert not ok
    assert "2 blocking" not in summary and "3 blocking" in summary
    blocking = details[:3]
    assert any("axe serious color-contrast" in d for d in blocking)
    assert any("uncaught exception: TypeError" in d for d in blocking)
    assert any("never showed" in d for d in blocking)
    notes = details[3:]
    assert any("moderate region" in d for d in notes)
    assert any("the dark theme was not audited" in d for d in notes)
    assert any("skipped" in d for d in notes)
    assert not any("noise" in d for d in details)


def test_summarise_passes_when_serious_findings_are_waived():
    waivers = [{"rule": "color-contrast", "reason": "Splunk's own badge colour"}]
    ok, summary, details = ux.summarise("demo", [_result(violations=[_finding()])], waivers)
    assert ok and "1 waived" in summary
    assert details and "[waived: Splunk's own badge colour]" in details[0]


def test_write_report_lists_every_screenshot(tmp_path):
    results = [_result(screenshot=str(tmp_path / "v-light.png"))]
    json_path, md_path = ux.write_report("demo", results, True, "sum", [], "4.14.0", str(tmp_path / "out"))
    assert json.load(open(json_path, encoding="utf-8"))["axe_version"] == "4.14.0"
    text = open(md_path, encoding="utf-8").read()
    assert "v-light.png" in text and "| v | light | light |" in text


def test_vendored_axe_is_present_and_versioned():
    assert os.path.getsize(ux.AXE_PATH) > 100000
    assert ux.axe_version() == "4.14.0"


def test_vendor_script_checks_integrity():
    import importlib
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts"))
    vendor_axe = importlib.import_module("vendor_axe")
    vendor_axe.verify_integrity(b"abc", "sha512-3a81oZNherrMQXNJriBBMRLm+k6JqX6iCp7u5ktV05ohkpkqJ0/BqDa6PCOj/uu9RU1EI2Q86A4qmslPpUyknw==")
    with pytest.raises(ValueError):
        vendor_axe.verify_integrity(b"abd", "sha512-3a81oZNherrMQXNJriBBMRLm+k6JqX6iCp7u5ktV05ohkpkqJ0/BqDa6PCOj/uu9RU1EI2Q86A4qmslPpUyknw==")


def test_parser_has_ux_command_and_ux_review():
    args = cli.build_parser().parse_args(["ux", "easyadmin", "--view", "role_management", "--theme", "dark"])
    assert (args.app, args.view, args.theme) == ("easyadmin", ["role_management"], "dark")
    args = cli.build_parser().parse_args(["review", "ux", "easyadmin", "pass", "--summary", "ok"])
    assert args.kind == "ux"


def test_ux_stage_skips_apps_without_views(monkeypatch):
    monkeypatch.setattr(stages.ux, "has_views", lambda app: False)
    result = stages.ux_audit("fillcontinuous", config.Target(name="local", host="localhost"))
    assert result.ok and "no views" in result.summary


# ------------------------------------------------------- fake Splunk Web

LOGIN_PAGE = """<html><body><form method="post" action="/en-US/account/login">
<input name="username"><input name="password" type="password">
<button type="submit">Sign in</button></form></body></html>"""

# The app's own script: draws the content, honours ?theme=, and on the "bad"
# view logs an error and throws, the way a broken dashboard script would.
APP_JS = """
const dark = new URLSearchParams(location.search).get("theme") === "dark";
document.body.style.background = dark ? "rgb(30, 34, 40)" : "rgb(255, 255, 255)";
document.body.style.color = dark ? "rgb(230, 233, 237)" : "rgb(26, 28, 32)";
const root = document.getElementById("root");
if (location.pathname.endsWith("/bad")) {
  root.innerHTML = '<img src="x.png"><button></button><p style="color:#bbb;background:#fff">faint</p>';
  console.error("demo script failed");
  setTimeout(() => { throw new Error("demo exploded"); }, 0);
} else {
  root.innerHTML = '<label for="f">Filter</label><input id="f"><button>Save</button>';
}
root.classList.add("ready");
"""

VIEW_PAGE = """<!doctype html><html lang="en"><head><title>Fake view</title></head><body>
<header><img src="splunk-logo.png"></header>
<main><div id="root">Loading...</div></main>
<script src="/en-US/static/app/demo/demo.js"></script></body></html>"""


class FakeSplunkWeb(http.server.BaseHTTPRequestHandler):
    """Login form plus app views behind a session cookie, with a strict CSP."""

    def log_message(self, *args):
        log.debug("fake web: " + args[0], *args[1:])

    def _send(self, status, body="", headers=None, content_type="text/html"):
        payload = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        # Like Splunk Web: no inline or eval'd script, so axe cannot be added
        # as a <script> tag and must go through the debugging protocol.
        self.send_header("Content-Security-Policy", "script-src 'self'")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/en-US/account/login":
            return self._send(200, LOGIN_PAGE)
        if "session=ok" not in (self.headers.get("Cookie") or ""):
            return self._send(303, headers={"Location": "/en-US/account/login?return_to=" +
                                            urllib.parse.quote(self.path, safe="")})
        if path == "/en-US/static/app/demo/demo.js":
            return self._send(200, APP_JS, content_type="application/javascript")
        if path.endswith(".png"):
            return self._send(404, "")
        return self._send(200, VIEW_PAGE)

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        form = urllib.parse.parse_qs(self.rfile.read(length).decode("utf-8"))
        if form.get("username") == [USER] and form.get("password") == [PASSWORD]:
            return self._send(303, headers={"Location": "/en-US/app/launcher/home", "Set-Cookie": "session=ok; Path=/"})
        return self._send(200, LOGIN_PAGE)


@pytest.fixture
def fake_web():
    pytest.importorskip("playwright")
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), FakeSplunkWeb)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield config.Target(name="local", host="localhost", verify_tls=False,
                        web_url="http://127.0.0.1:%d" % server.server_address[1])
    server.shutdown()


def _audit(fake_web, tmp_path, ui_dir, **kwargs):
    env = dict(os.environ, SPLUNK_WEB_USERNAME=USER, SPLUNK_WEB_PASSWORD=PASSWORD)
    try:
        return ux.run_audit("demo", fake_web, apps_dir=_make_app(tmp_path), ui_dir=ui_dir,
                            out_dir=str(tmp_path / "out"), environ=env, state_dir=str(tmp_path / "state"),
                            **kwargs)
    except Exception as exc:  # noqa: BLE001 - no browser binary on this machine
        if "Executable doesn't exist" in str(exc) or "asyncio loop" in str(exc):
            pytest.skip("Chromium not available: %s" % str(exc).splitlines()[0])
        raise


def test_audit_passes_a_clean_view_in_both_themes(fake_web, tmp_path):
    ui_dir = _write_config(tmp_path, "demo", '[defaults]\nscope = "#root"\nready = "#root.ready"\nsettle_ms = 0\n')
    ok, summary, details, report = _audit(fake_web, tmp_path, ui_dir, views=["good"])
    assert ok, details
    data = json.load(open(os.path.join(os.path.dirname(report), "report.json"), encoding="utf-8"))
    drawn = {r["theme"]: r["rendered_theme"] for r in data["results"]}
    assert drawn == {"light": "light", "dark": "dark"}
    for result in data["results"]:
        assert os.path.getsize(result["screenshot"]) > 0
        assert result["violations"] == []


def test_audit_blocks_on_the_bad_view_and_ignores_splunk_chrome(fake_web, tmp_path):
    ui_dir = _write_config(tmp_path, "demo", '[defaults]\nscope = "#root"\nready = "#root.ready"\nsettle_ms = 300\n')
    ok, summary, details, _report = _audit(fake_web, tmp_path, ui_dir, views=["bad"], themes=("light",))
    assert not ok
    text = "\n".join(details)
    # axe ran despite the strict CSP and found the app's problems...
    assert "image-alt" in text and "button-name" in text and "color-contrast" in text
    # ...but not the logo in the page shell, which is outside the scope.
    assert "header" not in text
    assert "uncaught exception" in text and "demo exploded" in text
    assert "console error from the app: demo script failed" in text


def test_audit_reports_a_scope_that_does_not_exist(fake_web, tmp_path):
    ui_dir = _write_config(tmp_path, "demo", '[defaults]\nscope = "#nope"\nready = "#root.ready"\nsettle_ms = 0\n')
    ok, _summary, details, _report = _audit(fake_web, tmp_path, ui_dir, views=["good"], themes=("light",))
    assert not ok and "scope selector '#nope' not found" in details[0]


def test_audit_rejects_config_for_a_view_the_app_lacks(fake_web, tmp_path):
    ui_dir = _write_config(tmp_path, "demo", '[views.renamed]\nscope = "#root"\n')
    with pytest.raises(ux.UxConfigError) as err:
        _audit(fake_web, tmp_path, ui_dir)
    assert "renamed" in str(err.value)


def test_audit_reports_splunk_web_not_running_in_one_line(tmp_path):
    pytest.importorskip("playwright")
    import socket
    # A port that was free a moment ago: nothing listens there.
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    down = config.Target(name="local", host="localhost", web_url="http://127.0.0.1:%d" % port)
    ok, _summary, details, _report = _audit(down, tmp_path, str(tmp_path / "ui"), views=["good"], themes=("light",))
    assert not ok
    assert "Could not load" in details[0] and "Is Splunk Web running" in details[0]
    assert "\n" not in details[0]
