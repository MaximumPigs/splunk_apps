#!/usr/bin/env python3
"""Work out which apps a commit range touched, so CI vets only those.

Usage:
    python scripts/changed_apps.py --base <sha> --head <sha>
    python scripts/changed_apps.py --all

Prints a JSON list of app names on stdout, for a GitHub Actions matrix. Logging
goes to stderr so it never corrupts that output.

Every app is selected when:
  * --all is passed (manual runs), or no usable base commit exists (the first
    push of a new branch reports an all-zero "before" SHA);
  * git cannot diff the range (a force push can orphan the old SHA);
  * a shared file changed that alters how every package is built or judged:
    the packager, this script, the CI workflow, or an AppInspect waiver file.

Otherwise an app is selected when any file under apps/<app>/ changed. An app
deleted in the range is dropped, since there is nothing left to package.
"""

import argparse
import json
import logging
import os
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APPS_DIR = os.path.join(REPO_ROOT, "apps")

LOGGER = logging.getLogger("changed_apps")

# Files outside apps/ whose change can alter every app's package or verdict.
# A packager bug or a new waiver affects apps nobody edited, so all are re-run.
SHARED_PATHS = frozenset([
    "scripts/package_app.py",
    "scripts/changed_apps.py",
    ".github/workflows/ci.yml",
    ".appinspect.expect.yaml",
    ".appinspect.manualcheck.yaml",
    ".appinspect_api.expect.yaml",
])

# git prints this as the "before" SHA of a push that created the branch.
NULL_SHA = "0" * 40


def discover_apps(apps_dir=APPS_DIR):
    """Every directory under apps/ that holds default/app.conf, sorted."""
    if not os.path.isdir(apps_dir):
        return []
    return sorted(
        name for name in os.listdir(apps_dir)
        if os.path.isfile(os.path.join(apps_dir, name, "default", "app.conf"))
    )


def select_apps(changed_paths, all_apps):
    """Pure selection logic: map changed repo paths to the apps to vet.

    Paths are repo-relative with forward slashes, as `git diff --name-only`
    prints them on every platform.
    """
    known = set(all_apps)
    selected = set()
    for path in changed_paths:
        if path in SHARED_PATHS:
            LOGGER.info("Shared file %s changed; selecting every app", path)
            return list(all_apps)
        parts = path.split("/")
        # apps/<name>/<something>: a file directly in apps/ belongs to no app.
        if len(parts) >= 3 and parts[0] == "apps":
            if parts[1] in known:
                selected.add(parts[1])
            else:
                # Deleted or not an app (no default/app.conf): nothing to build.
                LOGGER.debug("Ignoring %s: %s is not a current app", path, parts[1])
    return sorted(selected)


def git_changed_paths(base, head, cwd=REPO_ROOT):
    """Files changed on head since it diverged from base.

    Three dots diff against the merge base, so a PR reports only its own
    changes, not whatever landed on main since it branched.
    """
    command = ["git", "diff", "--name-only", "%s...%s" % (base, head)]
    LOGGER.debug("Running %s", " ".join(command))
    result = subprocess.run(
        command, cwd=cwd, check=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True,
    )
    return [line for line in result.stdout.splitlines() if line]


def resolve(base, head, run_all, all_apps, diff=git_changed_paths):
    """Decide the app list, falling back to every app whenever unsure.

    A false "nothing changed" would skip vetting silently, so every doubtful
    case errs towards running everything.
    """
    if run_all:
        LOGGER.info("--all requested; selecting every app")
        return list(all_apps)
    if not base or base == NULL_SHA:
        LOGGER.info("No base commit to compare against; selecting every app")
        return list(all_apps)
    try:
        changed = diff(base, head)
    except (subprocess.CalledProcessError, OSError) as error:
        stderr = getattr(error, "stderr", "") or ""
        LOGGER.warning(
            "Could not diff %s...%s (%s); selecting every app", base, head, stderr.strip() or error
        )
        return list(all_apps)
    LOGGER.info("%d file(s) changed in %s...%s", len(changed), base, head)
    return select_apps(changed, all_apps)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="", help="commit to compare from (PR base or push 'before')")
    parser.add_argument("--head", default="HEAD", help="commit to compare to")
    parser.add_argument("--all", action="store_true", help="select every app regardless of changes")
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )

    # APPS_DIR is read at call time so tests can point it at a fixture tree.
    all_apps = discover_apps(APPS_DIR)
    if not all_apps:
        LOGGER.error("No apps found under apps/ (expected apps/<name>/default/app.conf)")
        return 1

    apps = resolve(args.base, args.head, args.all, all_apps)
    LOGGER.info("Selected %d of %d app(s): %s", len(apps), len(all_apps), ", ".join(apps) or "none")
    # stdout carries only the JSON, so the workflow can capture it verbatim.
    sys.stdout.write(json.dumps(apps) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
