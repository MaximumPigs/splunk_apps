#!/usr/bin/env python3
"""Vendor splunklib into an app's lib/ directory.

Usage:
    python scripts/vendor_splunklib.py fillcontinuous
    python scripts/vendor_splunklib.py --all --version 3.0.0

Splunk does not make splunklib available to apps, so every app that uses the
Python SDK must bundle its own copy under <app>/lib/.

The ai/ subpackage is excluded. splunk-sdk 3.0.0 declares
requires_python >= 3.13, but the only 3.13-only syntax in it (match statements)
lives in splunklib/ai/, the LLM integration a search command has no use for.
Nothing outside ai/ imports it, and the remainder parses cleanly on Python 3.9.
Dropping it therefore satisfies AppInspect's check_python_sdk_version, which
wants 3.0.0 or later, while keeping the app working on Splunk's 3.9 LTS runtime.

The vendored result is committed to the repository, so neither CI nor the
packaging step needs network access. Re-run this only to change versions.
"""

import argparse
import hashlib
import io
import os
import re
import shutil
import sys
import tarfile
import tempfile
import urllib.request

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APPS_DIR = os.path.join(REPO_ROOT, "apps")

DEFAULT_VERSION = "3.0.0"
PYPI_JSON = "https://pypi.org/pypi/splunk-sdk/{version}/json"

# Subpackages left out of the vendored copy. See the module docstring: keeping
# ai/ would drag Python 3.10+ syntax into an app that must run on 3.9.
EXCLUDED_SUBPACKAGES = ("ai",)

# The sdist top-level directory has been both "splunk-sdk-2.1.1" and
# "splunk_sdk-3.0.0", so match on the splunklib directory instead of assuming.
_SPLUNKLIB_MEMBER = re.compile(r"^[^/]+/splunklib/")


def resolve_sdist(version):
    """Ask PyPI for the sdist URL and its published SHA-256."""
    import json

    with urllib.request.urlopen(PYPI_JSON.format(version=version), timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    for entry in payload.get("urls", []):
        if entry.get("packagetype") == "sdist":
            digest = (entry.get("digests") or {}).get("sha256")
            if not digest:
                raise SystemExit(
                    "PyPI published no sha256 for splunk-sdk %s; refusing to "
                    "vendor code that cannot be verified." % version
                )
            return entry["url"], digest
    raise SystemExit("PyPI lists no sdist for splunk-sdk %s" % version)


def _is_excluded(name):
    """True when a member belongs to a subpackage we do not ship."""
    remainder = _SPLUNKLIB_MEMBER.sub("", name)
    top = remainder.split("/", 1)[0]
    return top in EXCLUDED_SUBPACKAGES


def download_splunklib(version, workdir):
    url, expected_digest = resolve_sdist(version)
    archive_path = os.path.join(workdir, "splunk-sdk.tar.gz")
    print("Downloading %s" % url)
    urllib.request.urlretrieve(url, archive_path)

    # This code is committed and then ships inside every app, so verify it
    # rather than trusting the transport alone.
    digest = hashlib.sha256()
    with open(archive_path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    actual = digest.hexdigest()
    if actual != expected_digest:
        raise SystemExit(
            "SHA-256 mismatch for %s\n  expected %s\n  got      %s\n"
            "Refusing to vendor it." % (url, expected_digest, actual)
        )
    print("SHA-256 verified: %s" % actual)

    with tarfile.open(archive_path, "r:gz") as archive:
        members = [
            member for member in archive.getmembers()
            if _SPLUNKLIB_MEMBER.match(member.name) and not _is_excluded(member.name)
        ]
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

        root = members[0].name.split("/", 1)[0]

    skipped = ", ".join(EXCLUDED_SUBPACKAGES)
    print("Extracted splunklib from %s (excluding: %s)" % (root, skipped))
    return os.path.join(workdir, root, "splunklib")


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

    # Caches have no business in a shipped app.
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
        handle.write("excluded subpackages: %s\n" % ", ".join(EXCLUDED_SUBPACKAGES))
        handle.write("vendored by scripts/vendor_splunklib.py\n")

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
