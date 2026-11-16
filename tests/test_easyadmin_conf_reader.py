"""ConfFileReader.read_local: the local file of one app, read-only and confined to etc/."""

import importlib
import os
import sys
import types

import pytest


@pytest.fixture
def conf_rest(monkeypatch):
    """easyadmin_conf_rest with stand-ins for the splunk modules it imports at the top.

    The reader under test never calls them. The stand-ins and the modules
    imported through them are removed again so no other test sees them.
    """
    for name in ("easyadmin_conf_rest", "easyadmin_rest"):
        monkeypatch.delitem(sys.modules, name, raising=False)
    stand_ins = {}
    for name in ("splunk", "splunk.persistconn", "splunk.persistconn.application", "splunk.rest"):
        stand_ins[name] = types.ModuleType(name)
        monkeypatch.setitem(sys.modules, name, stand_ins[name])
    stand_ins["splunk"].__path__ = []
    stand_ins["splunk.persistconn"].__path__ = []
    stand_ins["splunk.persistconn.application"].PersistentServerConnectionApplication = object
    module = importlib.import_module("easyadmin_conf_rest")
    yield module
    for name in ("easyadmin_conf_rest", "easyadmin_rest"):
        sys.modules.pop(name, None)


@pytest.fixture
def reader(conf_rest, tmp_path):
    local = tmp_path / "etc" / "apps" / "myapp" / "local"
    local.mkdir(parents=True)
    (local / "savedsearches.conf").write_text(u"[a]\nx = 1\n", encoding="utf-8")
    system = tmp_path / "etc" / "system" / "local"
    system.mkdir(parents=True)
    (system / "macros.conf").write_text(u"[m]\ny = 2\n", encoding="utf-8")
    (tmp_path / "etc" / "apps" / "other").mkdir()
    (tmp_path / "secret.conf").write_text(u"[s]\nz = 3\n", encoding="utf-8")
    return conf_rest.ConfFileReader(str(tmp_path))


def test_reads_the_local_file_of_an_app_and_of_system(reader):
    assert reader.read_local("savedsearches", "myapp") == u"[a]\nx = 1\n"
    assert reader.read_local("macros", "system") == u"[m]\ny = 2\n"


def test_none_for_a_missing_file_an_unknown_app_or_a_bad_name(reader):
    assert reader.read_local("savedsearches", "other") is None
    assert reader.read_local("savedsearches", "nope") is None
    assert reader.read_local("savedsearches", "..") is None
    assert reader.read_local("../../secret", "myapp") is None
    assert reader.read_local("savedsearches", "../myapp") is None


def test_a_link_out_of_etc_is_not_followed(reader, tmp_path):
    link = tmp_path / "etc" / "apps" / "other" / "local"
    try:
        os.symlink(str(tmp_path), str(link), target_is_directory=True)
    except (OSError, NotImplementedError, AttributeError):
        pytest.skip("symbolic links need a privilege here")
    assert reader.read_local("secret", "other") is None


def test_the_app_listing_is_read_once(reader, conf_rest, monkeypatch):
    calls = []
    real = os.listdir
    monkeypatch.setattr(conf_rest.os, "listdir", lambda p: calls.append(p) or real(p))
    reader.read_local("savedsearches", "myapp")
    reader.read_local("savedsearches", "myapp")
    assert len(calls) == 1
