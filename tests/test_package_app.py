"""Tests for the packaging script.

These cover the invariants that block a bad release: the version a package
claims, and the contents and file modes of the archive AppInspect will read.
"""

import tarfile

import pytest

import package_app


APP_CONF = """\
[install]
state = enabled
is_configured = false

[package]
id = {name}

[id]
name = {name}
version = {id_version}

[launcher]
author = MaximumPigs
version = {launcher_version}
description = Test fixture.
"""


def _make_app(root, name="demo", launcher_version="1.2.3", id_version=None):
    """Create a minimal app tree and return its directory."""
    app = root / "apps" / name
    (app / "default").mkdir(parents=True)
    (app / "bin").mkdir()
    (app / "default" / "app.conf").write_text(
        APP_CONF.format(
            name=name,
            launcher_version=launcher_version,
            id_version=launcher_version if id_version is None else id_version,
        ),
        encoding="utf-8",
    )
    (app / "bin" / "demo.py").write_text("# demo\n", encoding="utf-8")
    return app


@pytest.fixture
def apps_root(tmp_path, monkeypatch):
    """Point the script at a throwaway apps/ directory."""
    monkeypatch.setattr(package_app, "APPS_DIR", str(tmp_path / "apps"))
    return tmp_path


# ---------------------------------------------------------------------------
# version handling
# ---------------------------------------------------------------------------

def test_read_app_version_returns_the_launcher_version(apps_root):
    app = _make_app(apps_root, launcher_version="2.4.0")
    assert package_app.read_app_version(str(app)) == "2.4.0"


def test_read_app_version_rejects_disagreeing_stanzas(apps_root):
    # AppInspect fails the package when [launcher] and [id] disagree, so the
    # build should stop here rather than produce something that cannot ship.
    app = _make_app(apps_root, launcher_version="1.0.0", id_version="1.0.1")
    with pytest.raises(SystemExit) as excinfo:
        package_app.read_app_version(str(app))
    assert "Version mismatch" in str(excinfo.value)


def test_expect_version_blocks_a_tag_that_ran_ahead_of_app_conf(apps_root):
    # The release workflow passes the git tag's version. Without this guard,
    # tagging v1.0.1 while app.conf still says 1.0.0 would publish a 1.0.0
    # package under a 1.0.1 release.
    _make_app(apps_root, launcher_version="1.0.0")
    with pytest.raises(SystemExit) as excinfo:
        package_app.main([
            "demo", "--outdir", str(apps_root / "dist"), "--expect-version", "1.0.1",
        ])
    message = str(excinfo.value)
    assert "1.0.1" in message and "1.0.0" in message


def test_expect_version_allows_a_matching_tag(apps_root):
    _make_app(apps_root, launcher_version="1.0.0")
    assert package_app.main([
        "demo", "--outdir", str(apps_root / "dist"), "--expect-version", "1.0.0",
    ]) == 0
    assert (apps_root / "dist" / "demo-1.0.0.spl").is_file()


def test_expect_version_refuses_to_span_several_apps(apps_root):
    _make_app(apps_root, name="one")
    _make_app(apps_root, name="two")
    with pytest.raises(SystemExit):
        package_app.main([
            "one", "two", "--outdir", str(apps_root / "dist"),
            "--expect-version", "1.2.3",
        ])


# ---------------------------------------------------------------------------
# archive contents
# ---------------------------------------------------------------------------

def _members(archive_path):
    with tarfile.open(archive_path) as archive:
        return {m.name: m for m in archive.getmembers()}


def test_package_is_rooted_at_a_single_app_directory(apps_root):
    _make_app(apps_root)
    target = package_app.build_package("demo", str(apps_root / "dist"))
    names = _members(target)
    assert "demo" in names and names["demo"].isdir()
    assert all(n == "demo" or n.startswith("demo/") for n in names)


def test_package_excludes_runtime_only_files(apps_root):
    app = _make_app(apps_root)
    (app / "local").mkdir()
    (app / "local" / "app.conf").write_text("[ui]\n", encoding="utf-8")
    (app / "metadata").mkdir()
    (app / "metadata" / "local.meta").write_text("[]\n", encoding="utf-8")
    (app / "metadata" / "default.meta").write_text("[]\n", encoding="utf-8")
    (app / "bin" / "demo.pyc").write_bytes(b"\x00")

    names = _members(package_app.build_package("demo", str(apps_root / "dist")))

    # local/ in a package is an outright AppInspect Cloud failure.
    assert not any("/local/" in n or n.endswith("local.meta") for n in names)
    assert not any(n.endswith(".pyc") for n in names)
    assert "demo/metadata/default.meta" in names


def test_package_normalises_file_modes(apps_root):
    # Windows sets no Unix permission bits, so without normalisation an archive
    # built there carries whatever the filesystem invented, and AppInspect
    # rejects needlessly executable or world-writable files.
    _make_app(apps_root)
    names = _members(package_app.build_package("demo", str(apps_root / "dist")))
    for name, member in names.items():
        expected = 0o755 if member.isdir() else 0o644
        assert member.mode == expected, "%s has mode %o" % (name, member.mode)


def test_package_is_reproducible_given_a_fixed_timestamp(apps_root):
    _make_app(apps_root)
    target = package_app.build_package(
        "demo", str(apps_root / "dist"), timestamp=1767225600
    )
    for member in _members(target).values():
        assert member.mtime == 1767225600
        assert member.uid == 0 and member.gid == 0
