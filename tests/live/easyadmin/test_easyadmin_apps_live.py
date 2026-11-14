"""Live tests for the App management endpoint (/services/easyadmin/apps).

Each test creates its own macros and dashboards in local/ and deletes them
afterwards, wherever the test left them. Objects are moved between ``search``
and ``launcher``, two apps every Splunk instance has, so no throwaway app is
needed (deleting an app makes splunkd ask for a restart).
"""

import json
import time
import urllib.parse

import pytest

from splk.rest import SplunkError

ENDPOINT = "/services/easyadmin/apps"
APPS = ("search", "launcher")


def q(name):
    return urllib.parse.quote(name, safe="")


def model(client):
    return client.request("GET", ENDPOINT)


def apply(client, changes):
    return client.request("POST", ENDPOINT, json_body={"changes": changes})


def find(document, type_id, name):
    found = [o for o in document["objects"] if o["type"] == type_id and o["name"] == name]
    return found[0] if found else None


def ref(obj, **edits):
    out = {"type": obj["type"], "ns": obj["ns"], "app": obj["app"], "name": obj["name"]}
    out.update(edits)
    return out


def acl_of(splunk, ns, app, endpoint, name):
    return splunk.request("GET", "/servicesNS/%s/%s/%s/%s" % (q(ns), q(app), endpoint, q(name)))["entry"][0]["acl"]


@pytest.fixture
def objects(splunk):
    """Create local macros and views; delete them afterwards from every app and namespace."""
    made = []

    def macro(owner="nobody", app="search"):
        name = "easyadmin_live_%d_%d" % (int(time.time() * 1000), len(made))
        splunk.request("POST", "/servicesNS/%s/%s/admin/macros" % (q(owner), app),
                       {"name": name, "definition": "index=_internal"})
        made.append(("admin/macros", name, owner))
        return name

    def view(app="search"):
        name = "easyadmin_live_view_%d" % int(time.time() * 1000)
        splunk.request("POST", "/servicesNS/nobody/%s/data/ui/views" % app,
                       {"name": name, "eai:data": '<dashboard version="1.1"><label>Live</label></dashboard>'})
        made.append(("data/ui/views", name, "nobody"))
        return name

    yield type("Objects", (), {"macro": staticmethod(macro), "view": staticmethod(view)})

    for endpoint, name, owner in made:
        for ns in {owner, "nobody", "admin"}:
            for app in APPS:
                try:
                    splunk.request("DELETE", "/servicesNS/%s/%s/%s/%s" % (q(ns), app, endpoint, q(name)))
                except SplunkError:
                    pass


def test_model_lists_apps_and_objects_with_what_splunkd_allows(splunk, objects):
    name = objects.macro()
    document = model(splunk)
    names = [a["name"] for a in document["apps"]]
    labels = [a["label"].lower() for a in document["apps"]]
    assert labels == sorted(labels)
    assert {"search", "launcher", "easyadmin"} <= set(names)
    search = next(a for a in document["apps"] if a["name"] == "search")
    # Splunk marks search as core (core=1); the page still shows it with the
    # installed apps, and launcher behind "Show Splunk's built-in apps".
    assert search["builtin"] is False and search["target"] is True
    assert next(a for a in document["apps"] if a["name"] == "launcher")["builtin"] is True
    assert next(a for a in document["apps"] if a["name"] == "easyadmin")["builtin"] is False

    mine = find(document, "macro", name)
    assert mine["app"] == "search" and mine["ns"] == "nobody"
    assert mine["movable"] is True and mine["removable"] is True

    # The app's own navigation ships in default/: locked.
    nav = [o for o in document["objects"] if o["type"] == "nav" and o["app"] == "easyadmin"][0]
    assert nav["movable"] is False and nav["removable"] is False
    assert document["warnings"] == []
    assert "admin" in document["roles"]


def test_model_includes_lookup_files_and_calculated_fields(splunk):
    # The reason the endpoint lists each type itself rather than admin/directory.
    types = {o["type"] for o in model(splunk)["objects"]}
    assert {"lookupfile", "calcfield", "savedsearch", "view", "macro"} <= types


def test_details_return_every_setting(splunk, objects):
    name = objects.macro()
    obj = find(model(splunk), "macro", name)
    details = splunk.request("GET", ENDPOINT, {k: obj[k] for k in ("type", "ns", "app", "name")})
    settings = {s["name"]: s["value"] for s in details["settings"]}
    assert settings["definition"] == "index=_internal"


def test_move_puts_the_object_in_the_other_app(splunk, objects):
    name = objects.macro()
    obj = find(model(splunk), "macro", name)
    result = apply(splunk, [ref(obj, move_to="launcher")])
    assert result["applied"] == 1, result
    assert acl_of(splunk, "nobody", "launcher", "admin/macros", name)["app"] == "launcher"
    assert find(model(splunk), "macro", name)["app"] == "launcher"


def test_move_and_permissions_in_one_change(splunk, objects):
    name = objects.view()
    obj = find(model(splunk), "view", name)
    result = apply(splunk, [ref(obj, move_to="launcher", acl={
        "sharing": "global", "owner": "nobody", "read": ["*"], "write": ["admin", "sc_admin"]})])
    assert result["applied"] == 1, result
    acl = acl_of(splunk, "nobody", "launcher", "data/ui/views", name)
    assert acl["app"] == "launcher" and acl["sharing"] == "global"
    assert set(acl["perms"]["write"]) == {"admin", "sc_admin"}


def test_empty_write_list_clears_write_roles(splunk, objects):
    # An empty perms.write leaves no write roles. splunkd stores it as one
    # empty entry (observed on 10.6.1: write == ['']), which grants nothing;
    # the model drops empty names, so the page shows no write roles.
    name = objects.macro()
    obj = find(model(splunk), "macro", name)
    result = apply(splunk, [ref(obj, acl={"sharing": "app", "owner": "nobody", "read": ["*"], "write": []})])
    assert result["applied"] == 1, result
    perms = acl_of(splunk, "nobody", "search", "admin/macros", name)["perms"]
    assert [role for role in perms.get("write") or [] if role] == []
    assert find(model(splunk), "macro", name)["write"] == []


def test_private_object_is_listed_moved_and_shared(splunk, objects):
    name = objects.macro(owner="admin")
    obj = find(model(splunk), "macro", name)
    assert obj["sharing"] == "user" and obj["ns"] == "admin"
    result = apply(splunk, [ref(obj, move_to="launcher")])
    assert result["applied"] == 1, result
    moved = find(model(splunk), "macro", name)
    assert (moved["app"], moved["sharing"], moved["ns"]) == ("launcher", "user", "admin")
    result = apply(splunk, [ref(moved, acl={"sharing": "app", "owner": "admin", "read": ["*"], "write": ["admin"]})])
    assert result["applied"] == 1, result
    shared = find(model(splunk), "macro", name)
    assert (shared["sharing"], shared["ns"]) == ("app", "nobody")


def test_delete_removes_the_object(splunk, objects):
    name = objects.macro()
    obj = find(model(splunk), "macro", name)
    assert apply(splunk, [ref(obj, delete=True)])["applied"] == 1
    assert find(model(splunk), "macro", name) is None


def test_object_in_default_is_refused_and_left_alone(splunk):
    nav = [o for o in model(splunk)["objects"] if o["type"] == "nav" and o["app"] == "easyadmin"][0]
    result = apply(splunk, [ref(nav, move_to="search")])
    assert result["failed"] == 1
    assert "default folder" in result["results"][0]["message"]
    assert acl_of(splunk, nav["ns"], "easyadmin", "data/ui/nav", nav["name"])["app"] == "easyadmin"


def test_stale_location_is_reported(splunk, objects):
    name = objects.macro()
    obj = find(model(splunk), "macro", name)
    splunk.request("POST", "/servicesNS/nobody/search/admin/macros/%s/move" % q(name),
                   {"app": "launcher", "user": "nobody"})
    result = apply(splunk, [ref(obj, delete=True)])
    assert result["failed"] == 1
    assert "no longer in search" in result["results"][0]["message"]


def test_user_without_rights_cannot_change_others_objects(splunk, sandbox, objects):
    # The endpoint acts with the caller's own session: a plain user cannot
    # delete or move an admin's shared object through it.
    name = objects.macro()
    user, password = sandbox.create_user(roles=["user"], label="easyadmin_apps_ro")
    client = splunk.as_user(user, password)
    obj = find(model(client), "macro", name)
    assert obj is not None
    result = apply(client, [ref(obj, delete=True)])
    assert result["failed"] == 1
    assert find(model(splunk), "macro", name) is not None


def test_invalid_requests_are_rejected_before_splunkd(splunk):
    with pytest.raises(SplunkError) as caught:
        apply(splunk, [{"type": "macro", "ns": "nobody", "app": "search", "name": "x", "move_to": "system"}])
    assert caught.value.status == 400
    with pytest.raises(SplunkError) as caught:
        splunk.request("GET", ENDPOINT, {"type": "../../authorization/roles", "ns": "nobody",
                                         "app": "search", "name": "admin"})
    assert caught.value.status == 400
    # A bare ".." survives URL quoting, so it is refused by name.
    with pytest.raises(SplunkError) as caught:
        apply(splunk, [{"type": "macro", "ns": "nobody", "app": "search", "name": "..", "delete": True}])
    assert caught.value.status == 400 and "not a valid name" in str(caught.value)


def test_form_encoded_changes_are_accepted(splunk, objects):
    name = objects.macro()
    obj = find(model(splunk), "macro", name)
    result = splunk.request("POST", ENDPOINT, {"changes": json.dumps([ref(obj, delete=True)])})
    assert result["applied"] == 1
