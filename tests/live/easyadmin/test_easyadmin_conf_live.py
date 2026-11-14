"""Live tests for the configuration precedence endpoint (/services/easyadmin/conf).

The endpoint reads .conf files from disk. These tests create a macro with the
same name, but different definitions, in two apps through splunkd (which
writes each app's local/macros.conf), and check the endpoint reports the
clash in btool's global order. The macros are deleted afterwards.
"""

import time
import urllib.parse

import pytest

from splk.rest import SplunkError

ENDPOINT = "/services/easyadmin/conf"


def q(name):
    return urllib.parse.quote(name, safe="")


@pytest.fixture
def clashing_macro(splunk):
    name = "easyadmin_live_conf_%d" % int(time.time() * 1000)
    made = []
    try:
        for app, definition in (("search", "index=_internal"), ("launcher", "index=_audit")):
            splunk.request("POST", "/servicesNS/nobody/%s/admin/macros" % app,
                           {"name": name, "definition": definition})
            made.append(app)
        yield name
    finally:
        for app in made:
            try:
                splunk.request("DELETE", "/servicesNS/nobody/%s/admin/macros/%s" % (app, q(name)))
            except SplunkError:
                pass


def test_lists_conf_files_but_never_passwords(splunk):
    confs = splunk.request("GET", ENDPOINT)["confs"]
    assert {"props", "transforms", "macros", "savedsearches", "server"} <= set(confs)
    assert "passwords" not in confs


def test_clash_between_two_apps_is_reported_in_precedence_order(splunk, clashing_macro):
    body = splunk.request("GET", ENDPOINT, {"conf": "macros"})
    stanza = next(s for s in body["stanzas"] if s["name"] == clashing_macro)
    assert stanza["conflicts"] == 1
    definition = next(s for s in stanza["settings"] if s["name"] == "definition")
    # Global order: app local folders in ASCII order, so launcher before search.
    assert [(s["app"], s["layer"], s["value"], s["effective"]) for s in definition["sources"]] == [
        ("launcher", "local", "index=_audit", True),
        ("search", "local", "index=_internal", False),
    ]
    # "order" lists only the layers that have this conf file (etc/system has
    # no macros.conf on 10.6.1).
    layers = [o["app"] + "/" + o["layer"] for o in body["order"]]
    assert layers.index("launcher/local") < layers.index("search/local")


def test_without_the_clash_the_stanza_is_only_listed_on_request(splunk, clashing_macro):
    splunk.request("DELETE", "/servicesNS/nobody/launcher/admin/macros/%s" % q(clashing_macro))
    names = [s["name"] for s in splunk.request("GET", ENDPOINT, {"conf": "macros"})["stanzas"]]
    assert clashing_macro not in names
    every = splunk.request("GET", ENDPOINT, {"conf": "macros", "all": "1"})["stanzas"]
    assert clashing_macro in [s["name"] for s in every]


def test_secret_values_are_never_returned(splunk):
    body = splunk.request("GET", ENDPOINT, {"conf": "server", "all": "1"})
    secrets = [st for s in body["stanzas"] for st in s["settings"] if st["secret"]]
    assert secrets, "expected server.conf to set at least one secret (pass4SymmKey, sslPassword...)"
    for setting in secrets:
        assert {src["value"] for src in setting["sources"]} <= {"********", ""}, setting["name"]


@pytest.mark.parametrize("name", ["passwords", "../server", "server.conf"])
def test_bad_or_excluded_names_are_refused(splunk, name):
    with pytest.raises(SplunkError) as caught:
        splunk.request("GET", ENDPOINT, {"conf": name})
    assert caught.value.status == 400


def test_user_without_admin_all_objects_is_refused(splunk, sandbox):
    user, password = sandbox.create_user(roles=["user"], label="easyadmin_conf_ro")
    client = splunk.as_user(user, password)
    with pytest.raises(SplunkError) as caught:
        client.request("GET", ENDPOINT, {"conf": "server"})
    assert caught.value.status == 403
