"""Test bootstrap for the app monorepo.

Each app's ``bin`` directory is put on sys.path so its modules import the same
way they do under Splunk, where the script's own directory is importable.

Module names must therefore be unique across apps. The convention in this repo
is to prefix helper modules with the app name, as in ``fillcontinuous_core``.
"""

import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APPS_DIR = os.path.join(REPO_ROOT, "apps")
SCRIPTS_DIR = os.path.join(REPO_ROOT, "scripts")

if os.path.isdir(SCRIPTS_DIR) and SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)


def _register_app_bin_directories():
    if not os.path.isdir(APPS_DIR):
        return
    for app_name in sorted(os.listdir(APPS_DIR)):
        bin_dir = os.path.join(APPS_DIR, app_name, "bin")
        if os.path.isdir(bin_dir) and bin_dir not in sys.path:
            sys.path.insert(0, bin_dir)


_register_app_bin_directories()
