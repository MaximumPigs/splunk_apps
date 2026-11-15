"""Live tests for creating and cloning apps through /services/easyadmin/apps.

The other live tests of this endpoint never create an app: deleting one makes
splunkd ask for a restart, and a test must leave the target as it found it.
Creating an app cannot be proven any other way, so this module deviates
deliberately and narrowly: one module-scoped fixture creates ONE throwaway app
per run (``splktest_ea_<hex>``) and, at teardown, deletes it together with any
left over from an interrupted run, then restarts the target only if splunkd
asks (the dev target may be restarted freely) and waits until a token call
works again. Every other test here is a refusal, which creates nothing.

Observed on 10.6.1 (plan probes, 2026-11-15): creating an app, or objects in
it, does not ask for a restart; deleting one does.
"""

import time
import urllib.parse
import uuid

import pytest

from splk.rest import SplunkError

ENDPOINT = "/services/easyadmin/apps"
PREFIX = "splktest_ea_"


def q(name):
    return urllib.parse.quote(name, safe="")


def post(client, document):
    return client.request("POST", ENDPOINT, json_body=document)


def app_names(client):
    entries = client.request("GET", "/services/apps/local", {"count": 0})["entry"]
    return [entry["name"] for entry in entries]


def app_exists(client, name):
    return name in app_names(client)


def wait_for_token_calls(client, timeout=180):
    """Wait until a token call works: it fails with 401 for ~30 s after splunkd answers again."""
    deadline = time.time() + timeout
    while True:
        try:
            client.request("GET", "/services/authentication/current-context")
            return
        except SplunkError:
            if time.time() >= deadline:
                raise
            time.sleep(3)


def restart_and_wait(client, timeout=300):
    """Restart splunkd and return only once it is a NEW process that accepts tokens.

    SplunkClient.restart() returns as soon as server/info answers, which it
    still does for a few seconds before splunkd goes down (observed: the next
    request was refused). A changed ``startup_time`` proves the restart
    happened; then a token call proves authentication is back.
    """
    before = client.server_info().get("startup_time")
    assert before, "server/info has no startup_time to tell a restart by"
    client.restart()
    deadline = time.time() + timeout
    while True:
        try:
            now = client.server_info().get("startup_time")
            if now != before:
                break
        except SplunkError:
            pass
        if time.time() >= deadline:
            raise AssertionError("splunkd did not restart within %d s" % timeout)
        time.sleep(3)
    wait_for_token_calls(client)


def remove_test_apps(client):
    """Delete every throwaway app; restart the dev target once if splunkd asks."""
    for name in app_names(client):
        if name.startswith(PREFIX):
            try:
                client.request("DELETE", "/services/apps/local/%s" % q(name))
            except SplunkError:
                pass   # reported by the check below
    if client.restart_required():
        restart_and_wait(client)
    leftover = [name for name in app_names(client) if name.startswith(PREFIX)]
    assert not leftover, "throwaway apps are still installed: %s" % leftover


@pytest.fixture(scope="module")
def created(splunk):
    """One app created, with a macro and a dashboard copied into it, in a single apply."""
    remove_test_apps(splunk)   # left over from an interrupted run
    token = uuid.uuid4().hex[:8]
    name = PREFIX + token
    macro = "easyadmin_live_clone_macro_" + token
    view = "easyadmin_live_clone_view_" + token
    splunk.request("POST", "/servicesNS/nobody/search/admin/macros", {"name": macro, "definition": "index=_internal"})
    splunk.request("POST", "/servicesNS/nobody/search/data/ui/views",
                   {"name": view, "eai:data": '<dashboard version="1.1"><label>Clone</label></dashboard>'})
    # Not splunkd's defaults, so a copy that only kept the defaults would differ.
    splunk.request("POST", "/servicesNS/nobody/search/admin/macros/%s/acl" % q(macro),
                   {"sharing": "global", "owner": "nobody", "perms.read": "admin,power", "perms.write": "admin"})
    restart_before = splunk.restart_required()
    try:
        result = post(splunk, {
            "apps": [{"name": name, "label": "Easy Admin Live Test", "visible": False,
                      "description": "Throwaway app made by a live test", "author": "easyadmin live test",
                      "version": "2.3.4"}],
            "changes": [
                {"type": "macro", "ns": "nobody", "app": "search", "name": macro, "copy_to": name},
                {"type": "view", "ns": "nobody", "app": "search", "name": view, "copy_to": name},
            ]})
        yield {"name": name, "macro": macro, "view": view, "result": result, "restart_before": restart_before}
    finally:
        for endpoint, obj in (("admin/macros", macro), ("data/ui/views", view)):
            try:
                splunk.request("DELETE", "/servicesNS/nobody/search/%s/%s" % (endpoint, q(obj)))
            except SplunkError:
                pass
        remove_test_apps(splunk)


def test_the_apply_reports_the_app_and_both_copies(created):
    result = created["result"]
    assert result["apps"] == [{"name": created["name"], "status": "applied",
                               "message": 'Created the app "%s".' % created["name"]}]
    assert [r["status"] for r in result["results"]] == ["applied", "applied"], result
    assert (result["applied"], result["failed"]) == (3, 0)


def test_splunkd_holds_the_app_with_the_fields_given(splunk, created):
    entry = splunk.request("GET", "/services/apps/local/%s" % q(created["name"]))["entry"][0]
    content = entry["content"]
    assert content["label"] == "Easy Admin Live Test"
    assert content["version"] == "2.3.4"
    assert content["description"] == "Throwaway app made by a live test"
    assert content["author"] == "easyadmin live test"
    assert str(content["visible"]).lower() in ("0", "false")


def test_the_copies_are_in_the_new_app_with_the_sources_permissions(splunk, created):
    for endpoint, obj in (("admin/macros", created["macro"]), ("data/ui/views", created["view"])):
        listed = splunk.request("GET", "/servicesNS/-/-/%s" % endpoint, {"count": 0})["entry"]
        in_new = [e for e in listed if e["name"] == obj and e["acl"]["app"] == created["name"]]
        assert len(in_new) == 1, "%s is not listed in %s" % (obj, created["name"])
        in_search = [e for e in listed if e["name"] == obj and e["acl"]["app"] == "search"]
        assert len(in_search) == 1, "the original must stay in search"
    copy = splunk.request("GET", "/servicesNS/nobody/%s/admin/macros/%s" % (q(created["name"]), q(created["macro"])))
    acl = copy["entry"][0]["acl"]
    assert acl["app"] == created["name"] and acl["sharing"] == "global"
    assert set(acl["perms"]["read"]) == {"admin", "power"} and "admin" in acl["perms"]["write"]
    assert copy["entry"][0]["content"]["definition"] == "index=_internal"


def test_the_report_of_a_restart_matches_splunkd(splunk, created):
    # Creating an app asks for no restart on 10.6.1. A restart that was
    # already pending before this run is not ours to blame.
    assert created["result"]["restart_required"] == splunk.restart_required()
    if not created["restart_before"]:
        assert created["result"]["restart_required"] is False


def test_the_model_lists_the_new_app_and_says_who_may_create(splunk, created):
    document = splunk.request("GET", ENDPOINT)
    assert document["can_create_apps"] is True
    listed = [a for a in document["apps"] if a["name"] == created["name"]]
    assert len(listed) == 1 and listed[0]["label"] == "Easy Admin Live Test" and listed[0]["visible"] is False
    assert listed[0]["builtin"] is False and listed[0]["target"] is True


def test_an_existing_name_is_refused_whatever_its_case(splunk, created):
    for name in ("search", "Search", created["name"], created["name"].upper()):
        with pytest.raises(SplunkError) as caught:
            post(splunk, {"apps": [{"name": name, "label": "Duplicate App"}]})
        assert caught.value.status == 400 and "already exists" in str(caught.value), name


@pytest.mark.parametrize("spec, text", [
    ({"name": PREFIX + "bad name", "label": "Bad Name App"}, "not a valid app ID"),
    ({"name": "../" + PREFIX + "x", "label": "Bad Name App"}, "not a valid app ID"),
    ({"name": PREFIX + "short", "label": "abc"}, "at least 5"),
    ({"name": PREFIX + "splunkfor", "label": "Splunk for Things"}, "Splunk for"),
    ({"name": PREFIX + "badver", "label": "Bad Version App", "version": "1 2"}, "not a valid version"),
    # The keys that make apps/local install a package from a path or URL.
    ({"name": PREFIX + "file", "label": "Install App", "filename": "true"}, "not accepted"),
    ({"name": PREFIX + "tmpl", "label": "Template App", "template": "sample_app"}, "not accepted"),
])
def test_invalid_apps_are_refused_and_nothing_is_created(splunk, spec, text):
    before = sorted(app_names(splunk))
    with pytest.raises(SplunkError) as caught:
        post(splunk, {"apps": [spec]})
    assert caught.value.status == 400 and text in str(caught.value)
    assert sorted(app_names(splunk)) == before


def test_a_user_without_the_capabilities_cannot_create_an_app(splunk, sandbox):
    user, password = sandbox.create_user(roles=["power"], label="easyadmin_app_create")
    client = splunk.as_user(user, password)
    assert splunk.request("GET", ENDPOINT)["can_create_apps"] is True
    assert client.request("GET", ENDPOINT)["can_create_apps"] is False
    name = PREFIX + "denied"
    with pytest.raises(SplunkError) as caught:
        post(client, {"apps": [{"name": name, "label": "Denied App"}]})
    assert caught.value.status == 403
    assert not app_exists(splunk, name)


def test_a_request_with_nothing_in_it_is_refused(splunk):
    with pytest.raises(SplunkError) as caught:
        post(splunk, {"apps": [], "changes": []})
    assert caught.value.status == 400
