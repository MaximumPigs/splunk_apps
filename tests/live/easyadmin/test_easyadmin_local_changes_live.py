"""Live tests: a shipped object with local changes names the local file that holds them.

Splunk refuses every delete of an object that ships in a default folder, and
no REST call removes only its local layer, so the page offers no delete and
says which file to edit. The report used here, ``instrumentation.anonymized.
eventsByTime`` in ``splunk_instrumentation``, ships in default and keeps a
local key by design (see test_easyadmin_settings_live: no REST call removes a
key again). The refusals pinned below were observed on 10.6.1.1 and are what
the README says.
"""

import urllib.parse

import pytest

from splk.rest import SplunkError

ENDPOINT = "/services/easyadmin/apps"
APP = "splunk_instrumentation"
REPORT = "instrumentation.anonymized.eventsByTime"
LOCAL_FILE = "splunk_instrumentation/local/savedsearches.conf"


def q(name):
    return urllib.parse.quote(name, safe="")


def listed(client, type_id, name, app):
    for obj in client.request("GET", ENDPOINT)["objects"]:
        if (obj["type"], obj["name"], obj["app"]) == (type_id, name, app):
            return obj
    return None


def local_layer(client, obj):
    """What the app's file reader sees in the object's own local stanza."""
    details = client.request("GET", ENDPOINT, {k: obj[k] for k in ("type", "ns", "app", "name")})
    return sorted((s["name"], s["value"]) for s in details["explicit"] if s["layer"] == "local")


@pytest.fixture
def report(splunk):
    obj = listed(splunk, "savedsearch", REPORT, APP)
    if obj is None:
        pytest.skip("splunk_instrumentation does not ship the report")
    # Make sure the local layer exists: post the current description back,
    # which changes nothing but pins the key in local (idempotent).
    entry = splunk.request("GET", "/servicesNS/nobody/%s/saved/searches/%s" % (APP, q(REPORT)))["entry"][0]
    splunk.request("POST", "/servicesNS/nobody/%s/configs/conf-savedsearches/%s" % (APP, q(REPORT)),
                   {"description": entry["content"].get("description") or ""})
    return obj


def test_a_shipped_report_with_local_changes_names_its_local_file(splunk, report):
    obj = listed(splunk, "savedsearch", REPORT, APP)
    assert obj["movable"] is False and obj["removable"] is False
    assert obj["local_file"] == LOCAL_FILE


def test_objects_that_can_be_removed_or_have_no_local_stanza_name_no_file(splunk, objects_macro):
    document = splunk.request("GET", ENDPOINT)
    assert all("local_file" in o for o in document["objects"])
    assert listed(splunk, "macro", objects_macro, "search")["local_file"] is None
    shipped = [o for o in document["objects"]
               if o["type"] == "macro" and o["app"] == "search" and not o["movable"]]
    assert shipped, "the search app ships macros"
    for obj in shipped:
        if not local_layer(splunk, obj):
            assert obj["local_file"] is None
            return
    pytest.skip("every shipped search macro has a local layer on this target")


@pytest.fixture
def objects_macro(splunk):
    name = "splktest_local_changes_%d" % int(__import__("time").time() * 1000)
    splunk.request("POST", "/servicesNS/nobody/search/admin/macros", {"name": name, "definition": "index=_internal"})
    yield name
    try:
        splunk.request("DELETE", "/servicesNS/nobody/search/admin/macros/%s" % q(name))
    except SplunkError:
        pass


def test_an_account_without_admin_all_objects_is_not_told_the_file(splunk, sandbox, report):
    # Reading the files bypasses splunkd's per-object permissions, so the
    # name of the file is only given to callers who may read them.
    user, password = sandbox.create_user(roles=["user"], label="easyadmin_local_ro")
    client = splunk.as_user(user, password)
    obj = listed(client, "savedsearch", REPORT, APP)
    if obj is None:
        pytest.skip("the sandbox user cannot list the report")
    assert obj["local_file"] is None


def test_splunkd_has_no_call_that_removes_only_the_local_layer(splunk, report):
    # Pins the README's claim (10.6.1): the typed endpoint and configs refuse,
    # the properties stanza DELETE answers success but changes nothing.
    before = local_layer(splunk, report)
    assert before, "the report has a local layer"
    for path in ("/servicesNS/nobody/%s/saved/searches/%s" % (APP, q(REPORT)),
                 "/servicesNS/nobody/%s/configs/conf-savedsearches/%s" % (APP, q(REPORT))):
        with pytest.raises(SplunkError) as caught:
            splunk.request("DELETE", path)
        assert caught.value.status == 400 and "cannot be deleted" in (str(caught.value) + str(caught.value.body)), path
        assert local_layer(splunk, report) == before, path
    splunk.request("DELETE", "/servicesNS/nobody/%s/properties/savedsearches/%s" % (APP, q(REPORT)))
    assert local_layer(splunk, report) == before
    assert listed(splunk, "savedsearch", REPORT, APP)["local_file"] == LOCAL_FILE
