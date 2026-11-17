"""Every app's default.meta may be written only by admin and sc_admin.

A role in a write list can change, re-permission or unexport the object for
every user; `power` was once granted on fillcontinuous by mistake. AppInspect
cannot tell a deliberate grant from a careless one, so this catches it in the
unit stage (rules `app-security` and `conf-files`).
"""
import re
from pathlib import Path

import pytest

APPS = Path(__file__).resolve().parents[1] / "apps"
APP_DIRS = sorted(p for p in APPS.iterdir() if (p / "metadata" / "default.meta").is_file())

WRITERS = {"admin", "sc_admin"}

# `[]` is a valid stanza name here (the app itself), which configparser
# rejects, so the file is read line by line.
_STANZA = re.compile(r"^\[(?P<name>[^\]]*)\]\s*$")
_WRITE = re.compile(r"write\s*:\s*\[(?P<roles>[^\]]*)\]")


def write_lists(text):
    """Map stanza name to the set of roles in its `write : [...]`.

    A stanza with an `access` line but no write list maps to an empty set.
    """
    result = {}
    stanza = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = _STANZA.match(line)
        if match:
            stanza = match.group("name")
            continue
        key, _, value = line.partition("=")
        if stanza is not None and key.strip() == "access":
            found = _WRITE.search(value)
            roles = found.group("roles") if found else ""
            result[stanza] = {r.strip() for r in roles.split(",") if r.strip()}
    return result


def test_parser_reads_the_app_stanza_and_spacing():
    text = (
        "# comment\n"
        "[]\n"
        "access = read : [ * ], write : [ admin, sc_admin, power ]\n"
        "export = system\n"
        "[commands]\n"
        "access = read : [*], write : [admin,sc_admin]\n"
        "[views]\n"
        "access = read : [ * ]\n"
    )
    assert write_lists(text) == {
        "": {"admin", "sc_admin", "power"},
        "commands": {"admin", "sc_admin"},
        "views": set(),
    }


@pytest.mark.parametrize("app_dir", APP_DIRS, ids=lambda p: p.name)
def test_only_admin_roles_can_write(app_dir):
    lists = write_lists((app_dir / "metadata" / "default.meta").read_text(encoding="utf-8"))
    extra = {name or "[]": sorted(roles - WRITERS) for name, roles in lists.items() if roles - WRITERS}
    assert not extra, "roles other than admin and sc_admin can write: %s" % extra


@pytest.mark.parametrize("app_dir", APP_DIRS, ids=lambda p: p.name)
def test_admin_write_comes_with_sc_admin(app_dir):
    lists = write_lists((app_dir / "metadata" / "default.meta").read_text(encoding="utf-8"))
    missing = [name or "[]" for name, roles in lists.items() if "admin" in roles and "sc_admin" not in roles]
    assert not missing, "admin without sc_admin (check_kos_are_accessible) in: %s" % missing
