#!/usr/bin/env python3
"""Package an app directory into a Splunk .spl archive.

Usage:
    python scripts/package_app.py fillcontinuous
    python scripts/package_app.py --all --outdir dist

The archive is a gzipped tar containing a single top-level directory named for
the app, which is what Splunk and AppInspect expect.

File modes are normalised to 0644 for files and 0755 for directories. Windows
has no Unix permission bits, so a tarball built there would otherwise carry
whatever mode the filesystem invented, and AppInspect rejects world-writable or
needlessly executable files.
"""

import argparse
import io
import os
import re
import sys
import tarfile
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APPS_DIR = os.path.join(REPO_ROOT, "apps")

# Never ship these: build noise, editor droppings, and the runtime-only local/
# directory whose presence fails an AppInspect Cloud submission outright.
EXCLUDED_DIRS = frozenset(["local", "__pycache__", ".git", ".pytest_cache", ".ruff_cache"])
EXCLUDED_FILES = frozenset(["local.meta", ".DS_Store", "Thumbs.db", "desktop.ini"])
EXCLUDED_SUFFIXES = (".pyc", ".pyo", ".swp", ".orig", ".rej")

FILE_MODE = 0o644
DIR_MODE = 0o755


def read_app_version(app_dir):
    """Pull the version out of default/app.conf's [launcher] stanza."""
    app_conf = os.path.join(app_dir, "default", "app.conf")
    if not os.path.isfile(app_conf):
        raise SystemExit("No default/app.conf in %s" % app_dir)

    stanza = None
    launcher_version = None
    id_version = None
    with io.open(app_conf, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            header = re.match(r"^\[(.+)\]$", line)
            if header:
                stanza = header.group(1)
                continue
            match = re.match(r"^version\s*=\s*(\S+)$", line)
            if match:
                if stanza == "launcher":
                    launcher_version = match.group(1)
                elif stanza == "id":
                    id_version = match.group(1)

    if launcher_version is None:
        raise SystemExit("No [launcher] version in %s" % app_conf)
    if id_version is not None and id_version != launcher_version:
        raise SystemExit(
            "Version mismatch in %s: [launcher] says %s but [id] says %s. "
            "AppInspect fails the package when these disagree."
            % (app_conf, launcher_version, id_version)
        )
    return launcher_version


def should_skip(relative_path, name, is_dir):
    parts = relative_path.replace("\\", "/").split("/")
    if any(part in EXCLUDED_DIRS for part in parts):
        return True
    if is_dir:
        return name in EXCLUDED_DIRS
    if name in EXCLUDED_FILES:
        return True
    return name.endswith(EXCLUDED_SUFFIXES)


def collect_members(app_dir):
    """Yield (absolute_path, archive_path, is_dir), sorted for reproducibility."""
    entries = []
    for root, dirs, files in os.walk(app_dir):
        dirs[:] = sorted(d for d in dirs if d not in EXCLUDED_DIRS)
        relative_root = os.path.relpath(root, app_dir)
        relative_root = "" if relative_root == "." else relative_root

        for name in dirs:
            relative = os.path.join(relative_root, name) if relative_root else name
            if not should_skip(relative, name, True):
                entries.append((os.path.join(root, name), relative, True))

        for name in sorted(files):
            relative = os.path.join(relative_root, name) if relative_root else name
            if not should_skip(relative, name, False):
                entries.append((os.path.join(root, name), relative, False))

    entries.sort(key=lambda item: item[1].replace("\\", "/"))
    return entries


def build_package(app_name, outdir, timestamp=None):
    app_dir = os.path.join(APPS_DIR, app_name)
    if not os.path.isdir(app_dir):
        raise SystemExit("No such app: %s" % app_dir)

    version = read_app_version(app_dir)
    if not os.path.isdir(outdir):
        os.makedirs(outdir)

    target = os.path.join(outdir, "%s-%s.spl" % (app_name, version))
    mtime = int(timestamp if timestamp is not None else time.time())

    def normalise(info):
        info.uid = 0
        info.gid = 0
        info.uname = "root"
        info.gname = "root"
        info.mtime = mtime
        info.mode = DIR_MODE if info.isdir() else FILE_MODE
        return info

    with tarfile.open(target, "w:gz") as archive:
        root_info = tarfile.TarInfo(app_name)
        root_info.type = tarfile.DIRTYPE
        archive.addfile(normalise(root_info))

        for absolute, relative, is_dir in collect_members(app_dir):
            arcname = "%s/%s" % (app_name, relative.replace("\\", "/"))
            info = archive.gettarinfo(absolute, arcname=arcname)
            info = normalise(info)
            if is_dir:
                archive.addfile(info)
            else:
                with open(absolute, "rb") as handle:
                    archive.addfile(info, handle)

    return target


def discover_apps():
    if not os.path.isdir(APPS_DIR):
        return []
    return sorted(
        name for name in os.listdir(APPS_DIR)
        if os.path.isfile(os.path.join(APPS_DIR, name, "default", "app.conf"))
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("app", nargs="*", help="app directory name under apps/")
    parser.add_argument("--all", action="store_true", help="package every app")
    parser.add_argument("--outdir", default=os.path.join(REPO_ROOT, "dist"))
    parser.add_argument(
        "--source-date-epoch", type=int, default=None,
        help="fixed mtime for reproducible archives",
    )
    parser.add_argument(
        "--expect-version", default=None,
        help=(
            "fail unless the app declares exactly this version. The release "
            "workflow passes the version from the git tag, so a tag that has "
            "run ahead of app.conf cannot publish a mislabelled package."
        ),
    )
    args = parser.parse_args(argv)

    apps = discover_apps() if args.all else args.app
    if not apps:
        parser.error("name at least one app, or pass --all")

    if args.expect_version is not None and len(apps) != 1:
        parser.error("--expect-version applies to exactly one app")

    for app_name in apps:
        if args.expect_version is not None:
            declared = read_app_version(os.path.join(APPS_DIR, app_name))
            if declared != args.expect_version:
                raise SystemExit(
                    "Version mismatch for %s: expected %s but default/app.conf "
                    "declares %s. Bump app.conf to match the tag, or delete the "
                    "tag and cut it again."
                    % (app_name, args.expect_version, declared)
                )
        path = build_package(app_name, args.outdir, args.source_date_epoch)
        print(path)

    return 0


if __name__ == "__main__":
    sys.exit(main())
