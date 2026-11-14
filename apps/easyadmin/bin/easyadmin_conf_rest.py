# coding=utf-8
#
# Copyright 2026 MaximumPigs - https://github.com/maximumpigs
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not
# use this file except in compliance with the License. You may obtain a copy of
# the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under
# the License.

"""REST endpoint behind the configuration precedence view.

Reads .conf files read-only, as ``splunk btool`` does, because splunkd's REST
API returns only merged values (see easyadmin_conf_core). Only these folders
are read, and only files named <conf>.conf in them:

    $SPLUNK_HOME/etc/system/default and local
    $SPLUNK_HOME/etc/apps/<app>/default and local

The conf name is checked against a strict pattern before any path is built,
app directory names come from listing etc/apps (never from the request), and
nothing is ever written. Reading files bypasses splunkd's per-object
permissions, so the core refuses callers without admin_all_objects; the
caller's capabilities come from splunkd with their own session token.

One handler class per script: splunkd refuses a persist script that defines
two (see easyadmin_apps_rest).

Must remain valid on Python 3.9 as well as 3.13.
"""

import io
import json
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from splunk.persistconn.application import PersistentServerConnectionApplication  # noqa: E402

import easyadmin_conf_core as conf_core  # noqa: E402
import easyadmin_core as core  # noqa: E402
import easyadmin_rest as roles_rest  # noqa: E402  (a module, so its handler class stays out of this one)

logger = logging.getLogger("easyadmin")


class ConfFileReader(object):
    """Reads <conf>.conf from each default and local folder, read-only."""

    def __init__(self, splunk_home):
        self._etc = os.path.join(splunk_home, "etc")
        self._etc_real = os.path.realpath(self._etc)

    def _layers(self):
        """(app, layer, folder) for every folder that can hold .conf files."""
        system = os.path.join(self._etc, "system")
        yield conf_core.SYSTEM, "local", os.path.join(system, "local")
        yield conf_core.SYSTEM, "default", os.path.join(system, "default")
        apps = os.path.join(self._etc, "apps")
        try:
            names = os.listdir(apps)
        except OSError:
            names = []
        for name in names:
            # A directory name, never a path: listdir gives no separators,
            # and "." / ".." are not returned.
            for layer in ("local", "default"):
                yield name, layer, os.path.join(apps, name, layer)

    def list_confs(self):
        found = set()
        for _app, _layer, folder in self._layers():
            try:
                entries = os.listdir(folder)
            except OSError:
                continue
            for entry in entries:
                if entry.endswith(".conf"):
                    stem = entry[:-5]
                    if conf_core.CONF_NAME_RE.match(stem):
                        found.add(stem)
        return sorted(found)

    def _inside_etc(self, path):
        """False for a path that a symbolic link takes outside etc/."""
        real = os.path.realpath(path)
        return real == self._etc_real or real.startswith(self._etc_real + os.sep)

    def read_conf(self, conf):
        files = {}
        total = 0
        for app, layer, folder in self._layers():
            path = os.path.join(folder, conf + ".conf")
            try:
                if not os.path.isfile(path):
                    continue
                if not self._inside_etc(path):
                    logger.warning("Skipped %s: it links outside etc/", path)
                    continue
                with io.open(path, encoding="utf-8", errors="replace") as handle:
                    # Read one character past the limit rather than trusting
                    # the size checked earlier: the file may have grown.
                    text = handle.read(conf_core.MAX_FILE_CHARS + 1)
            except (IOError, OSError) as error:
                logger.info("Could not read %s: %s", path, error)
                continue
            if len(text) > conf_core.MAX_FILE_CHARS:
                logger.warning("Skipped %s: longer than %d characters", path, conf_core.MAX_FILE_CHARS)
                continue
            total += len(text)
            if total > conf_core.MAX_TOTAL_CHARS:
                raise core.EasyAdminError("%s.conf is too large across all apps to show (over %d MB)."
                                          % (conf, conf_core.MAX_TOTAL_CHARS // (1024 * 1024)), status=413)
            files[(app, layer)] = text
        return files


class ConfHandler(PersistentServerConnectionApplication):
    """GET lists the conf files, or one conf file's settings with their sources."""

    def __init__(self, command_line, command_arg):
        PersistentServerConnectionApplication.__init__(self)
        roles_rest._configure_logging()

    def handle(self, in_string):
        try:
            if isinstance(in_string, bytes):
                in_string = in_string.decode("utf-8", "replace")
            request = json.loads(in_string)
            session = request.get("session") or {}
            query = {}
            for pair in request.get("query") or []:
                if isinstance(pair, (list, tuple)) and len(pair) == 2:
                    query[pair[0]] = pair[1]
            gateway = roles_rest.SplunkdGateway(session.get("authtoken"))
            context = gateway.current_context()
            context["user"] = session.get("user") or "unknown"
            status, payload = conf_core.handle_request(
                request.get("method"), query, ConfFileReader(os.environ["SPLUNK_HOME"]), context)
        except core.GatewayError as error:
            status, payload = error.status, core.error_payload(str(error))
        except Exception:  # pylint: disable=broad-except
            logger.exception("Unhandled error in configuration precedence endpoint")
            status, payload = 500, core.error_payload(
                "Easy Admin hit an unexpected error. See easyadmin.log on the search head.")
        return {
            "status": status,
            "payload": json.dumps(payload),
            "headers": {"Content-Type": "application/json"},
        }
