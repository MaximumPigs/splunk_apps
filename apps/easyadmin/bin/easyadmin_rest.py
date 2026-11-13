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

"""REST endpoint behind the Easy Admin role management page.

A thin wrapper: routing, validation and the matrix logic live in
easyadmin_core, which imports nothing from Splunk so it can be unit tested.
This module only adapts splunkd's persistent-handler protocol and makes the
calls to splunkd.

Every call to splunkd is made with the *calling user's* session token
(restmap.conf leaves passSystemAuth off), so splunkd applies that user's own
capabilities. The app never elevates: someone who cannot edit a role in
Settings cannot edit it here either.

Must remain valid on Python 3.9 as well as 3.13 - see python.required in
default/restmap.conf.
"""

import json
import logging
import logging.handlers
import os
import sys

try:  # Python 3
    from urllib.parse import quote
except ImportError:  # pragma: no cover - Splunk no longer ships Python 2
    from urllib import quote

# splunkd starts persistent handlers with its own working directory, so the
# app's bin/ is not reliably importable until it is added here.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import splunk.rest as splunk_rest  # noqa: E402  (must follow the sys.path setup)
from splunk.persistconn.application import PersistentServerConnectionApplication  # noqa: E402

import easyadmin_core as core  # noqa: E402

logger = logging.getLogger("easyadmin")


def _configure_logging():
    """Log to var/log/splunk/easyadmin.log, which Splunk indexes into _internal.

    That file is the audit trail of role edits made through this app. Failing
    to open it must never take the endpoint down, hence the broad except.
    """
    if logger.handlers:
        return
    logger.setLevel(logging.INFO)
    try:
        path = os.path.join(os.environ["SPLUNK_HOME"], "var", "log", "splunk", "easyadmin.log")
        handler = logging.handlers.RotatingFileHandler(path, maxBytes=5 * 1024 * 1024, backupCount=2)
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
    except Exception:  # pylint: disable=broad-except
        logger.addHandler(logging.NullHandler())


def _error_text(content, fallback):
    """Extract splunkd's human-readable message from a JSON error body."""
    try:
        if isinstance(content, bytes):
            content = content.decode("utf-8", "replace")
        messages = json.loads(content).get("messages") or []
        text = "; ".join(m.get("text", "") for m in messages if isinstance(m, dict))
        return text or fallback
    except (AttributeError, TypeError, ValueError):
        return fallback


class SplunkdGateway(object):
    """The splunkd calls easyadmin_core needs, made as the calling user."""

    def __init__(self, session_key):
        self._session_key = session_key

    def _request(self, path, method="GET", getargs=None, postargs=None):
        getargs = dict(getargs or {})
        getargs["output_mode"] = "json"
        try:
            response, content = splunk_rest.simpleRequest(
                path,
                sessionKey=self._session_key,
                getargs=getargs,
                postargs=postargs,
                method=method,
                raiseAllErrors=False,
            )
        except Exception as error:  # pylint: disable=broad-except
            # simpleRequest raises its own exception types for 401/403/404 and
            # others; they carry statusCode. Anything else is a transport fault.
            status = getattr(error, "statusCode", None) or 502
            raise core.GatewayError(str(error) or error.__class__.__name__, status=int(status))

        status = int(getattr(response, "status", 502))
        if status >= 400:
            raise core.GatewayError(
                _error_text(content, "splunkd returned HTTP %d for %s" % (status, path)),
                status=status,
            )
        if isinstance(content, bytes):
            content = content.decode("utf-8", "replace")
        try:
            return json.loads(content) if content and content.strip() else {}
        except ValueError:
            raise core.GatewayError("splunkd returned a non-JSON response for %s" % path)

    @staticmethod
    def _entries(document):
        return [{"name": entry.get("name"), "content": entry.get("content") or {}}
                for entry in document.get("entry") or []]

    def list_roles(self):
        # count=0 lifts the default page size of 30; the page shows every role.
        return self._entries(self._request("/services/authorization/roles", getargs={"count": 0}))

    def list_indexes(self):
        # datatype=all includes metrics indexes, which the default omits.
        return self._entries(self._request(
            "/services/data/indexes", getargs={"count": 0, "datatype": "all"}))

    def list_capabilities(self):
        # One entry whose content.capabilities lists every capability splunkd
        # defines, including those added by installed apps (249 on 10.6.1).
        entries = self._entries(self._request("/services/authorization/capabilities"))
        return core.as_list(entries[0]["content"].get("capabilities")) if entries else []

    def current_context(self):
        entries = self._entries(self._request("/services/authentication/current-context"))
        if not entries:
            return {}
        content = entries[0]["content"]
        return {"capabilities": core.as_list(content.get("capabilities")),
                "roles": core.as_list(content.get("roles")),
                "theme": self._user_theme(content.get("username"))}

    def _user_theme(self, username):
        """The user's theme preference (user-prefs.conf [general] theme), or None.

        The page only needs this to match Splunk's theme, so any failure to
        read it (no user-prefs for this user, no permission) is not an error:
        the page simply stays in whatever theme Splunk drew.
        """
        if not username:
            return None
        try:
            entries = self._entries(self._request(
                "/servicesNS/%s/user-prefs/data/user-prefs/general" % quote(username, safe="")))
        except core.GatewayError as error:
            logger.info("Could not read theme preference for %s: %s", username, error)
            return None
        return entries[0]["content"].get("theme") if entries else None

    def get_role(self, name):
        try:
            entries = self._entries(self._request(
                "/services/authorization/roles/%s" % quote(name, safe="")))
        except core.GatewayError as error:
            if error.status != 404:
                raise
            # simpleRequest's own 404 text is just the URL it called.
            entries = []
        if not entries:
            raise core.GatewayError("Role %s was not found." % name, status=404)
        return entries[0]["content"]

    def update_role(self, name, fields):
        # simpleRequest only accepts a dict (it calls .items() on it) and sends
        # a list value as one form value per item. An empty list is sent as a
        # single empty value, which is how splunkd clears the attribute. A
        # string is sent as is. The live tests assert these against splunkd.
        postargs = {}
        for field, value in fields.items():
            if isinstance(value, (list, tuple)):
                postargs[field] = list(value) if value else ""
            else:
                postargs[field] = value
        self._request("/services/authorization/roles/%s" % quote(name, safe=""),
                      method="POST", postargs=postargs)


class RolesHandler(PersistentServerConnectionApplication):
    """GET returns every tab of the role model; POST applies a list of changes."""

    def __init__(self, command_line, command_arg):
        PersistentServerConnectionApplication.__init__(self)
        _configure_logging()

    def handle(self, in_string):
        try:
            if isinstance(in_string, bytes):
                in_string = in_string.decode("utf-8", "replace")
            request = json.loads(in_string)
            session = request.get("session") or {}
            status, payload = core.handle_request(
                request.get("method"),
                request.get("payload"),
                SplunkdGateway(session.get("authtoken")),
                user=session.get("user") or "unknown",
            )
        except Exception:  # pylint: disable=broad-except
            # Never leak a traceback to the browser; the detail goes to the log.
            logger.exception("Unhandled error in role management endpoint")
            status, payload = 500, core.error_payload(
                "Easy Admin hit an unexpected error. See easyadmin.log on the search head.")
        return {
            "status": status,
            "payload": json.dumps(payload),
            "headers": {"Content-Type": "application/json"},
        }
