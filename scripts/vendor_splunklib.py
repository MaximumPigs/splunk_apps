#!/usr/bin/env python3
"""Vendor splunklib into an app's lib/ directory.

Usage:
    python scripts/vendor_splunklib.py fillcontinuous
    python scripts/vendor_splunklib.py --all --version 2.1.1

Splunk does not make splunklib available to apps, so every app that uses the
Python SDK must bundle its own copy under <app>/lib/.

The pinned default is 2.1.1 on purpose. splunk-sdk 3.0.0 declares
requires_python >= 3.13, which breaks the moment Splunk falls back to its 3.9
LTS runtime; 2.1.1 supports 3.7 through 3.13. Do not bump this to 3.x without
also dropping 3.9 from python.required in commands.conf.

The vendored result is committed to the repository, so neither CI nor the
packaging step needs network access. Re-run this only to change versions.
"""

import argparse
import io
import os
import shutil
import sys
import tarfile
import tempfile
import urllib.request

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APPS_DIR = os.path.join(REPO_ROOT, "apps")

DEFAULT_VERSION = "2.1.1"
SDIST_URL = "https://files.pythonhosted.org/packages/source/s/splunk-sdk/splunk-sdk-{version}.tar.gz"
PYPI_JSON = "https://pypi.org/pypi/splunk-sdk/{version}/json"


def resolve_sdist_url(version):
    """Ask PyPI for the sdist URL, falling back to the conventional path."""
    import json

    try:
        with urllib.request.urlopen(PYPI_JSON.format(version=version), timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
        for entry in payload.get("urls", []):
            if entry.get("packagetype") == "sdist":
                return entry["url"]
    except Exception as error:  # noqa: BLE001 - fall back rather than fail hard
        print("Could not query PyPI (%s); using the conventional URL." % error)
    return SDIST_URL.format(version=version)


def download_splunklib(version, workdir):
    url = resolve_sdist_url(version)
    archive_path = os.path.join(workdir, "splunk-sdk.tar.gz")
    print("Downloading %s" % url)
    urllib.request.urlretrieve(url, archive_path)

    with tarfile.open(archive_path, "r:gz") as archive:
        prefix = "splunk-sdk-%s/splunklib/" % version
        members = [m for m in archive.getmembers() if m.name.startswith(prefix)]
        if not members:
            raise SystemExit("No splunklib/ inside %s" % url)
        for member in members:
            # Guard against path traversal in the archive.
            target = os.path.normpath(os.path.join(workdir, member.name))
            if not target.startswith(os.path.normpath(workdir) + os.sep):
                raise SystemExit("Refusing unsafe path in archive: %s" % member.name)
        # Python 3.12+ (and later 3.9-3.11 patches) can sanitise members on
        # extraction; 3.14 makes it the default and warns until then.
        extract_kwargs = {}
        if hasattr(tarfile, "data_filter"):
            extract_kwargs["filter"] = "data"
        archive.extractall(workdir, members=members, **extract_kwargs)

    return os.path.join(workdir, "splunk-sdk-%s" % version, "splunklib")


def install_into(app_name, source, version):
    lib_dir = os.path.join(APPS_DIR, app_name, "lib")
    target = os.path.join(lib_dir, "splunklib")

    if not os.path.isdir(os.path.join(APPS_DIR, app_name)):
        raise SystemExit("No such app: %s" % app_name)

    if os.path.isdir(target):
        shutil.rmtree(target)
    if not os.path.isdir(lib_dir):
        os.makedirs(lib_dir)

    shutil.copytree(source, target)

    # Tests and caches have no business in a shipped app.
    for root, dirs, files in os.walk(target):
        for name in list(dirs):
            if name == "__pycache__":
                shutil.rmtree(os.path.join(root, name))
                dirs.remove(name)
        for name in files:
            if name.endswith((".pyc", ".pyo")):
                os.remove(os.path.join(root, name))

    stamp = os.path.join(lib_dir, "SPLUNKLIB_VERSION")
    with io.open(stamp, "w", encoding="utf-8", newline="\n") as handle:
        handle.write("splunk-sdk %s\n" % version)

    print("Vendored splunklib %s into %s" % (version, target))


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
    parser.add_argument("--all", action="store_true", help="vendor into every app")
    parser.add_argument("--version", default=DEFAULT_VERSION)
    args = parser.parse_args(argv)

    apps = discover_apps() if args.all else args.app
    if not apps:
        parser.error("name at least one app, or pass --all")

    workdir = tempfile.mkdtemp(prefix="splunklib-")
    try:
        source = download_splunklib(args.version, workdir)
        for app_name in apps:
            install_into(app_name, source, args.version)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())
