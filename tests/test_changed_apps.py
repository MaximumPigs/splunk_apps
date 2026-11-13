"""Tests for CI's changed-app selection.

The failure that matters is a false "nothing changed": AppInspect would be
skipped for an app that needed it. So every uncertain case must select all.
"""

import json
import subprocess

import pytest

import changed_apps

APPS = ["alpha", "beta", "gamma"]


@pytest.mark.parametrize(
    "paths, expected",
    [
        # One app's file selects only that app.
        (["apps/alpha/default/app.conf"], ["alpha"]),
        # Several apps, deduplicated and sorted.
        (["apps/gamma/bin/x.py", "apps/alpha/README.md", "apps/gamma/default/a.conf"], ["alpha", "gamma"]),
        # Changes outside apps/ that do not affect packaging select nothing.
        (["README.md", "tools/splk/cli.py", "tests/test_x.py", "scripts/vendor_splunklib.py"], []),
        # A deleted app, or a folder that is not an app, is dropped.
        (["apps/removed/default/app.conf", "apps/README.md"], []),
        # Nothing changed at all.
        ([], []),
    ],
)
def test_select_apps_maps_paths_to_apps(paths, expected):
    assert changed_apps.select_apps(paths, APPS) == expected


@pytest.mark.parametrize("shared", sorted(changed_apps.SHARED_PATHS))
def test_shared_file_selects_every_app(shared):
    assert changed_apps.select_apps(["apps/alpha/x", shared], APPS) == APPS


def test_release_workflow_is_not_shared():
    # release.yml does not run on PRs, so editing it must not vet every app.
    assert changed_apps.select_apps([".github/workflows/release.yml"], APPS) == []


def test_resolve_all_flag_ignores_diff():
    def boom(base, head):
        raise AssertionError("diff must not run with --all")

    assert changed_apps.resolve("abc", "def", True, APPS, diff=boom) == APPS


@pytest.mark.parametrize("base", ["", changed_apps.NULL_SHA])
def test_resolve_without_base_selects_every_app(base):
    assert changed_apps.resolve(base, "HEAD", False, APPS, diff=None) == APPS


def test_resolve_falls_back_to_all_when_git_fails():
    def fail(base, head):
        raise subprocess.CalledProcessError(128, ["git"], stderr="fatal: bad object")

    assert changed_apps.resolve("abc", "def", False, APPS, diff=fail) == APPS


def test_resolve_uses_diff():
    assert changed_apps.resolve(
        "abc", "def", False, APPS, diff=lambda b, h: ["apps/beta/default/app.conf"]
    ) == ["beta"]


def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo)] + list(args), check=True, stdout=subprocess.PIPE)


def test_git_changed_paths_uses_merge_base(tmp_path):
    """A PR must not inherit changes that landed on main after it branched."""
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "base.txt").write_text("x", encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "base")
    _git(tmp_path, "checkout", "-q", "-b", "feature")
    (tmp_path / "apps").mkdir()
    (tmp_path / "apps" / "feature.txt").write_text("x", encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "feature")
    _git(tmp_path, "checkout", "-q", "main")
    (tmp_path / "main_only.txt").write_text("x", encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "main moves on")

    assert changed_apps.git_changed_paths("main", "feature", cwd=str(tmp_path)) == ["apps/feature.txt"]


def test_main_prints_json(monkeypatch, capsys, tmp_path):
    for name in ("one", "two"):
        (tmp_path / name / "default").mkdir(parents=True)
        (tmp_path / name / "default" / "app.conf").write_text("", encoding="utf-8")
    monkeypatch.setattr(changed_apps, "APPS_DIR", str(tmp_path))
    assert changed_apps.main(["--all"]) == 0
    assert json.loads(capsys.readouterr().out) == ["one", "two"]
