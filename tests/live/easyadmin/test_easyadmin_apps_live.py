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
    assert 'no longer in "search"' in result["results"][0]["message"]


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


# ------------------------------------------------------- request size cap
#
# Splunk Web passed 64 MB bodies to this handler and splunkd allows 2 GB, so
# the handler caps one request itself: 16 MB of body, refused before the
# change list is read. Nothing is written, so no objects are needed.

MAX_REQUEST_BYTES = 16 * 1024 * 1024


def _padded(total):
    head, tail = '{"changes": [], "pad": "', '"}'
    return head + "x" * (total - len(head) - len(tail)) + tail


def _post_raw(splunk, body):
    """POST ``body`` as it is, through the same client path as every other call."""
    return splunk.request("POST", ENDPOINT, json_body=json.loads(body))


def test_a_request_over_16_mb_is_refused_with_413(splunk):
    with pytest.raises(SplunkError) as caught:
        _post_raw(splunk, _padded(MAX_REQUEST_BYTES + 1024))
    assert caught.value.status == 413
    assert "one Apply can send at most 16 MB" in str(caught.value)
    assert "smaller batches" in str(caught.value)


def test_a_request_just_under_the_cap_reaches_the_change_checks(splunk):
    with pytest.raises(SplunkError) as caught:
        _post_raw(splunk, _padded(MAX_REQUEST_BYTES - 1024))
    assert caught.value.status == 400
    assert "no changes to apply" in str(caught.value).lower()


def test_a_real_change_in_an_over_cap_request_is_not_applied(splunk, objects):
    name = objects.macro()
    obj = find(model(splunk), "macro", name)
    body = {"changes": [ref(obj, delete=True)], "pad": "x" * (MAX_REQUEST_BYTES + 1024)}
    with pytest.raises(SplunkError) as caught:
        splunk.request("POST", ENDPOINT, json_body=body)
    assert caught.value.status == 413
    assert find(model(splunk), "macro", name) is not None


# ------------------------------------------------------------------- copying

def _delete_quietly(splunk, path):
    try:
        splunk.request("DELETE", path)
    except SplunkError:
        pass


def test_copy_creates_a_second_object_and_keeps_the_original(splunk, objects):
    name = objects.macro()
    obj = find(model(splunk), "macro", name)
    try:
        result = apply(splunk, [ref(obj, copy_to="launcher")])
        assert result["applied"] == 1, result
        copied = splunk.request("GET", "/servicesNS/nobody/launcher/admin/macros/%s" % q(name))["entry"][0]
        assert copied["content"]["definition"] == "index=_internal"
        assert copied["acl"]["app"] == "launcher"
        assert acl_of(splunk, "nobody", "search", "admin/macros", name)["app"] == "search"
        # A second copy is refused rather than overwriting the first.
        again = apply(splunk, [ref(obj, copy_to="launcher")])
        assert again["failed"] == 1 and 'already exists in "launcher"' in again["results"][0]["message"]
    finally:
        _delete_quietly(splunk, "/servicesNS/nobody/launcher/admin/macros/%s" % q(name))


def test_copy_keeps_sharing_and_a_dashboards_source(splunk, objects):
    name = objects.view()
    splunk.request("POST", "/servicesNS/nobody/search/data/ui/views/%s/acl" % q(name),
                   {"sharing": "global", "owner": "nobody", "perms.read": "*", "perms.write": "admin"})
    obj = find(model(splunk), "view", name)
    try:
        assert apply(splunk, [ref(obj, copy_to="launcher")])["applied"] == 1
        copied = splunk.request("GET", "/servicesNS/nobody/launcher/data/ui/views/%s" % q(name))["entry"][0]
        assert "<label>Live</label>" in copied["content"]["eai:data"]
        assert copied["acl"]["sharing"] == "global"
    finally:
        _delete_quietly(splunk, "/servicesNS/nobody/launcher/data/ui/views/%s" % q(name))


def test_an_object_shipped_in_default_can_be_copied(splunk):
    document = model(splunk)
    shipped = next(o for o in document["objects"]
                   if o["type"] == "macro" and o["app"] == "search" and not o["movable"] and o["copyable"])
    path = "/servicesNS/nobody/launcher/admin/macros/%s" % q(shipped["name"])
    try:
        result = apply(splunk, [ref(shipped, copy_to="launcher")])
        assert result["applied"] == 1, result
        original = splunk.request("GET", "/servicesNS/nobody/search/admin/macros/%s" % q(shipped["name"]))
        copied = splunk.request("GET", path)["entry"][0]
        assert copied["content"]["definition"] == original["entry"][0]["content"]["definition"]
        assert copied["acl"]["app"] == "launcher"
    finally:
        _delete_quietly(splunk, path)


def test_props_objects_and_tags_are_not_offered_for_copying(splunk):
    # splunkd's REST API merges these across apps, so a copy could not be
    # written reliably; the endpoint refuses rather than half-copying.
    document = model(splunk)
    source = next(o for o in document["objects"] if o["type"] == "extraction")
    assert source["copyable"] is False
    with pytest.raises(SplunkError) as caught:
        apply(splunk, [ref(source, copy_to="launcher")])
    assert caught.value.status == 400 and "cannot be copied" in str(caught.value)


# -------------------------------------------------------- explicit settings

def _details(client, obj):
    return client.request("GET", ENDPOINT, {k: obj[k] for k in ("type", "ns", "app", "name")})


def test_details_list_only_the_settings_set_in_the_object(splunk, objects):
    name = objects.macro()
    details = _details(splunk, find(model(splunk), "macro", name))
    # Created with only a definition: that is all its own stanza holds,
    # however many settings splunkd reports for it.
    assert details["explicit_conf"] == "macros"
    assert [(s["name"], s["value"], s["layer"]) for s in details["explicit"]] == [
        ("definition", "index=_internal", "local")]
    assert len(details["settings"]) > len(details["explicit"])


def test_a_shipped_objects_own_settings_come_from_default(splunk):
    shipped = next(o for o in model(splunk)["objects"]
                   if o["type"] == "macro" and o["app"] == "search" and not o["movable"])
    details = _details(splunk, shipped)
    assert details["explicit"], "a shipped macro sets at least its definition"
    assert {s["layer"] for s in details["explicit"]} <= {"default", "local"}
    assert "definition" in [s["name"] for s in details["explicit"]]


def test_a_private_objects_own_settings_come_from_the_owners_folder(splunk, objects):
    name = objects.macro(owner="admin")
    details = _details(splunk, find(model(splunk), "macro", name))
    assert [(s["name"], s["layer"]) for s in details["explicit"]] == [("definition", "user")]


def test_without_admin_all_objects_the_full_list_is_returned(splunk, sandbox, objects):
    name = objects.macro()
    user, password = sandbox.create_user(roles=["user"], label="easyadmin_explicit_ro")
    client = splunk.as_user(user, password)
    details = _details(client, find(model(client), "macro", name))
    assert details["explicit"] is None and details["explicit_note"] == "capability"
    assert details["settings"]


def test_shipped_reports_are_not_offered_as_movable(splunk):
    # A saved search in a default folder still lists move and remove links,
    # but splunkd refuses the move ("cannot be deleted and thus it cannot be
    # moved"); the model must not offer it. Seen with the search app's
    # "Bucket Merge Retrieve Conf Settings".
    shipped = [o for o in model(splunk)["objects"] if o["type"] == "savedsearch" and o["app"] == "search"]
    assert shipped, "the search app ships saved searches"
    entry = splunk.request("GET", "/servicesNS/nobody/search/saved/searches/%s" % q(shipped[0]["name"]))["entry"][0]
    if not entry["acl"].get("removable"):
        assert "move" in entry["links"]   # the misleading link is still there
        assert shipped[0]["movable"] is False and shipped[0]["removable"] is False
        assert shipped[0]["copyable"] is True


def test_details_and_precedence_do_not_read_the_theme_preference(splunk, sandbox, objects, search):
    # The capability check behind the details panel and the precedence view
    # needs current-context only. Reading the theme (user-prefs) as well cost
    # a second splunkd request per click, so splunkd's own access log must
    # show current-context for this user and never user-prefs. The model GET
    # does read the theme, so this sandbox user must never call it: the
    # object is found with the admin client.
    #
    # An absent line proves nothing while the log is still being indexed (it
    # lags the request by seconds), so the absence is only checked after a
    # marker request made afterwards is searchable. splunkd writes an access
    # line when a request finishes, so any user-prefs call the handler made
    # finished, and was logged, before the marker was sent; splunkd_access.log
    # is indexed in file order, so once the marker is searchable an earlier
    # user-prefs line would be too. (That ordering is observed, and checked
    # below by test_access_log_becomes_searchable_in_request_order.)
    import easyadmin_live_support as ea
    name = objects.macro()
    obj = find(model(splunk), "macro", name)
    user, password = sandbox.create_user(roles=["admin"], label="easyadmin_details_calls")
    client = splunk.as_user(user, password)
    details = _details(client, obj)
    assert details["explicit"] is not None   # the capability check still sees admin_all_objects
    assert client.request("GET", "/services/easyadmin/conf")["confs"]
    context = ea.wait_for_access_rows(search, user, "/services/authentication/current-context*")
    assert context, "no current-context request by %s in splunkd_access within 90s" % user
    marker_rows = ea.wait_for_marker(client, search, user)
    assert marker_rows, "the marker request never reached splunkd_access in 90s"
    prefs = search('search index=_internal sourcetype=splunkd_access user="%s" uri="/servicesNS/*/user-prefs/*"'
                   ' | table _time uri' % user, earliest="-15m", latest="now")
    assert prefs == [], "the theme preference was read: %s" % prefs


def _order_violations(snapshots):
    """Snapshots where the searchable markers are not 1..seen (a later one before an earlier one)."""
    return [s for s in snapshots if s[1] > 0 and not (s[2] == 1 and s[3] == s[1])]


def test_access_log_becomes_searchable_in_request_order(splunk):
    # wait_for_marker relies on splunkd_access lines becoming searchable in the
    # order they were written. Send numbered requests one after another and,
    # after each, list which are searchable: the set must always be 1..k. A
    # gap (a later marker searchable while an earlier one is not) would let the
    # absence check above pass falsely. Observed on 10.6.1, one ingestion pipeline.
    import easyadmin_live_support as ea
    count = 40
    prefix, snapshots = ea.access_log_order_snapshots(splunk, count=count)
    assert snapshots, "the probe returned no snapshots; cannot check the ordering"
    assert _order_violations(snapshots) == [], \
        "markers became searchable out of order (sent, seen, low, top): %s" % _order_violations(snapshots)
    if not any(s[1] > 0 for s in snapshots):
        # Indexing lagged the whole probe: wait for the markers, then check once.
        # Weaker than the per-request check (final set only, no transient gap)
        # and not yet seen to run: every probe so far saw markers.
        deadline = time.time() + 90
        while True:
            rows = splunk.oneshot(
                'search index=_internal sourcetype=splunkd_access uri="*%s_*" | rex field=uri "%s_(?<m>\\d+)"'
                ' | stats dc(m) as seen min(m) as low max(m) as top' % (prefix, prefix),
                earliest="-15m", latest="now")
            seen = int(rows[0].get("seen") or 0) if rows else 0
            if seen or time.time() >= deadline:
                break
            time.sleep(3)
        assert seen, "no marker became searchable within the probe; cannot check the ordering"
        later = [(count, seen, int(rows[0]["low"]), int(rows[0]["top"]))]
        assert _order_violations(later) == [], "markers searchable with a gap: %s" % later


def test_order_check_flags_a_gap():
    # Shows the ordering check can fail: markers 2..3 searchable without 1.
    assert _order_violations([(5, 2, 2, 3)]) == [(5, 2, 2, 3)]
    assert _order_violations([(5, 3, 1, 3), (6, 0, 0, 0)]) == []
