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

"""Pure logic behind the App management page: no Splunk imports.

The page shows every app with the knowledge objects it holds, and lets an
administrator move objects between apps, change their sharing, owner and
permissions, or delete them, all staged and applied at once.

What splunkd allows for an object is read from the object itself, never
assumed per type. Observed on 10.6.1 and pinned by tests/live/easyadmin/
test_easyadmin_apps_live.py: an object that exists in an app's default/
folder has no ``move`` or ``remove`` link, and splunkd refuses to move it
("cannot be deleted and thus it cannot be moved"). Such objects are shown
locked: they can be re-permissioned (splunkd writes local.meta) but not moved
or deleted, which keeps every write within the REST API and so within what
Splunk Cloud permits.

Must remain valid on Python 3.9 as well as 3.13.
"""

import json
import logging
import re
from collections import OrderedDict

try:  # Python 3
    from urllib.parse import parse_qs, quote, unquote
except ImportError:  # pragma: no cover - Splunk no longer ships Python 2
    from urllib import quote, unquote
    from urlparse import parse_qs

from easyadmin_core import EasyAdminError, GatewayError, as_list, as_text, error_payload

logger = logging.getLogger("easyadmin")

# Every kind of knowledge object the page lists, in the order its legend shows
# them. ``endpoint`` is the splunkd collection under /servicesNS/<user>/<app>/.
# admin/directory was not used: on 10.6.1 it omits lookup table files, data
# models and calculated fields (75 of them on the dev target).
TYPES = OrderedDict((t["id"], t) for t in (
    {"id": "savedsearch", "label": "Report or alert", "endpoint": "saved/searches"},
    {"id": "view", "label": "Dashboard", "endpoint": "data/ui/views"},
    {"id": "nav", "label": "Navigation menu", "endpoint": "data/ui/nav"},
    {"id": "panel", "label": "Prebuilt panel", "endpoint": "data/ui/panels"},
    {"id": "macro", "label": "Search macro", "endpoint": "admin/macros"},
    {"id": "eventtype", "label": "Event type", "endpoint": "saved/eventtypes"},
    {"id": "tag", "label": "Tag", "endpoint": "saved/fvtags"},
    {"id": "extraction", "label": "Field extraction", "endpoint": "data/props/extractions"},
    {"id": "fieldalias", "label": "Field alias", "endpoint": "data/props/fieldaliases"},
    {"id": "calcfield", "label": "Calculated field", "endpoint": "data/props/calcfields"},
    {"id": "autolookup", "label": "Automatic lookup", "endpoint": "data/props/lookups"},
    {"id": "sourcetyperename", "label": "Source type renaming",
     "endpoint": "data/props/sourcetype-rename"},
    {"id": "transform", "label": "Field transformation", "endpoint": "data/transforms/extractions"},
    {"id": "lookupdef", "label": "Lookup definition", "endpoint": "data/transforms/lookups"},
    {"id": "lookupfile", "label": "Lookup table file", "endpoint": "data/lookup-table-files"},
    {"id": "workflow", "label": "Workflow action", "endpoint": "data/ui/workflow-actions"},
    {"id": "timerange", "label": "Time range", "endpoint": "data/ui/times"},
    {"id": "datamodel", "label": "Data model", "endpoint": "datamodel/model"},
    {"id": "collection", "label": "KV store collection", "endpoint": "storage/collections/config"},
    {"id": "alertaction", "label": "Alert action", "endpoint": "data/ui/alerts"},
))

SHARING = ("user", "app", "global")

# Objects in $SPLUNK_HOME/etc/system report this as their app. It is not an
# app directory, so nothing can be moved into it.
SYSTEM_APP = "system"

# Bounds on one apply request, so a malformed or hostile body cannot make the
# handler issue an unbounded number of splunkd calls.
MAX_CHANGES = 2000
MAX_NAME_LENGTH = 1024
MAX_ROLES = 500

# Longest single setting shown in the details panel. A dashboard's XML can be
# hundreds of kilobytes; the panel is for reading settings, not the source.
MAX_DETAIL_VALUE = 4000

# App directory names: what Splunk's own "Create app" form accepts.
APP_NAME_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.\-]*$")
CONTROL_RE = re.compile(u"[\u0000-\u001f\u007f]")


def _is_true(value):
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "t", "yes")


def namespace_of(entry_id):
    """The user and app parts of an entry's id URL, or (None, None).

    ``https://host:8089/servicesNS/admin/search/admin/macros/x`` gives
    ``("admin", "search")``. A private object lives in its owner's namespace
    and a shared one in ``nobody``'s; the id is the one place that says which,
    and the object can only be addressed (moved, re-permissioned, deleted)
    through that namespace.
    """
    marker = "/servicesNS/"
    text = entry_id or ""
    at = text.find(marker)
    if at < 0:
        return None, None
    parts = text[at + len(marker):].split("/")
    if len(parts) < 2:
        return None, None
    return unquote(parts[0]), unquote(parts[1])


def object_key(type_id, ns, app, name):
    """One string per object, for the page's maps. NUL cannot occur in a name."""
    return u"\u0000".join((type_id, ns, app, name))


def object_path(type_id, ns, app, name):
    """The splunkd path of one object. Every part is quoted, ``safe=""``."""
    return "/servicesNS/%s/%s/%s/%s" % (quote(ns, safe=""), quote(app, safe=""),
                                        TYPES[type_id]["endpoint"], quote(name, safe=""))


def build_object(type_id, entry):
    """Normalise one REST entry (name, id, acl, links, content) for the page."""
    acl = entry.get("acl") or {}
    links = entry.get("links") or {}
    perms = acl.get("perms") or {}
    sharing = as_text(acl.get("sharing")) or "app"
    owner = as_text(acl.get("owner")) or "nobody"
    ns, path_app = namespace_of(entry.get("id"))
    app = as_text(acl.get("app")) or path_app or ""
    if not ns:
        ns = owner if sharing == "user" else "nobody"
    content = entry.get("content") or {}
    name = as_text(entry.get("name"))
    return {
        "key": object_key(type_id, ns, app, name),
        "type": type_id,
        "name": name,
        "app": app,
        "ns": ns,
        "owner": owner,
        "sharing": sharing,
        "read": as_list(perms.get("read")),
        "write": as_list(perms.get("write")),
        # Read from the links splunkd offers for this very object: an object
        # in default/ has neither, and a move or delete of it is refused.
        "movable": "move" in links,
        "removable": "remove" in links,
        "can_change_perms": _is_true(acl.get("can_change_perms")),
        "can_share_global": _is_true(acl.get("can_share_global", True)),
        "can_share_app": _is_true(acl.get("can_share_app", True)),
        "disabled": _is_true(content.get("disabled", False)),
    }


def build_app(entry):
    content = entry.get("content") or {}
    name = as_text(entry.get("name"))
    return {
        "name": name,
        "label": as_text(content.get("label")) or name,
        # core=1 marks the apps Splunk ships (search, launcher, splunk_*...).
        "builtin": _is_true(content.get("core", False)),
        "visible": _is_true(content.get("visible", True)),
        "disabled": _is_true(content.get("disabled", False)),
        "version": as_text(content.get("version")),
        "target": True,
    }


def _system_app():
    return {"name": SYSTEM_APP, "label": "System (etc/system)", "builtin": True,
            "visible": False, "disabled": False, "version": "", "target": False}


def _missing_app(name):
    # An object reports an app that apps/local did not list (for example one
    # the user cannot see). Show it so its objects are not hidden, but do not
    # offer it as a destination.
    return {"name": name, "label": name, "builtin": False, "visible": False,
            "disabled": False, "version": "", "target": False}


def build_model(app_entries, objects_by_type, failures, roles, users, context):
    """The document the page renders.

    ``objects_by_type`` maps a type id to its REST entries; ``failures`` maps a
    type id to the reason it could not be listed (usually a missing
    capability), which the page shows rather than silently omitting the type.
    """
    apps = OrderedDict()
    for entry in app_entries:
        app = build_app(entry)
        if app["name"]:
            apps[app["name"]] = app
    objects = []
    for type_id in TYPES:
        for entry in objects_by_type.get(type_id) or []:
            item = build_object(type_id, entry)
            if not item["name"] or not item["app"]:
                continue
            if item["app"] not in apps:
                apps[item["app"]] = _system_app() if item["app"] == SYSTEM_APP else _missing_app(item["app"])
            objects.append(item)
    objects.sort(key=lambda o: (o["app"].lower(), list(TYPES).index(o["type"]), o["name"].lower()))
    return {
        "types": [{"id": t["id"], "label": t["label"]} for t in TYPES.values()],
        # Alphabetical by the label people see in each box's title; the
        # directory name only breaks ties.
        "apps": sorted(apps.values(), key=lambda a: (a["label"].lower(), a["name"].lower())),
        "objects": objects,
        "warnings": ["%s could not be listed: %s" % (TYPES[t]["label"], failures[t])
                     for t in TYPES if t in failures],
        "roles": sorted(set(roles), key=lambda r: r.lower()),
        "users": sorted(set(users), key=lambda u: u.lower()),
        "user": context.get("username") or "",
        "theme": context.get("theme"),
    }


def read_model(gateway):
    objects_by_type = {}
    failures = {}
    for type_id, spec in TYPES.items():
        try:
            objects_by_type[type_id] = gateway.list_objects(spec["endpoint"])
        except GatewayError as error:
            failures[type_id] = str(error)
    try:
        roles = gateway.list_role_names()
    except GatewayError as error:
        logger.info("Could not list roles for the permissions editor: %s", error)
        roles = []
    try:
        users = gateway.list_user_names()
    except GatewayError as error:
        logger.info("Could not list users for the owner field: %s", error)
        users = []
    return build_model(gateway.list_apps(), objects_by_type, failures, roles, users,
                       gateway.current_context())


# ----------------------------------------------------------------- details

def build_details(type_id, entry):
    """Every setting of one object, for the side panel, values capped in size."""
    item = build_object(type_id, entry)
    settings = []
    for name in sorted((entry.get("content") or {}).keys()):
        if name.startswith("eai:acl") or name == "eai:appName" or name == "eai:userName":
            continue
        value = entry["content"][name]
        if isinstance(value, (dict, list)):
            text = json.dumps(value, sort_keys=True)
        else:
            text = as_text(value)
        truncated = len(text) > MAX_DETAIL_VALUE
        settings.append({"name": name, "value": text[:MAX_DETAIL_VALUE], "truncated": truncated})
    item["settings"] = settings
    return item


def parse_object_ref(fields, where="Request"):
    """Validate the four parts that address an object; return them as a tuple."""
    if not isinstance(fields, dict):
        raise EasyAdminError("%s must be an object." % where)
    type_id = fields.get("type")
    if type_id not in TYPES:
        raise EasyAdminError("%s has an unknown object type: %r." % (where, type_id))
    parts = [type_id]
    for part in ("ns", "app", "name"):
        parts.append(_clean_name(fields.get(part), "%s %s" % (where, part)))
    return tuple(parts)


def _clean_name(value, what):
    if not isinstance(value, str) or not value.strip():
        raise EasyAdminError("%s must be a non-empty string." % what)
    if len(value) > MAX_NAME_LENGTH:
        raise EasyAdminError("%s is longer than %d characters." % (what, MAX_NAME_LENGTH))
    if CONTROL_RE.search(value):
        raise EasyAdminError("%s contains control characters." % what)
    # quote(safe="") encodes "/", but leaves a bare "." or ".." as is, which
    # would make it a relative path segment in the splunkd URL.
    if value.strip() in (".", ".."):
        raise EasyAdminError("%s is not a valid name." % what)
    return value


def _clean_roles(value, what):
    if not isinstance(value, list):
        raise EasyAdminError("%s must be a list of role names." % what)
    if len(value) > MAX_ROLES:
        raise EasyAdminError("%s lists more than %d roles." % (what, MAX_ROLES))
    roles = []
    for role in value:
        role = _clean_name(role, what).strip()
        # splunkd takes the list comma-separated, so a comma would split it.
        if "," in role:
            raise EasyAdminError("%s: a role name cannot contain a comma (%r)." % (what, role))
        if role not in roles:
            roles.append(role)
    return roles


# ----------------------------------------------------------------- changes

def parse_changes(raw):
    """Validate the page's change list. One entry per object, all of its edits.

    Each entry addresses the object where the page last saw it (type, ns,
    app, name) and carries any of: ``move_to`` (an app name), ``acl``
    (sharing, owner, read, write) and ``delete`` (true, alone).
    """
    if not isinstance(raw, list):
        raise EasyAdminError("'changes' must be a list.")
    if not raw:
        raise EasyAdminError("There are no changes to apply.")
    if len(raw) > MAX_CHANGES:
        raise EasyAdminError("At most %d objects can be changed at once." % MAX_CHANGES)
    changes = []
    seen = set()
    for position, entry in enumerate(raw, 1):
        where = "Change %d" % position
        type_id, ns, app, name = parse_object_ref(entry, where)
        key = object_key(type_id, ns, app, name)
        if key in seen:
            raise EasyAdminError("%s repeats an object listed earlier: %s." % (where, name))
        seen.add(key)
        change = {"key": key, "type": type_id, "ns": ns, "app": app, "name": name,
                  "move_to": None, "acl": None, "delete": False}

        if entry.get("delete") is not None:
            if entry.get("delete") is not True:
                raise EasyAdminError("%s: 'delete' must be true when present." % where)
            if entry.get("move_to") is not None or entry.get("acl") is not None:
                raise EasyAdminError("%s: a deleted object cannot also be moved or changed." % where)
            change["delete"] = True

        if entry.get("move_to") is not None:
            target = _clean_name(entry.get("move_to"), "%s move_to" % where)
            if not APP_NAME_RE.match(target) or target == SYSTEM_APP:
                raise EasyAdminError("%s: %r is not an app that objects can be moved to." % (where, target))
            if target == app:
                raise EasyAdminError("%s: %s is already in %s." % (where, name, app))
            change["move_to"] = target

        if entry.get("acl") is not None:
            acl = entry.get("acl")
            if not isinstance(acl, dict):
                raise EasyAdminError("%s: 'acl' must be an object." % where)
            sharing = acl.get("sharing")
            if sharing not in SHARING:
                raise EasyAdminError("%s: sharing must be one of %s." % (where, ", ".join(SHARING)))
            clean = {"sharing": sharing,
                     "owner": _clean_name(acl.get("owner"), "%s owner" % where).strip()}
            if sharing != "user":
                # A private object has no role permissions: only its owner sees it.
                clean["read"] = _clean_roles(acl.get("read", []), "%s read" % where)
                clean["write"] = _clean_roles(acl.get("write", []), "%s write" % where)
            change["acl"] = clean

        if not (change["delete"] or change["move_to"] or change["acl"]):
            raise EasyAdminError("%s for %s changes nothing." % (where, name))
        changes.append(change)
    return changes


def acl_postargs(acl):
    """The form fields for <object>/acl.

    splunkd requires ``sharing`` on every acl POST, even to change only the
    owner (observed: HTTP 400 "required arguments are missing: sharing").
    Role lists go comma-separated; an empty list is sent as "".
    """
    args = {"sharing": acl["sharing"], "owner": acl["owner"]}
    if acl["sharing"] != "user":
        args["perms.read"] = ",".join(acl["read"])
        args["perms.write"] = ",".join(acl["write"])
    return args


def _apply_one(gateway, change, user):
    """Apply one object's edits. Returns (status, message, moved_to)."""
    type_id, ns, app, name = change["type"], change["ns"], change["app"], change["name"]
    label = TYPES[type_id]["label"].lower()
    path = object_path(type_id, ns, app, name)
    try:
        entry = gateway.get_object(path)
    except GatewayError as error:
        if error.status == 404:
            return ("error", "%s is no longer in %s: it was moved, renamed or deleted elsewhere. "
                    "Reload to see where it is now." % (name, app), None)
        raise
    links = entry.get("links") or {}

    if change["delete"]:
        if "remove" not in links:
            return ("error", "%s ships in %s's default folder, so it cannot be deleted." % (name, app), None)
        gateway.delete_object(path)
        logger.info("user=%s action=delete type=%s app=%s owner_ns=%s name=%s",
                    user, type_id, app, ns, json.dumps(name))
        return ("applied", "Deleted %s %s from %s." % (label, name, app), None)

    moved_to = None
    if change["move_to"]:
        if "move" not in links:
            return ("error", "%s ships in %s's default folder, so it cannot be moved. "
                    "Copy it instead." % (name, app), None)
        # ``user`` keeps the object in its namespace: the owner's for a
        # private object, nobody's for a shared one (observed: the owner and
        # sharing are kept across the move).
        gateway.move_object(path, change["move_to"], ns)
        logger.info("user=%s action=move type=%s app=%s to=%s owner_ns=%s name=%s",
                    user, type_id, app, change["move_to"], ns, json.dumps(name))
        moved_to = app = change["move_to"]
        path = object_path(type_id, ns, app, name)

    if change["acl"]:
        acl = entry.get("acl") or {}
        if not _is_true(acl.get("can_change_perms", True)):
            message = "Your account cannot change the permissions of %s." % name
            return ("error", message if not moved_to else "Moved to %s, but %s" % (
                moved_to, message[0].lower() + message[1:]), moved_to)
        try:
            gateway.set_acl(path, acl_postargs(change["acl"]))
        except GatewayError as error:
            if not moved_to:
                raise
            return ("error", "Moved to %s, but its permissions were not changed: %s" % (moved_to, error),
                    moved_to)
        logger.info("user=%s action=acl type=%s app=%s owner_ns=%s name=%s acl=%s",
                    user, type_id, app, ns, json.dumps(name), json.dumps(change["acl"], sort_keys=True))

    if moved_to and change["acl"]:
        return ("applied", "Moved %s %s to %s and changed its permissions." % (label, name, moved_to), moved_to)
    if moved_to:
        return ("applied", "Moved %s %s to %s." % (label, name, moved_to), moved_to)
    return ("applied", "Changed the permissions of %s %s." % (label, name), None)


def submit_changes(gateway, raw_changes, user="unknown"):
    """Apply every change, one object at a time, and report each outcome.

    splunkd has no transaction across objects, so a failure on one does not
    stop the rest; the page keeps the failed ones pending to retry.
    """
    changes = parse_changes(raw_changes)
    results = []
    for change in changes:
        try:
            status, message, moved_to = _apply_one(gateway, change, user)
        except GatewayError as error:
            logger.warning("user=%s object=%s change refused: status=%s %s",
                           user, json.dumps(change["key"]), error.status, error)
            status, message, moved_to = "error", "%s: %s" % (change["name"], error), None
        results.append({"key": change["key"], "status": status, "message": message,
                        "moved_to": moved_to})
    return {
        "results": results,
        "applied": sum(1 for r in results if r["status"] == "applied"),
        "failed": sum(1 for r in results if r["status"] == "error"),
    }


def extract_document(body):
    """The JSON document a POST carries (the page sends ``{"changes": [...]}``).

    A form body with a ``changes`` field holding that JSON list is accepted
    too, as the role endpoint does, for generic REST clients and live tests.
    """
    if isinstance(body, bytes):
        body = body.decode("utf-8", "replace")
    text = (body or "").strip()
    if not text:
        raise EasyAdminError("Request body is empty.")
    try:
        if text.startswith("{"):
            document = json.loads(text)
            if not isinstance(document, dict):
                raise EasyAdminError("Request body must be a JSON object.")
            return document
        fields = parse_qs(text, keep_blank_values=True)
        if "changes" not in fields:
            raise EasyAdminError("Request has no 'changes' field.")
        return {"changes": json.loads(fields["changes"][0])}
    except ValueError:
        raise EasyAdminError("Request body is not valid JSON.")


def handle_request(method, body, query, gateway, user="unknown"):
    """Route one REST call. Returns ``(http_status, json_serialisable_payload)``.

    GET without parameters returns the whole model; GET with type, ns, app
    and name returns one object's settings for the details panel. POST
    applies a change list. Nothing changes state on GET.
    """
    method = (method or "").upper()
    query = query or {}
    try:
        if method == "GET":
            if query.get("type") is not None:
                type_id, ns, app, name = parse_object_ref(query, "Object")
                return 200, build_details(type_id, gateway.get_object(object_path(type_id, ns, app, name),
                                                                       full=True))
            return 200, read_model(gateway)
        if method == "POST":
            document = extract_document(body)
            return 200, submit_changes(gateway, document.get("changes"), user=user)
        return 405, error_payload("Method %s is not supported." % method)
    except EasyAdminError as error:
        return error.status, error_payload(str(error))
    except GatewayError as error:
        return error.status, error_payload(str(error))
