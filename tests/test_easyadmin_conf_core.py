"""Unit tests for easyadmin_conf_core: .conf parsing and btool-style precedence."""

import pytest

import easyadmin_conf_core as conf

ADMIN = {"capabilities": ["admin_all_objects"], "user": "admin"}


class FakeReader(object):
    def __init__(self, files, confs=("props", "macros", "passwords")):
        self.files = files
        self.confs = list(confs)
        self.read = []

    def list_confs(self):
        return self.confs

    def read_conf(self, name):
        self.read.append(name)
        return dict(self.files)


# ------------------------------------------------------------------ parsing

def test_parse_reads_stanzas_settings_and_comments():
    text = u"﻿# comment\nglobal = 1\n\n[one]\na = 1\n  b=two words  \n# c = 3\n[two]\nx = y = z\n"
    assert conf.parse_conf(text) == [("default", {"global": "1"}), ("one", {"a": "1", "b": "two words"}),
                                     ("two", {"x": "y = z"})]


def test_parse_joins_continued_lines_and_keeps_the_newline():
    text = "[m]\ndefinition = index=a \\\n  OR index=b\nnext = 1\n"
    parsed = dict(conf.parse_conf(text))
    assert parsed["m"]["definition"] == "index=a \n  OR index=b"
    assert parsed["m"]["next"] == "1"


def test_parse_merges_a_repeated_stanza_later_value_winning():
    parsed = dict(conf.parse_conf("[s]\na = 1\nb = 1\n[s]\na = 2\n"))
    assert parsed["s"] == {"a": "2", "b": "1"}


def test_parse_ignores_lines_without_equals_and_empty_headers():
    assert conf.parse_conf("[]\njunk line\na = 1\n") == [("default", {"a": "1"})]


# --------------------------------------------------------------- precedence

def test_precedence_is_system_local_app_locals_app_defaults_system_default():
    order = conf.precedence_order({"search", "Zeta", "alpha", "system"})
    # ASCII: uppercase names sort before lowercase, as Splunk orders them.
    assert order == [("system", "local"), ("Zeta", "local"), ("alpha", "local"), ("search", "local"),
                     ("Zeta", "default"), ("alpha", "default"), ("search", "default"), ("system", "default")]


def test_conflicts_name_the_effective_value_and_what_it_overrides():
    files = {
        ("system", "default"): "[st]\nTRUNCATE = 10000\nSHOULD_LINEMERGE = true\n",
        ("search", "default"): "[st]\nTRUNCATE = 5000\n",
        ("search", "local"): "[st]\nTRUNCATE = 2000\n",
        ("alpha", "default"): "[st]\nTRUNCATE = 9999\nSHOULD_LINEMERGE = true\n",
    }
    result = conf.build_precedence("props", files)
    stanza = result["stanzas"][0]
    assert stanza["name"] == "st" and stanza["conflicts"] == 1
    assert stanza["apps"] == ["alpha", "search", "system"]
    settings = {s["name"]: s for s in stanza["settings"]}
    truncate = settings["TRUNCATE"]
    assert truncate["conflict"] is True
    assert [(s["app"], s["layer"], s["value"], s["effective"]) for s in truncate["sources"]] == [
        ("search", "local", "2000", True),
        ("alpha", "default", "9999", False),
        ("search", "default", "5000", False),
        ("system", "default", "10000", False),
    ]
    # The same value set twice is overridden, not a conflict.
    assert settings["SHOULD_LINEMERGE"]["conflict"] is False
    assert settings["SHOULD_LINEMERGE"]["overridden"] is True
    assert [o["app"] + "/" + o["layer"] for o in result["order"]] == [
        "search/local", "alpha/default", "search/default", "system/default"]


def test_only_conflicting_stanzas_unless_all_are_asked_for():
    files = {("a", "default"): "[same]\nx = 1\n[clash]\ny = 1\n",
             ("b", "default"): "[same]\nx = 1\n[clash]\ny = 2\n[alone]\nz = 1\n"}
    assert [s["name"] for s in conf.build_precedence("props", files)["stanzas"]] == ["clash"]
    everything = conf.build_precedence("props", files, only_conflicts=False)
    assert [s["name"] for s in everything["stanzas"]] == ["alone", "clash", "same"]
    assert everything["conflicting_stanzas"] == 1


def test_default_stanza_is_listed_first():
    files = {("a", "default"): "x = 1\n[b]\ny = 1\n", ("b", "default"): "x = 2\n[b]\ny = 2\n"}
    assert [s["name"] for s in conf.build_precedence("props", files)["stanzas"]] == ["default", "b"]


@pytest.mark.parametrize("attr", ["password", "sslPassword", "pass4SymmKey", "bindDNpassword",
                                  "token", "secret", "api_key", "privateKey", "privKey", "pwd",
                                  "access_key", "encryption_key", "shared_key", "auth_key",
                                  "clientSecret", "sslKeysfilePassword", "credentials",
                                  "scriptSecureArguments"])
def test_secret_values_are_masked_but_still_compared(attr):
    files = {("a", "local"): "[s]\n%s = hunter2\n" % attr, ("b", "default"): "[s]\n%s = other\n" % attr}
    setting = conf.build_precedence("server", files)["stanzas"][0]["settings"][0]
    assert setting["secret"] is True and setting["conflict"] is True
    assert {s["value"] for s in setting["sources"]} == {conf.MASK}


@pytest.mark.parametrize("attr", ["TRUNCATE", "definition", "pass4SymmKey_minLength",
                                  "invalidateSessionTokensOnLogout", "tokenAuth", "keyword",
                                  "skipSearchSessionTokenInvalidationOnLogout", "sourcetype"])
def test_settings_about_secrets_are_not_masked(attr):
    # Their values are flags or numbers an admin needs to see.
    assert not conf.is_secret(attr)


def test_search_time_files_are_marked():
    assert conf.build_precedence("macros", {})["search_time"] is True
    assert conf.build_precedence("props", {})["search_time"] is True
    assert conf.build_precedence("server", {})["search_time"] is False


def test_long_values_are_shortened():
    files = {("a", "local"): "[s]\nv = %s\n" % ("x" * 5000), ("b", "default"): "[s]\nv = y\n"}
    sources = conf.build_precedence("props", files)["stanzas"][0]["settings"][0]["sources"]
    assert len(sources[0]["value"]) == conf.MAX_VALUE_LENGTH


# ------------------------------------------------------------------ requests

def test_list_omits_passwords_conf():
    status, body = conf.handle_request("GET", {}, FakeReader({}), ADMIN)
    assert status == 200 and body["confs"] == ["props", "macros"]


def test_conf_request_returns_precedence():
    reader = FakeReader({("a", "local"): "[s]\nx = 1\n", ("b", "local"): "[s]\nx = 2\n"})
    status, body = conf.handle_request("GET", {"conf": "props"}, reader, ADMIN)
    assert status == 200 and body["conflicting_stanzas"] == 1
    status, body = conf.handle_request("GET", {"conf": "props", "all": "1"}, reader, ADMIN)
    assert status == 200


@pytest.mark.parametrize("name", ["../server", "props.conf", "Props", "", "a/b", "x" * 65, "passwords",
                                  "props\n"])
def test_bad_or_excluded_conf_names_are_refused_before_reading(name):
    reader = FakeReader({})
    status, body = conf.handle_request("GET", {"conf": name}, reader, ADMIN)
    assert status == 400 and reader.read == []


def test_reader_errors_are_returned_with_their_status():
    class TooBig(FakeReader):
        def read_conf(self, name):
            raise conf.EasyAdminError("props.conf is too large", status=413)
    status, body = conf.handle_request("GET", {"conf": "props"}, TooBig({}), ADMIN)
    assert status == 413 and "too large" in body["messages"][0]["text"]


def test_callers_without_admin_all_objects_are_refused():
    reader = FakeReader({})
    status, body = conf.handle_request("GET", {"conf": "props"}, reader, {"capabilities": ["search"]})
    assert status == 403 and reader.read == []
    assert "admin_all_objects" in body["messages"][0]["text"]


def test_only_get_is_allowed():
    assert conf.handle_request("POST", {}, FakeReader({}), ADMIN)[0] == 405
