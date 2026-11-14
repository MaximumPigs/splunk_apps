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

"""REST endpoint behind the Easy Admin app management page.

A thin wrapper like easyadmin_rest: the model, validation and the order of
writes live in easyadmin_apps_core, which imports nothing from Splunk. Every
call to splunkd is made with the calling user's session token.

This handler has its own script because splunkd's persistent-handler loader
refuses a script that defines more than one PersistentServerConnectionApplication
subclass, whatever restmap.conf's ``handler`` names (observed on 10.6.1:
"Error starting: More than one class implements
PersistentServerConnectionApplication", which took both endpoints down). The
shared gateway is therefore imported as a module, never by class name.

Must remain valid on Python 3.9 as well as 3.13.
"""

import json
import logging
import os
import sys

# splunkd starts persistent handlers with its own working directory, so the
# app's bin/ is not reliably importable until it is added here.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from splunk.persistconn.application import PersistentServerConnectionApplication  # noqa: E402

import easyadmin_apps_core as apps_core  # noqa: E402
import easyadmin_core as core  # noqa: E402
import easyadmin_rest as roles_rest  # noqa: E402  (a module, so its handler class stays out of this one)

logger = logging.getLogger("easyadmin")


class AppsGateway(roles_rest.SplunkdGateway):
    """The splunkd calls easyadmin_apps_core needs, made as the calling user."""

    @staticmethod
    def _full_entries(document):
        # The page needs each object's acl and links as well as its content:
        # the links say whether splunkd will move or delete it.
        return [{"name": entry.get("name"), "id": entry.get("id"),
                 "acl": entry.get("acl") or {}, "links": entry.get("links") or {},
                 "content": entry.get("content") or {}}
                for entry in document.get("entry") or []]

    def list_apps(self):
        return self._entries(self._request("/services/apps/local", getargs={"count": 0}))

    def list_objects(self, endpoint):
        # -/- lists every app and every owner's objects the caller may see,
        # private ones included. f=disabled trims content to one field: a
        # dashboard's content holds its whole source, which the list does not
        # need (the details panel fetches one object in full).
        return self._full_entries(self._request(
            "/servicesNS/-/-/%s" % endpoint, getargs={"count": 0, "f": "disabled"}))

    def list_role_names(self):
        return [e["name"] for e in self._entries(self._request(
            "/services/authorization/roles", getargs={"count": 0, "f": "imported_roles"}))]

    def list_user_names(self):
        return [e["name"] for e in self._entries(self._request(
            "/services/authentication/users", getargs={"count": 0, "f": "realname"}))]

    def current_context(self):
        entries = self._entries(self._request("/services/authentication/current-context"))
        username = entries[0]["content"].get("username") if entries else None
        return {"username": username, "theme": self._user_theme(username)}

    def get_object(self, path, full=False):
        # The path is built by easyadmin_apps_core.object_path from a known
        # type and quoted parts, never taken from the request as is.
        getargs = {} if full else {"f": "disabled"}
        try:
            entries = self._full_entries(self._request(path, getargs=getargs))
        except core.GatewayError as error:
            if error.status != 404:
                raise
            entries = []
        if not entries:
            raise core.GatewayError("Object not found.", status=404)
        return entries[0]

    def move_object(self, path, app, user):
        self._request(path + "/move", method="POST", postargs={"app": app, "user": user})

    def set_acl(self, path, postargs):
        self._request(path + "/acl", method="POST", postargs=postargs)

    def delete_object(self, path):
        self._request(path, method="DELETE")


def _query_dict(request):
    """The query string of a persistent-handler request as {name: value}.

    splunkd passes it as a list of [name, value] pairs; the last value wins.
    """
    query = {}
    for pair in request.get("query") or []:
        if isinstance(pair, (list, tuple)) and len(pair) == 2:
            query[pair[0]] = pair[1]
    return query


class AppsHandler(PersistentServerConnectionApplication):
    """GET returns the app model (or one object's settings); POST applies changes."""

    def __init__(self, command_line, command_arg):
        PersistentServerConnectionApplication.__init__(self)
        roles_rest._configure_logging()

    def handle(self, in_string):
        try:
            if isinstance(in_string, bytes):
                in_string = in_string.decode("utf-8", "replace")
            request = json.loads(in_string)
            session = request.get("session") or {}
            status, payload = apps_core.handle_request(
                request.get("method"),
                request.get("payload"),
                _query_dict(request),
                AppsGateway(session.get("authtoken")),
                user=session.get("user") or "unknown",
            )
        except Exception:  # pylint: disable=broad-except
            logger.exception("Unhandled error in app management endpoint")
            status, payload = 500, core.error_payload(
                "Easy Admin hit an unexpected error. See easyadmin.log on the search head.")
        return {
            "status": status,
            "payload": json.dumps(payload),
            "headers": {"Content-Type": "application/json"},
        }
