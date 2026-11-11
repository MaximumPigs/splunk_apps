"""Tests for the REST client and the deploy stage against a fake splunkd.

The fake speaks plain HTTP on 127.0.0.1 and records every request, so the
tests assert on exactly what splk sends: paths, methods, form fields, auth.
"""

import json
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from splk import runlog, stages
from splk.config import Target
from splk.rest import SplunkClient, SplunkError


class FakeSplunk(object):
    """State shared by the handler: canned routes and a request log."""

    def __init__(self):
        self.requests = []
        self.routes = {}  # (method, path) -> (status, body dict)

    def route(self, method, path, status=200, body=None):
        self.routes[(method, path)] = (status, body if body is not None else {})


def _handler(fake):
    class Handler(BaseHTTPRequestHandler):
        def _serve(self, method):
            parsed = urllib.parse.urlparse(self.path)
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length).decode("utf-8") if length else ""
            form = urllib.parse.parse_qs(raw) if method == "POST" and "receivers" not in parsed.path else {}
            fake.requests.append({
                "method": method, "path": parsed.path, "query": urllib.parse.parse_qs(parsed.query),
                "form": form, "raw": raw, "auth": self.headers.get("Authorization"),
            })
            status, body = fake.routes.get((method, parsed.path), (404, {"messages": [{"text": "not found"}]}))
            payload = json.dumps(body).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self):
            self._serve("GET")

        def do_POST(self):
            self._serve("POST")

        def log_message(self, *args):
            pass  # Keep pytest output clean.

    return Handler


@pytest.fixture
def fake():
    state = FakeSplunk()
    server = HTTPServer(("127.0.0.1", 0), _handler(state))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    state.target = Target("fake", "127.0.0.1", port=server.server_address[1], scheme="http", token="tok")
    yield state
    server.shutdown()
    server.server_close()


def _entry(content):
    return {"entry": [{"content": content}]}


def test_requests_carry_bearer_token_and_json_mode(fake):
    fake.route("GET", "/services/server/info", body=_entry({"version": "10.6.1"}))
    assert SplunkClient(fake.target).server_info()["version"] == "10.6.1"
    req = fake.requests[0]
    assert req["auth"] == "Bearer tok"
    assert req["query"]["output_mode"] == ["json"]


def test_errors_surface_splunk_messages(fake):
    fake.route("GET", "/services/server/info", status=401, body={"messages": [{"text": "token expired"}]})
    with pytest.raises(SplunkError) as info:
        SplunkClient(fake.target).server_info()
    assert info.value.status == 401
    assert "token expired" in str(info.value)


def test_unreachable_target_is_a_splunk_error():
    target = Target("dead", "127.0.0.1", port=1, scheme="http", token="t")
    with pytest.raises(SplunkError, match="Cannot reach"):
        SplunkClient(target, timeout=2).server_info()


def test_oneshot_prefixes_search_keyword(fake):
    fake.route("POST", "/services/search/jobs", body={"results": [{"a": "1"}]})
    client = SplunkClient(fake.target)
    assert client.oneshot("index=main error") == [{"a": "1"}]
    assert client.oneshot("| makeresults") == [{"a": "1"}]
    sent = [r["form"]["search"][0] for r in fake.requests]
    assert sent == ["search index=main error", "| makeresults"]
    assert fake.requests[0]["form"]["exec_mode"] == ["oneshot"]


def test_install_package_sends_path_and_update(fake):
    fake.route("POST", "/services/apps/local", body={})
    SplunkClient(fake.target).install_package("/opt/pkgs/a-1.0.0.spl")
    form = fake.requests[0]["form"]
    assert form["filename"] == ["true"]
    assert form["name"] == ["/opt/pkgs/a-1.0.0.spl"]
    assert form["update"] == ["true"]


def test_restart_required_reads_message_presence(fake):
    client = SplunkClient(fake.target)
    assert client.restart_required() is False  # 404: no message posted
    fake.route("GET", "/services/messages/restart_required", body=_entry({}))
    assert client.restart_required() is True


def test_submit_event_posts_raw_body(fake):
    fake.route("POST", "/services/receivers/simple", body={})
    SplunkClient(fake.target).submit_event("raw line", index="splk_test", sourcetype="st")
    req = fake.requests[0]
    assert req["raw"] == "raw line"
    assert req["query"]["index"] == ["splk_test"]


# --------------------------------------------------------------------- deploy

@pytest.fixture
def no_runlog(monkeypatch):
    monkeypatch.setattr(runlog, "record", lambda *a, **k: None)


def _deploy_routes(fake, installed_version):
    fake.route("POST", "/services/apps/local", body={})
    fake.route("GET", "/services/apps/local/fillcontinuous", body=_entry({"version": installed_version}))
    fake.route("POST", "/services/apps/local/_reload", body={})


def _version():
    import os
    from splk import paths
    return stages._package_app_module().read_app_version(os.path.join(paths.APPS_DIR, "fillcontinuous"))


def test_deploy_happy_path(fake, no_runlog, tmp_path):
    _deploy_routes(fake, _version())
    package = tmp_path / "fillcontinuous-x.spl"
    package.write_bytes(b"pkg")
    result = stages.deploy("fillcontinuous", str(package), fake.target)
    assert result.ok, result.summary
    paths_hit = [(r["method"], r["path"]) for r in fake.requests]
    assert ("POST", "/services/apps/local/_reload") in paths_hit


def test_deploy_flags_version_that_did_not_change(fake, no_runlog, tmp_path):
    _deploy_routes(fake, "0.0.1")
    result = stages.deploy("fillcontinuous", str(tmp_path / "p.spl"), fake.target)
    assert not result.ok
    assert "expected" in result.summary


def test_deploy_never_restarts_without_flag(fake, no_runlog, tmp_path):
    _deploy_routes(fake, _version())
    fake.route("GET", "/services/messages/restart_required", body=_entry({}))
    fake.target.allow_restart = True
    result = stages.deploy("fillcontinuous", str(tmp_path / "p.spl"), fake.target, restart=False)
    assert not result.ok
    assert "needs a restart" in result.summary
    assert ("POST", "/services/server/control/restart") not in [(r["method"], r["path"]) for r in fake.requests]


def test_deploy_stages_package_for_remote_view(fake, no_runlog, tmp_path):
    _deploy_routes(fake, _version())
    package = tmp_path / "fillcontinuous-x.spl"
    package.write_bytes(b"pkg")
    fake.target.stage_dir = str(tmp_path / "stage")
    fake.target.server_stage_dir = "/tmp/splunk-stage"
    assert stages.deploy("fillcontinuous", str(package), fake.target).ok
    assert (tmp_path / "stage" / "fillcontinuous-x.spl").read_bytes() == b"pkg"
    assert fake.requests[0]["form"]["name"] == ["/tmp/splunk-stage/fillcontinuous-x.spl"]
