"""Every app's version must agree in app.conf and app.manifest.

AppInspect fails check_version_is_valid_semver when they differ, but only
after a full build; this catches it in the unit stage.
"""
import configparser
import json
from pathlib import Path

import pytest

APPS = Path(__file__).resolve().parents[1] / "apps"
APP_DIRS = sorted(p for p in APPS.iterdir() if (p / "default" / "app.conf").is_file())


@pytest.mark.parametrize("app_dir", APP_DIRS, ids=lambda p: p.name)
def test_versions_match_across_conf_and_manifest(app_dir):
    conf = configparser.ConfigParser(interpolation=None, strict=False)
    conf.read(app_dir / "default" / "app.conf", encoding="utf-8")
    versions = {
        "launcher": conf["launcher"]["version"].strip(),
        "id": conf["id"]["version"].strip(),
    }
    manifest = app_dir / "app.manifest"
    if manifest.is_file():
        data = json.loads(manifest.read_text(encoding="utf-8"))
        versions["manifest"] = data["info"]["id"]["version"]
    assert len(set(versions.values())) == 1, versions
