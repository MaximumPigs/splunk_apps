#!/usr/bin/env python3
"""Vendor axe-core (the accessibility rules engine) into tools/splk/vendor/axe-core/.

`splk ux` injects axe.min.js into Splunk Web pages to scan them for
accessibility problems. It is vendored rather than fetched at run time, the
same way apps vendor splunklib: runs need no network, and the exact engine
that produced a result is the one committed in the repository.

The tarball is checked against the npm registry's sha512 integrity value,
pinned below, before anything is extracted. To upgrade, change VERSION and
INTEGRITY together (from https://registry.npmjs.org/axe-core/<version>) and
run this script; the diff then shows exactly what changed.

Usage::

    python scripts/vendor_axe.py
"""

import base64
import hashlib
import io
import logging
import os
import sys
import tarfile
import urllib.request

log = logging.getLogger("vendor_axe")

# The pinned release. 4.14.0 was published to npm on 2026-10-05.
VERSION = "4.14.0"
INTEGRITY = "sha512-9WTZxEjsZ7b13TH8JPmbV2z8CHbl80/2hm3XPEG4JgNdQLK81IBRXmSxHfMAOkSqQeRxT/0dwNDz2GOm3zzpcQ=="
TARBALL_URL = "https://registry.npmjs.org/axe-core/-/axe-core-%s.tgz" % VERSION

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEST_DIR = os.path.join(REPO_ROOT, "tools", "splk", "vendor", "axe-core")

# Only the files splk needs: the engine and its licence (MPL-2.0 requires the
# licence to travel with the code).
WANTED = {"package/axe.min.js": "axe.min.js", "package/LICENSE": "LICENSE"}


def verify_integrity(data, integrity):
    """Raise ValueError unless ``data`` matches an npm ``sha512-<base64>`` integrity string."""
    algorithm, _, expected = integrity.partition("-")
    if algorithm != "sha512":
        raise ValueError("Unsupported integrity algorithm %r" % algorithm)
    actual = base64.b64encode(hashlib.sha512(data).digest()).decode("ascii")
    if actual != expected:
        raise ValueError("Integrity mismatch: expected %s, got sha512-%s" % (integrity, actual))


def extract(data, dest_dir):
    """Write the WANTED members of the tarball into ``dest_dir``; return the written paths."""
    os.makedirs(dest_dir, exist_ok=True)
    written = []
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
        for member_name, out_name in WANTED.items():
            # extractfile() on a named member never touches the filesystem, so
            # a hostile path inside the archive cannot escape dest_dir.
            member = archive.extractfile(member_name)
            if member is None:
                raise ValueError("%s is missing from the tarball" % member_name)
            out_path = os.path.join(dest_dir, out_name)
            with open(out_path, "wb") as handle:
                handle.write(member.read())
            written.append(out_path)
    # Record the version beside the engine, so splk can report it in results.
    version_path = os.path.join(dest_dir, "VERSION")
    with open(version_path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(VERSION + "\n")
    written.append(version_path)
    return written


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    log.info("Downloading %s", TARBALL_URL)
    with urllib.request.urlopen(TARBALL_URL, timeout=60) as response:
        data = response.read()
    verify_integrity(data, INTEGRITY)
    log.info("Integrity verified (%d bytes)", len(data))
    for path in extract(data, DEST_DIR):
        log.info("Wrote %s", os.path.relpath(path, REPO_ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
