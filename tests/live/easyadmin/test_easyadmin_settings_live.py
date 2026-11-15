"""Live tests for editing the individual settings of a knowledge object.

Everything is made in ``search`` under a ``splktest_`` name and removed again.
The writes go through /services/easyadmin/apps (``settings`` on a change); what
landed is read back from splunkd's own endpoints and from the app's file reader
(``explicit`` in the details), never only from the endpoint's report.

Observed on Splunk 10.6.1 and relied on here: a POST to
``configs/conf-<conf>/<stanza>`` writes only the posted keys into the app's
local file (the owner's folder for a private object), keeps sharing and roles,
and creates the file when the app has none. No REST call removes one setting
from a file, so there is no delete to test: ``test_a_default_backed_setting``
leaves its local key behind by design and is idempotent for that reason.
"""

import json
import time
import urllib.parse

import pytest

from splk.rest import SplunkError

ENDPOINT = "/services/easyadmin/apps"
HOST_APP = "search"


def q(name):
    return urllib.parse.quote(name, safe="")


def model(client):
    return client.request("GET", ENDPOINT)


def find(document, type_id, name, app=HOST_APP):
    found = [o for o in document["objects"] if o["type"] == type_id and o["name"] == name and o["app"] == app]
    return found[0] if found else None


def details_of(client, obj):
    return client.request("GET", ENDPOINT, {k: obj[k] for k in ("type", "ns", "app", "name")})


def own(details):
    return dict((s["name"], s) for s in details["explicit"])


def edit(client, obj, settings, **more):
    change = {"type": obj["type"], "ns": obj["ns"], "app": obj["app"], "name": obj["name"], "settings": settings}
    change.update(more)
    return client.request("POST", ENDPOINT, json_body={"changes": [change]})


def setting(name, value, previous=None):
    return {"name": name, "value": value, "previous": previous}


def acl_of(splunk, ns, app, endpoint, name):
    return splunk.request("GET", "/servicesNS/%s/%s/%s/%s" % (q(ns), q(app), endpoint, q(name)))["entry"][0]["acl"]


@pytest.fixture
def made(splunk):
    """Create throwaway objects in search; delete them afterwards wherever they ended up."""
    cleanup = []

    def unique(kind):
        return "splktest_%s_%d_%d" % (kind, int(time.time() * 1000), len(cleanup))

    def macro(owner="nobody", definition="index=_internal"):
        name = unique("macro")
        splunk.request("POST", "/servicesNS/%s/%s/admin/macros" % (q(owner), HOST_APP),
                       {"name": name, "definition": definition})
        cleanup.append("admin/macros/%s" % q(name))
        return name

    def report(**extra):
        name = unique("report")
        args = {"name": name, "search": "| makeresults"}
        args.update(extra)
        splunk.request("POST", "/servicesNS/nobody/%s/saved/searches" % HOST_APP, args)
        cleanup.append("saved/searches/%s" % q(name))
        return name

    def props(endpoint, **args):
        name = unique("props")
        args["name"] = name
        splunk.request("POST", "/servicesNS/nobody/%s/data/props/%s" % (HOST_APP, endpoint), args)
        return name

    def conf_stanza(conf, stanza, **args):
        args["name"] = stanza
        splunk.request("POST", "/servicesNS/nobody/%s/configs/conf-%s" % (HOST_APP, conf), args)
        cleanup.append("configs/conf-%s/%s" % (conf, q(stanza)))
        return stanza

    def remember(tail):
        cleanup.append(tail)

    yield type("Made", (), {"unique": staticmethod(unique), "macro": staticmethod(macro),
                            "report": staticmethod(report), "props": staticmethod(props),
                            "conf_stanza": staticmethod(conf_stanza), "remember": staticmethod(remember)})
    for tail in cleanup:
        for ns in ("nobody", "admin"):
            try:
                splunk.request("DELETE", "/servicesNS/%s/%s/%s" % (ns, HOST_APP, tail))
            except SplunkError:
                pass


def test_a_macro_is_edited_and_gains_a_setting_from_splunkds_list(splunk, made):
    name = made.macro()
    before = acl_of(splunk, "nobody", HOST_APP, "admin/macros", name)
    details = details_of(splunk, find(model(splunk), "macro", name))
    # Proves the deployed code is the new code: only it returns these keys.
    assert details["editable"] is True and details["edit_layer"] == "local"
    assert "errormsg" in details["addable"] and "definition" not in details["addable"]

    result = edit(splunk, find(model(splunk), "macro", name), [
        setting("definition", "index=_audit", "index=_internal"), setting("errormsg", "splktest message")])
    assert result["applied"] == 1 and result["failed"] == 0, result
    assert result["results"][0]["settings_applied"] is True

    content = splunk.request("GET", "/servicesNS/nobody/%s/admin/macros/%s" % (HOST_APP, q(name)))["entry"][0]["content"]
    assert content["definition"] == "index=_audit" and content["errormsg"] == "splktest message"
    after = own(details_of(splunk, find(model(splunk), "macro", name)))
    assert (after["definition"]["value"], after["definition"]["layer"]) == ("index=_audit", "local")
    assert (after["errormsg"]["value"], after["errormsg"]["layer"]) == ("splktest message", "local")
    assert "errormsg" not in details_of(splunk, find(model(splunk), "macro", name))["addable"]
    now = acl_of(splunk, "nobody", HOST_APP, "admin/macros", name)
    assert (now["sharing"], now["owner"], now["perms"]) == (before["sharing"], before["owner"], before["perms"])


def test_a_private_macro_is_edited_in_the_owners_folder_and_stays_private(splunk, made):
    name = made.macro(owner="admin")
    obj = find(model(splunk), "macro", name)
    assert obj["sharing"] == "user"
    details = details_of(splunk, obj)
    assert details["edit_layer"] == "user"
    result = edit(splunk, obj, [setting("definition", "index=_audit", "index=_internal")])
    assert result["applied"] == 1, result
    after = details_of(splunk, find(model(splunk), "macro", name))
    assert (own(after)["definition"]["value"], own(after)["definition"]["layer"]) == ("index=_audit", "user")
    assert acl_of(splunk, "admin", HOST_APP, "admin/macros", name)["sharing"] == "user"


def test_a_saved_search_takes_a_dispatch_setting_and_a_description(splunk, made):
    name = made.report()
    obj = find(model(splunk), "savedsearch", name)
    details = details_of(splunk, obj)
    # splunkd lists dispatch.* as a wildcard (observed) and description as a name.
    assert any(p.startswith("dispatch") for p in details["addable_patterns"])
    result = edit(splunk, obj, [setting("dispatch.earliest_time", "-2h"), setting("description", "splktest")])
    assert result["applied"] == 1, result
    content = splunk.request("GET", "/servicesNS/nobody/%s/saved/searches/%s" % (HOST_APP, q(name)))["entry"][0]["content"]
    assert content["dispatch.earliest_time"] == "-2h" and content["description"] == "splktest"
    after = own(details_of(splunk, find(model(splunk), "savedsearch", name)))
    assert after["dispatch.earliest_time"]["layer"] == "local"


def test_a_stale_previous_is_refused_and_nothing_is_written(splunk, made):
    name = made.macro()
    obj = find(model(splunk), "macro", name)
    result = edit(splunk, obj, [setting("definition", "index=_audit", "what the page saw earlier")])
    assert result["failed"] == 1 and result["applied"] == 0
    assert "changed since the page loaded" in result["results"][0]["message"]
    assert result["results"][0]["settings_applied"] is False
    content = splunk.request("GET", "/servicesNS/nobody/%s/admin/macros/%s" % (HOST_APP, q(name)))["entry"][0]["content"]
    assert content["definition"] == "index=_internal"


def test_a_name_splunkd_does_not_list_for_a_macro_is_refused(splunk, made):
    name = made.macro()
    obj = find(model(splunk), "macro", name)
    result = edit(splunk, obj, [setting("splktest_unlisted", "x")])
    assert result["failed"] == 1
    assert "not a setting splunkd lists" in result["results"][0]["message"]
    assert "splktest_unlisted" not in own(details_of(splunk, find(model(splunk), "macro", name)))


def test_a_secret_name_and_a_dashboard_are_refused_before_splunkd(splunk, made):
    name = made.macro()
    obj = find(model(splunk), "macro", name)
    with pytest.raises(SplunkError) as caught:
        edit(splunk, obj, [setting("password", "x")])
    assert caught.value.status == 400 and "secret" in str(caught.value)
    view = next(o for o in model(splunk)["objects"] if o["type"] == "view")
    with pytest.raises(SplunkError) as caught:
        edit(splunk, view, [setting("label", "x")])
    assert caught.value.status == 400 and "cannot be edited" in str(caught.value)


def test_a_field_extraction_edits_only_its_own_line(splunk, made):
    stanza = made.unique("sourcetype")
    suffix = made.props("extractions", stanza=stanza, type="EXTRACT", value="(?<splktest_a>\\d+)")
    obj = next(o for o in model(splunk)["objects"] if o["type"] == "extraction" and o["name"].endswith("EXTRACT-" + suffix))
    made.remember("data/props/extractions/%s" % (q(obj["name"])))
    details = details_of(splunk, obj)
    assert details["explicit_conf"] == "props" and details["editable"] is True
    (line,) = details["explicit"]
    assert line["name"] == "EXTRACT-" + suffix and line["value"] == "(?<splktest_a>\\d+)"
    assert details["addable"] == [] and details["free_text"] is False

    result = edit(splunk, obj, [setting(line["name"], "(?<splktest_b>\\w+)", line["value"])])
    assert result["applied"] == 1, result
    assert own(details_of(splunk, obj))[line["name"]]["value"] == "(?<splktest_b>\\w+)"
    entry = splunk.request("GET", "/servicesNS/nobody/%s/data/props/extractions/%s" % (HOST_APP, q(obj["name"])))["entry"][0]
    assert entry["content"]["value"] == "(?<splktest_b>\\w+)"

    # Another key of the same stanza belongs to some other object: refused.
    other = edit(splunk, obj, [setting("EXTRACT-splktest_other", "x")])
    assert other["failed"] == 1 and "belong to other objects" in other["results"][0]["message"]


def test_a_field_alias_is_edited_as_its_whole_line(splunk, made):
    stanza = made.unique("sourcetype")
    suffix = made.props("fieldaliases", stanza=stanza, **{"alias.splktest_a1": "splktest_b1"})
    obj = next(o for o in model(splunk)["objects"] if o["type"] == "fieldalias" and o["name"].endswith("FIELDALIAS-" + suffix))
    made.remember("data/props/fieldaliases/%s" % (q(obj["name"])))
    (line,) = details_of(splunk, obj)["explicit"]
    # The value is the whole line, as the conf file holds it (observed).
    assert line["name"] == "FIELDALIAS-" + suffix and "splktest_a1" in line["value"] and "splktest_b1" in line["value"]
    result = edit(splunk, obj, [setting(line["name"], "splktest_a1 AS splktest_b1 splktest_a2 AS splktest_b2", line["value"])])
    assert result["applied"] == 1, result
    entry = splunk.request("GET", "/servicesNS/nobody/%s/data/props/fieldaliases/%s" % (HOST_APP, q(obj["name"])))["entry"][0]
    content = entry["content"]
    assert "splktest_b1" in content["value"] and "splktest_b2" in content["value"]


def test_a_tag_gets_a_setting_by_free_text(splunk, made):
    stanza = made.conf_stanza("tags", "host=%s" % made.unique("host"), splktest_one="enabled")
    obj = find(model(splunk), "tag", stanza)
    assert obj is not None, "the tag %s is listed by the page" % stanza
    details = details_of(splunk, obj)
    assert details["editable"] is True and details["free_text"] is True
    assert own(details)["splktest_one"]["value"] == "enabled"
    result = edit(splunk, obj, [setting("splktest_two", "enabled")])
    assert result["applied"] == 1, result
    assert own(details_of(splunk, obj))["splktest_two"]["value"] == "enabled"


def test_a_source_type_rename_is_editable_only_when_splunkd_names_its_line(splunk, made):
    try:
        made.props("sourcetype-rename", value="splktest_original")
    except SplunkError as error:
        pytest.skip("splunkd would not create a source type renaming: %s" % error)
    listed = [o for o in model(splunk)["objects"] if o["type"] == "sourcetyperename" and "splktest" in o["name"]]
    assert listed, "the renaming is listed by the page"
    obj = listed[0]
    made.remember("data/props/sourcetype-rename/%s" % (q(obj["name"])))
    raw = splunk.request("GET", "/servicesNS/nobody/%s/data/props/sourcetype-rename/%s" % (HOST_APP, q(obj["name"])))["entry"][0]["content"]
    details = details_of(splunk, obj)
    # Observed here, then asserted: editable exactly when the entry names a stanza and a line.
    assert details["editable"] is bool(raw.get("stanza") and raw.get("attribute"))


def test_a_default_backed_setting_becomes_local_and_keeps_its_permissions(splunk):
    """A report that ships in splunk_instrumentation: writing ``description`` creates the local key.

    No REST call removes it again (observed: "Key deletion is not supported"), so
    the key stays in splunk_instrumentation/local by design. The test writes the
    value it found back, which makes it idempotent.
    """
    document = model(splunk)
    obj = find(document, "savedsearch", "instrumentation.anonymized.eventsByTime", app="splunk_instrumentation")
    if obj is None:
        pytest.skip("splunk_instrumentation does not ship the report")
    before = acl_of(splunk, obj["ns"], obj["app"], "saved/searches", obj["name"])
    current = own(details_of(splunk, obj)).get("description")
    previous = current["value"] if current else None
    try:
        result = edit(splunk, obj, [setting("description", "splktest description", previous)])
        assert result["applied"] == 1, result
        after = own(details_of(splunk, obj))["description"]
        assert (after["value"], after["layer"]) == ("splktest description", "local")
        now = acl_of(splunk, obj["ns"], obj["app"], "saved/searches", obj["name"])
        assert (now["sharing"], now["owner"], now["perms"]) == (before["sharing"], before["owner"], before["perms"])
    finally:
        restore = own(details_of(splunk, obj)).get("description")
        if restore and restore["value"] == "splktest description":
            edit(splunk, obj, [setting("description", previous or "", "splktest description")])
    # The default value is still there to show: the setting overrides it.
    shown = own(details_of(splunk, obj))["description"]
    assert shown["layer"] == "local"


def test_a_multi_line_value_cannot_add_a_stanza_or_a_key(splunk, made):
    name = made.report()
    made.remember("configs/conf-savedsearches/evil")
    obj = find(model(splunk), "savedsearch", name)
    value = "first line\n[evil]\nx = 1"
    result = edit(splunk, obj, [setting("description", value)])
    assert result["applied"] == 1, result
    with pytest.raises(SplunkError) as caught:
        splunk.request("GET", "/servicesNS/nobody/%s/configs/conf-savedsearches/evil" % HOST_APP)
    assert caught.value.status == 404, "a second stanza came out of the value"
    after = own(details_of(splunk, find(model(splunk), "savedsearch", name)))
    assert "x" not in after, "a second key came out of the value"
    # splunkd stores the newlines with continuation backslashes; the value round-trips.
    assert after["description"]["value"].replace("\\\n", "\n").split() == value.split()
    content = splunk.request("GET", "/servicesNS/nobody/%s/saved/searches/%s" % (HOST_APP, q(name)))["entry"][0]["content"]
    assert content["description"] == value


def test_a_user_without_admin_all_objects_cannot_edit(splunk, sandbox, made):
    name = made.macro()
    obj = find(model(splunk), "macro", name)
    user, password = sandbox.create_user(roles=["user"], label="easyadmin_settings_ro")
    client = splunk.as_user(user, password)
    details = details_of(client, find(model(client), "macro", name))
    assert details["editable"] is False and details["edit_note"] == "capability"
    result = edit(client, obj, [setting("definition", "index=_audit", "index=_internal")])
    assert result["failed"] == 1 and "admin_all_objects" in result["results"][0]["message"]
    content = splunk.request("GET", "/servicesNS/nobody/%s/admin/macros/%s" % (HOST_APP, q(name)))["entry"][0]["content"]
    assert content["definition"] == "index=_internal"


def test_a_settings_edit_is_audited_by_name_and_never_by_value(splunk, made, search):
    name = made.macro()
    marker = "splktest_value_%d" % int(time.time())
    edit(splunk, find(model(splunk), "macro", name), [setting("errormsg", marker)])
    spl = 'search index=_internal source=*easyadmin.log "action=settings" "%s" | table _raw' % name
    deadline = time.time() + 90
    rows = []
    while not rows and time.time() < deadline:
        rows = search(spl, earliest="-15m", latest="now")
        if not rows:
            time.sleep(3)
    assert rows, "no easyadmin.log line for the settings edit within 90s"
    line = rows[0]["_raw"]
    assert "action=settings" in line and "errormsg" in line and "user=" in line
    assert marker not in line
    assert json.dumps(name) in line
