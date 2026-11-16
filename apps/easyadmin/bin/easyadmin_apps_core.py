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

import easyadmin_conf_core as conf_core
from easyadmin_core import EasyAdminError, GatewayError, as_list, as_text, error_payload

logger = logging.getLogger("easyadmin")

# Every kind of knowledge object the page lists, in the order its legend shows
# them. ``endpoint`` is the splunkd collection under /servicesNS/<user>/<app>/.
# ``copy`` says how a copy is made in another app: "fields" posts the
# object's writable fields (from its "fields" list) to the same endpoint in
# the target app. None means it cannot be copied (all observed on 10.6.1):
# - props-based objects and tags: their endpoints refuse a create with the
#   source's arguments ("missing: stanza, type"; "already exists"), and the
#   configs/conf-props and conf-tags fallback is not reliable either: it
#   answers 409 for a stanza that is only visible from another app, reports
#   saved/fvtags as belonging to whichever app asks, and a write of a value
#   equal to the one in effect left nothing on disk;
# - lookup table files need Splunk's staging folder;
# - a navigation menu belongs to its app.
# ``common`` marks what users create day to day (reports, dashboards, lookups,
# macros...): the page shows those types at first and leaves the
# administrator's ones (navigation, panels, time ranges...) to be added.
# admin/directory was not used: on 10.6.1 it omits lookup table files, data
# models and calculated fields (75 of them on the dev target).
TYPES = OrderedDict((t["id"], t) for t in (
    {"id": "savedsearch", "label": "Report or alert", "endpoint": "saved/searches", "common": True, "copy": "fields"},
    {"id": "view", "label": "Dashboard", "endpoint": "data/ui/views", "common": True, "copy": "fields"},
    {"id": "nav", "label": "Navigation menu", "endpoint": "data/ui/nav", "common": False, "copy": None},
    {"id": "panel", "label": "Prebuilt panel", "endpoint": "data/ui/panels", "common": False, "copy": "fields"},
    {"id": "macro", "label": "Search macro", "endpoint": "admin/macros", "common": True, "copy": "fields"},
    {"id": "eventtype", "label": "Event type", "endpoint": "saved/eventtypes", "common": True, "copy": "fields"},
    {"id": "tag", "label": "Tag", "endpoint": "saved/fvtags", "common": True, "copy": None},
    {"id": "extraction", "label": "Field extraction", "endpoint": "data/props/extractions", "common": True, "copy": None},
    {"id": "fieldalias", "label": "Field alias", "endpoint": "data/props/fieldaliases", "common": True, "copy": None},
    {"id": "calcfield", "label": "Calculated field", "endpoint": "data/props/calcfields", "common": True, "copy": None},
    {"id": "autolookup", "label": "Automatic lookup", "endpoint": "data/props/lookups", "common": True, "copy": None},
    {"id": "sourcetyperename", "label": "Source type renaming",
     "endpoint": "data/props/sourcetype-rename", "common": False, "copy": None},
    {"id": "transform", "label": "Field transformation", "endpoint": "data/transforms/extractions", "common": False, "copy": "fields"},
    {"id": "lookupdef", "label": "Lookup definition", "endpoint": "data/transforms/lookups", "common": True, "copy": "fields"},
    {"id": "lookupfile", "label": "Lookup table file", "endpoint": "data/lookup-table-files", "common": True, "copy": None},
    {"id": "workflow", "label": "Workflow action", "endpoint": "data/ui/workflow-actions", "common": True, "copy": "fields"},
    {"id": "timerange", "label": "Time range", "endpoint": "data/ui/times", "common": False, "copy": "fields"},
    {"id": "datamodel", "label": "Data model", "endpoint": "datamodel/model", "common": True, "copy": "fields"},
    {"id": "collection", "label": "KV store collection", "endpoint": "storage/collections/config", "common": False, "copy": "fields"},
    {"id": "alertaction", "label": "Alert action", "endpoint": "data/ui/alerts", "common": False, "copy": None},
))

SHARING = ("user", "app", "global")

# Apps Splunk marks as its own (core=1) that are still where most users keep
# their knowledge objects, so they are shown with the installed apps rather
# than behind "Show Splunk's built-in apps".
USER_FACING_APPS = ("search", "SplunkEnterpriseSecuritySuite")

# Objects in $SPLUNK_HOME/etc/system report this as their app. It is not an
# app directory, so nothing can be moved into it.
SYSTEM_APP = "system"

# Bounds on one apply request, so a malformed or hostile body cannot make the
# handler issue an unbounded number of splunkd calls.
MAX_CHANGES = 2000

# The whole POST body of one Apply, in UTF-8 bytes. The per-value and
# per-object limits alone allow 200 settings x 64 KB x 2000 objects (the
# security review on #39), and neither Splunk Web nor splunkd stops that: a
# probe passed bodies of 64 MB through Splunk Web to this handler, and
# splunkd's own max_content_length is 2 GB. So the app sets its own cap. The
# page mirrors it (easyadmin_apps.js) and refuses at staging; this is the
# backstop. A 2000-object bulk permission change is about 6 MB.
MAX_REQUEST_BYTES = 16 * 1024 * 1024
MAX_NAME_LENGTH = 1024
MAX_ROLES = 500

# Longest single setting shown in the details panel. A dashboard's XML can be
# hundreds of kilobytes; the panel is for reading settings, not the source.
MAX_DETAIL_VALUE = 4000

# App directory names: what Splunk's own "Create app" form accepts.
APP_NAME_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.\-]*$")
CONTROL_RE = re.compile(u"[\u0000-\u001f\u007f]")

# Creating an app. Limits on one request, as for changes. The label rule is
# from Splunk's REST reference (5 to 80 characters, not starting "Splunk for").
MAX_NEW_APPS = 20
MAX_APP_NAME = 100
LABEL_MIN = 5
LABEL_MAX = 80
MAX_APP_TEXT = 1024
MAX_VERSION = 64
# The only template offered (the owner's choice); the client cannot pick one.
APP_TEMPLATE = "barebones"
DEFAULT_APP_VERSION = "1.0.0"
VERSION_RE = re.compile(r"^[0-9A-Za-z][0-9A-Za-z.\-+]*$")
# The keys a new app may carry. Anything else is refused, above all
# ``filename``, ``update`` and ``explicit_appname``: apps/local uses those to
# install a package from a path or a URL, which this page must never do.
NEW_APP_KEYS = ("name", "label", "visible", "description", "author", "version")
# What splunkd names in its 403 for apps/local (observed on 10.6.1): either
# capability allows a create.
CREATE_APP_CAPS = ("admin_all_objects", "edit_local_apps")


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
        # Read from splunkd for this very object: the link for the action and
        # its acl.removable flag. Links alone are not enough: a saved search
        # in an app's default folder still lists "move" and "remove", but has
        # removable 0, and splunkd refuses the move ("cannot be deleted and
        # thus it cannot be moved"; observed on 10.6.1). Other types drop the
        # links as well.
        "movable": "move" in links and _is_true(acl.get("removable", True)),
        "copyable": TYPES[type_id]["copy"] is not None,
        "removable": "remove" in links and _is_true(acl.get("removable", True)),
        "can_change_perms": _is_true(acl.get("can_change_perms")),
        "can_share_global": _is_true(acl.get("can_share_global", True)),
        "can_share_app": _is_true(acl.get("can_share_app", True)),
        "disabled": _is_true(content.get("disabled", False)),
        # Set by mark_local_changes for callers who may read the files.
        "local_file": None,
    }


def build_app(entry):
    content = entry.get("content") or {}
    name = as_text(entry.get("name"))
    return {
        "name": name,
        "label": as_text(content.get("label")) or name,
        # core=1 marks the apps Splunk ships (search, launcher, splunk_*...).
        "builtin": _is_true(content.get("core", False)) and name not in USER_FACING_APPS,
        "visible": _is_true(content.get("visible", True)),
        "disabled": _is_true(content.get("disabled", False)),
        "version": as_text(content.get("version")),
        # Pre-fill a clone's form; capped here so a huge value cannot bloat the model.
        "description": as_text(content.get("description"))[:MAX_APP_TEXT],
        "author": as_text(content.get("author"))[:MAX_APP_TEXT],
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
        "types": [{"id": t["id"], "label": t["label"], "common": t["common"]} for t in TYPES.values()],
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
        "can_create_apps": can_create_apps(context),
    }


def can_create_apps(context):
    caps = context.get("capabilities") or []
    return any(cap in caps for cap in CREATE_APP_CAPS)


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
    context = gateway.current_context()
    model = build_model(gateway.list_apps(), objects_by_type, failures, roles, users, context)
    # Reading the files bypasses splunkd's per-object permissions, so only
    # callers who may see every object get the name of a local file (the same
    # gate as the details panel's own settings, see add_explicit).
    if "admin_all_objects" in (context.get("capabilities") or []):
        mark_local_changes(model["objects"], gateway.read_local_conf)
    return model


def local_stanzas(text):
    """The names of the stanzas that set at least one key in this .conf text.

    A header with nothing under it does not count: there is nothing in it to remove.
    """
    return {name for name, settings in conf_core.parse_conf(text) if settings}


def local_file_path(conf, app):
    """The path of the local file as the page shows it, from the Splunk home folder."""
    if app == SYSTEM_APP:
        return "etc/system/local/%s.conf" % conf
    return "etc/apps/%s/local/%s.conf" % (app, conf)


def mark_local_changes(objects, read_local):
    """Set ``local_file`` on each shipped object whose stanza is also set in local.

    Splunk refuses to delete an object that ships in a default folder, and no
    REST call removes only its local layer (probed on 10.6.1 with a saved
    search: the typed endpoint and ``configs`` answer "cannot be deleted", the
    ``properties`` stanza DELETE answers success and changes nothing; see the
    README). So the page offers no delete and names the file whose stanza has
    to be edited instead. Only objects that are stanzas of a conf file
    qualify: a props-based object is one line of a shared stanza, and views,
    navigation, panels and lookup files are not stanzas.

    ``read_local(conf, app)`` returns the text of that app's local file or
    None; it is called once per file, however many objects the file holds.
    """
    wanted = {}
    for obj in objects:
        if obj["movable"] or obj["removable"] or obj["type"] not in STANZA_CONFS:
            continue
        wanted.setdefault((STANZA_CONFS[obj["type"]], obj["app"]), []).append(obj)
    for (conf, app), group in wanted.items():
        text = read_local(conf, app)
        names = local_stanzas(text) if text else set()
        for obj in group:
            if obj["name"] in names:
                obj["local_file"] = local_file_path(conf, app)


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


# The .conf file whose [<object name>] stanza holds each type's own settings.
# Dashboards, navigation and panels are XML files (all their settings are
# their own), props-based objects are a single line of a shared stanza (see
# PROPS_TYPES), and lookup files are files, so they are not here.
STANZA_CONFS = {
    "savedsearch": "savedsearches", "macro": "macros", "eventtype": "eventtypes", "tag": "tags",
    "transform": "transforms", "lookupdef": "transforms", "workflow": "workflow_actions",
    "timerange": "times", "datamodel": "datamodels", "collection": "collections",
    "alertaction": "alert_actions",
}

# Objects that are one line of a props.conf stanza (``EXTRACT-x``,
# ``FIELDALIAS-y``...): the entry names the stanza (``content.stanza``) and the
# line (``content.attribute``), and the stanza is shared with other objects, so
# only that one line may be written.
PROPS_TYPES = ("extraction", "fieldalias", "calcfield", "autolookup", "sourcetyperename")
PROPS_CONF = "props"

# Why a type is not editable here, for the page: view, nav and panel are one
# XML document each (the owner's decision: Splunk's own editors suit them
# better), and a lookup table file is a CSV file with no settings.
# Every other listed type is editable.
NOT_EDITABLE = ("view", "nav", "panel", "lookupfile")

# Types for which splunkd's ``fields`` are not the conf keys of the stanza
# (observed on 10.6.1: tags reports ``tags`` and ``tag\..*``, alert actions
# only ``eai:data``), so a new setting is free text there.
FREE_TEXT_TYPES = ("tag", "alertaction")

# Where an object's own stanza can be, lowest priority first: the app's
# default folder, its local folder, then the owner's private folder.
OWN_LAYERS = ("default", "local", "user")

# Bounds on a staged settings edit.
MAX_SETTINGS_PER_OBJECT = 200
MAX_SETTING_NAME = 256
MAX_SETTING_VALUE = 65536
# Control characters refused in a value: a newline and a tab are ordinary in
# searches and macros, anything else (NUL, CR, escape...) is not.
VALUE_CONTROL_RE = re.compile(u"[\u0000-\u0008\u000b-\u001f\u007f]")


def own_setting_target(type_id, entry, name):
    """Where an object's own settings live: (conf, stanza, only_attribute) or None.

    Stanza types use the object's name as stanza. A props-based object is one
    line of a stanza shared with other objects, so both the stanza and the
    line come from splunkd's own entry for it, never from the request, and
    ``only_attribute`` is that line.
    """
    if type_id in STANZA_CONFS:
        return STANZA_CONFS[type_id], name, None
    if type_id in PROPS_TYPES:
        content = entry.get("content") or {}
        stanza = as_text(content.get("stanza"))
        attribute = as_text(content.get("attribute"))
        if stanza and attribute:
            return PROPS_CONF, stanza, attribute
    return None


def _own_history(files, stanza, only=None):
    """{setting: [(layer, raw value), ...]}, lowest layer first, for one stanza."""
    history = {}
    for layer in OWN_LAYERS:
        text = files.get(layer)
        if text is None:
            continue
        for stanza_name, attrs in conf_core.parse_conf(text):
            if stanza_name != stanza:
                continue
            for attr, value in attrs.items():
                if only is not None and attr != only:
                    continue
                history.setdefault(attr, []).append((layer, value))
    return history


def _shown(attr, value):
    """(text, truncated) of a value as the panel may see it: masked, capped."""
    text = conf_core.MASK if conf_core.is_secret(attr) and value else value
    return text[:MAX_DETAIL_VALUE], len(text) > MAX_DETAIL_VALUE


def explicit_settings(files, stanza, only=None):
    """The settings set in an object's own stanza, as {name, value, layer, ...}.

    ``files`` maps a layer (default, local, user) to that file's text. Like
    btool, a later layer overrides an earlier one; ``layer`` says where the
    value in effect comes from, and ``overrides`` lists the values it hides
    (lowest layer first) so the page can show the default on request.
    [default] stanzas and other apps' files are not read: what they provide
    is what the object inherits. Secret values are masked as on the
    precedence tab, in ``overrides`` too. ``only`` limits the answer to one
    setting (a props-based object is one line of a shared stanza).
    """
    history = _own_history(files, stanza, only)
    settings = []
    for attr in sorted(history, key=str.lower):
        layer, raw = history[attr][-1]
        value, truncated = _shown(attr, raw)
        overrides = []
        for lower_layer, lower_raw in history[attr][:-1]:
            lower_value, lower_truncated = _shown(attr, lower_raw)
            overrides.append({"layer": lower_layer, "value": lower_value, "truncated": lower_truncated})
        settings.append({"name": attr, "layer": layer, "value": value, "truncated": truncated,
                         "secret": conf_core.is_secret(attr), "overrides": overrides})
    return settings


def _wildcards(fields):
    patterns = []
    for pattern in fields.get("wildcard") or []:
        try:
            patterns.append(re.compile("^(?:%s)$" % pattern))
        except re.error:
            continue
    return patterns


def add_explicit(details, gateway, type_id, ns, app, name, entry=None):
    """Add the object's own settings to ``details``, or say why they are absent.

    Reading files bypasses splunkd's per-object permissions, so, as on the
    precedence tab, only callers with admin_all_objects get them. The same
    holds for editing, whose result is verified by reading the files.
    ``editable`` says whether this caller may stage settings edits, and
    ``edit_note`` why not.
    """
    entry = entry or {}
    details.update({"explicit": None, "editable": False, "edit_layer": None, "edit_note": None,
                    "addable": [], "addable_patterns": [], "free_text": False})
    target = own_setting_target(type_id, entry, name)
    if target is None:
        details["explicit_note"] = "kind"
        details["edit_note"] = "kind"
        return details
    conf, stanza, only = target
    if "admin_all_objects" not in gateway.caller_capabilities():
        details["explicit_note"] = "capability"
        details["edit_note"] = "capability"
        return details
    files = gateway.read_own_conf(conf, app, ns if ns != "nobody" else None)
    details["explicit"] = explicit_settings(files, stanza, only)
    details["explicit_note"] = None
    details["explicit_conf"] = conf
    acl = entry.get("acl") or {}
    if not _is_true(acl.get("can_write", False)):
        details["edit_note"] = "write"
        return details
    details["editable"] = True
    details["edit_layer"] = "user" if as_text(acl.get("sharing")) == "user" else "local"
    if only is not None:
        return details    # a props-based object is its one line: nothing to add
    if type_id in FREE_TEXT_TYPES:
        details["free_text"] = True
        return details
    fields = entry.get("fields") or {}
    own = set(s["name"] for s in details["explicit"])
    names = set(fields.get("required") or []) | set(fields.get("optional") or [])
    details["addable"] = sorted((n for n in names if not n.startswith("eai:") and n not in own
                                 and not conf_core.is_secret(n)), key=str.lower)
    details["addable_patterns"] = [p for p in (fields.get("wildcard") or []) if isinstance(p, str)]
    return details


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

def _app_text(value, what, maximum, required=False):
    if value is None or value == "":
        if required:
            raise EasyAdminError("%s is required." % what)
        return ""
    if not isinstance(value, str):
        raise EasyAdminError("%s must be text." % what)
    value = value.strip()
    if required and not value:
        raise EasyAdminError("%s is required." % what)
    if len(value) > maximum:
        raise EasyAdminError("%s is longer than %d characters." % (what, maximum))
    if CONTROL_RE.search(value):
        raise EasyAdminError("%s contains control characters." % what)
    return value


def parse_new_apps(raw, existing_names=()):
    """Validate the apps to create. Returns a list of clean specs.

    ``existing_names`` are the apps already on the target. Names are compared
    case-insensitively, as app directories are on Windows and macOS file
    systems, so "Search" is refused beside "search".
    """
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise EasyAdminError("'apps' must be a list.")
    if len(raw) > MAX_NEW_APPS:
        raise EasyAdminError("At most %d apps can be created at once." % MAX_NEW_APPS)
    taken = set(name.lower() for name in existing_names)
    taken.add(SYSTEM_APP)
    specs = []
    for position, entry in enumerate(raw, 1):
        where = "App %d" % position
        if not isinstance(entry, dict):
            raise EasyAdminError("%s must be an object." % where)
        unknown = sorted(str(key) for key in entry if key not in NEW_APP_KEYS)
        if unknown:
            raise EasyAdminError("%s has settings that are not accepted: %s." % (where, ", ".join(unknown)))
        name = entry.get("name")
        if not isinstance(name, str) or not name.strip():
            raise EasyAdminError("%s needs an app ID." % where)
        name = name.strip()
        if len(name) > MAX_APP_NAME:
            raise EasyAdminError("%s: the app ID is longer than %d characters." % (where, MAX_APP_NAME))
        if not APP_NAME_RE.match(name) or name in (".", ".."):
            raise EasyAdminError('%s: "%s" is not a valid app ID. Use letters, digits, "_", "-" and ".", '
                                 "starting with a letter, digit or \"_\"." % (where, name))
        if name.lower() in taken:
            raise EasyAdminError('%s: an app called "%s" already exists, or is named twice in this request.'
                                 % (where, name))
        taken.add(name.lower())
        label = _app_text(entry.get("label"), "%s: the label" % where, LABEL_MAX, required=True)
        if len(label) < LABEL_MIN:
            raise EasyAdminError("%s: the label must be at least %d characters." % (where, LABEL_MIN))
        if label.lower().startswith("splunk for"):
            raise EasyAdminError('%s: the label cannot start with "Splunk for".' % where)
        visible = entry.get("visible", True)
        if not isinstance(visible, bool):
            raise EasyAdminError("%s: 'visible' must be true or false." % where)
        version = _app_text(entry.get("version"), "%s: the version" % where, MAX_VERSION) or DEFAULT_APP_VERSION
        if not VERSION_RE.match(version):
            raise EasyAdminError("%s: \"%s\" is not a valid version." % (where, version))
        specs.append({
            "name": name, "label": label, "visible": visible, "version": version,
            "description": _app_text(entry.get("description"), "%s: the description" % where, MAX_APP_TEXT),
            "author": _app_text(entry.get("author"), "%s: the author" % where, MAX_APP_TEXT),
        })
    return specs


def create_app_args(spec):
    """The exact form fields for POST apps/local; nothing else is ever sent."""
    args = {"name": spec["name"], "template": APP_TEMPLATE, "label": spec["label"],
            "visible": "1" if spec["visible"] else "0", "version": spec["version"]}
    for field in ("description", "author"):
        if spec.get(field):
            args[field] = spec[field]
    return args


def _create_one(gateway, spec, user):
    """Create one app; returns its per-app result."""
    name = spec["name"]
    try:
        gateway.create_app(create_app_args(spec))
    except GatewayError as error:
        logger.warning("user=%s action=create_app app=%s refused: status=%s %s",
                       user, json.dumps(name), error.status, json.dumps(str(error)))
        if error.status == 409:
            message = 'An app called "%s" already exists, so it was not created.' % name
        else:
            message = 'The app "%s" was not created: %s' % (name, error)
        return {"name": name, "status": "error", "message": message}
    logger.info("user=%s action=create_app app=%s label=%s version=%s",
                user, json.dumps(name), json.dumps(spec["label"]), json.dumps(spec["version"]))
    return {"name": name, "status": "applied", "message": 'Created the app "%s".' % name}


RESERVED_FORM_KEYS = frozenset(("output_mode", "name", "owner", "sharing", "app", "count", "f"))


def parse_settings(raw, type_id, where):
    """Validate the settings edits of one change: [{name, value, previous}].

    ``previous`` is the value the page saw (null for a setting the object did
    not have), checked again at Apply so an edit never overwrites a change
    made elsewhere. Names are checked against what the object may hold when
    it is applied (that needs splunkd's own entry for it); here only their
    shape. Secrets are masked on the page, so they are not edited here.
    """
    if type_id in NOT_EDITABLE:
        raise EasyAdminError("%s: the settings of %s objects cannot be edited here." % (
            where, TYPES[type_id]["label"].lower()))
    if not isinstance(raw, list) or not raw:
        raise EasyAdminError("%s: 'settings' must be a non-empty list." % where)
    if len(raw) > MAX_SETTINGS_PER_OBJECT:
        raise EasyAdminError("%s: at most %d settings can be changed on one object." % (
            where, MAX_SETTINGS_PER_OBJECT))
    settings = []
    seen = set()
    for item in raw:
        if not isinstance(item, dict):
            raise EasyAdminError("%s: each setting must be an object." % where)
        name = item.get("name")
        if not isinstance(name, str) or not name or len(name) > MAX_SETTING_NAME:
            raise EasyAdminError("%s: a setting needs a name of 1 to %d characters." % (where, MAX_SETTING_NAME))
        if (CONTROL_RE.search(name) or "=" in name or name[0] in "[#" or name != name.strip()
                or name.startswith("eai:")):
            raise EasyAdminError("%s: %r is not a name a setting can have." % (where, name))
        if name in RESERVED_FORM_KEYS:
            # These are splunkd's own form parameters, not settings: sent in the
            # POST body they would change the request, not the object.
            raise EasyAdminError('%s: "%s" is reserved by splunkd and cannot be a setting.' % (where, name))
        if conf_core.is_secret(name):
            raise EasyAdminError('%s: "%s" looks like a secret, and secrets are not edited here.' % (where, name))
        if name in seen:
            raise EasyAdminError("%s: the setting \"%s\" is listed twice." % (where, name))
        seen.add(name)
        value = item.get("value")
        if not isinstance(value, str):
            raise EasyAdminError('%s: the value of "%s" must be text.' % (where, name))
        if len(value) > MAX_SETTING_VALUE:
            raise EasyAdminError('%s: the value of "%s" is longer than %d characters.' % (
                where, name, MAX_SETTING_VALUE))
        if VALUE_CONTROL_RE.search(value):
            raise EasyAdminError('%s: the value of "%s" contains control characters.' % (where, name))
        if "previous" not in item:
            raise EasyAdminError('%s: "%s" needs the value it had when the page loaded ("previous").' % (where, name))
        previous = item.get("previous")
        if previous is not None and (not isinstance(previous, str) or len(previous) > MAX_SETTING_VALUE):
            raise EasyAdminError('%s: "previous" of "%s" must be text or null.' % (where, name))
        settings.append({"name": name, "value": value, "previous": previous})
    return settings


def parse_changes(raw, allow_empty=False):
    """Validate the page's change list. One entry per object, all of its edits.

    Each entry addresses the object where the page last saw it (type, ns,
    app, name) and carries any of: ``move_to`` or ``copy_to`` (an app name),
    ``acl`` (sharing, owner, read, write) and ``delete`` (true, alone).
    ``allow_empty`` is for a request that creates apps and changes nothing.
    """
    if raw is None and allow_empty:
        return []
    if not isinstance(raw, list):
        raise EasyAdminError("'changes' must be a list.")
    if not raw and not allow_empty:
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
            raise EasyAdminError("%s repeats an object listed earlier: \"%s\"." % (where, name))
        seen.add(key)
        change = {"key": key, "type": type_id, "ns": ns, "app": app, "name": name,
                  "move_to": None, "copy_to": None, "acl": None, "delete": False, "settings": None}

        if entry.get("delete") is not None:
            if entry.get("delete") is not True:
                raise EasyAdminError("%s: 'delete' must be true when present." % where)
            if any(entry.get(k) is not None for k in ("move_to", "copy_to", "acl", "settings")):
                raise EasyAdminError("%s: a deleted object cannot also be moved, copied or changed." % where)
            change["delete"] = True

        if entry.get("settings") is not None:
            change["settings"] = parse_settings(entry.get("settings"), type_id, where)

        if entry.get("move_to") is not None and entry.get("copy_to") is not None:
            raise EasyAdminError("%s: an object is either moved or copied, not both." % where)
        for field, verb in (("move_to", "moved"), ("copy_to", "copied")):
            if entry.get(field) is None:
                continue
            target = _clean_name(entry.get(field), "%s %s" % (where, field))
            if not APP_NAME_RE.match(target) or target == SYSTEM_APP:
                raise EasyAdminError("%s: %r is not an app that objects can be %s to." % (where, target, verb))
            if target == app:
                raise EasyAdminError("%s: \"%s\" is already in \"%s\"." % (where, name, app))
            if field == "copy_to" and TYPES[type_id]["copy"] is None:
                raise EasyAdminError("%s: %s objects cannot be copied." % (where, TYPES[type_id]["label"]))
            change[field] = target

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

        if not (change["delete"] or change["move_to"] or change["copy_to"] or change["acl"] or change["settings"]):
            raise EasyAdminError("%s for \"%s\" changes nothing." % (where, name))
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


def get_in_app(gateway, type_id, ns, app, name, full=False):
    """The object called ``name`` that lives in ``app``, or GatewayError 404.

    A GET under /servicesNS/<ns>/<app>/ returns any object *visible* from
    that app, and an object shared with all apps is visible from every app
    (observed on 10.6.1: the search app's global objects answered under
    launcher). Acting on what came back could change another app's object,
    so the answer counts only when its own acl.app is ``app``.
    """
    entry = gateway.get_object(object_path(type_id, ns, app, name), full=full)
    if as_text((entry.get("acl") or {}).get("app")) != app:
        raise GatewayError('"%s" is not in "%s".' % (name, app), status=404)
    return entry


def copy_args(entry):
    """The form fields that recreate ``entry`` through its endpoint's create.

    splunkd lists, per object, the fields its endpoint accepts: ``required``,
    ``optional`` and ``wildcard`` patterns (such as ``action\\..*``). Only
    those are sent; ``eai:*`` metadata is not, except ``eai:data`` (a
    dashboard's or data model's source). Booleans and numbers go as text.
    """
    fields = entry.get("fields") or {}
    allowed = set(fields.get("required") or []) | set(fields.get("optional") or [])
    wildcards = []
    for pattern in fields.get("wildcard") or []:
        try:
            wildcards.append(re.compile("^(?:%s)$" % pattern))
        except re.error:
            continue
    args = {}
    for attr, value in (entry.get("content") or {}).items():
        if value is None or (attr.startswith("eai:") and attr != "eai:data"):
            continue
        if attr not in allowed and not any(w.match(attr) for w in wildcards):
            continue
        if isinstance(value, bool):
            value = "1" if value else "0"
        elif isinstance(value, (int, float)):
            value = str(value)
        elif isinstance(value, dict):
            continue
        args[attr] = value
    args["name"] = as_text(entry.get("name"))
    return args


def _copy_one(gateway, change, entry, user):
    """Create a copy of the object in ``copy_to``; returns (status, message)."""
    type_id, ns, name, target = change["type"], change["ns"], change["name"], change["copy_to"]
    label = TYPES[type_id]["label"].lower()
    new_path = object_path(type_id, ns, target, name)
    try:
        get_in_app(gateway, type_id, ns, target, name)
        return "error", '"%s" already exists in "%s", so it was not copied.' % (name, target)
    except GatewayError as error:
        if error.status != 404:
            raise
    full = get_in_app(gateway, type_id, ns, change["app"], name, full=True)
    gateway.create_object("/servicesNS/%s/%s/%s" % (quote(ns, safe=""), quote(target, safe=""),
                                                     TYPES[type_id]["endpoint"]), copy_args(full))
    logger.info("user=%s action=copy type=%s app=%s to=%s owner_ns=%s name=%s",
                user, type_id, change["app"], target, ns, json.dumps(name))
    # The copy gets the source's sharing, owner and roles. A private copy
    # already has its owner's namespace, and splunkd keeps it private.
    acl = entry.get("acl") or {}
    sharing = as_text(acl.get("sharing")) or "app"
    if sharing in ("app", "global"):
        perms = acl.get("perms") or {}
        try:
            gateway.set_acl(new_path, acl_postargs({
                "sharing": sharing, "owner": as_text(acl.get("owner")) or "nobody",
                "read": as_list(perms.get("read")), "write": as_list(perms.get("write"))}))
        except GatewayError as error:
            # A copy left with the owner and sharing splunkd gave it on create
            # could run (a scheduled report) or be visible as someone else, so
            # it is removed again rather than kept half-made.
            try:
                gateway.delete_object(new_path)
                undone = "the copy was removed again"
            except GatewayError as cleanup:
                logger.warning("user=%s copy of %s in %s left behind: %s", user, json.dumps(name), target, cleanup)
                undone = 'the copy could not be removed and is still in "%s": check its permissions' % target
            logger.warning("user=%s copy of %s to %s: permissions refused: %s", user, json.dumps(name), target, error)
            return "error", '"%s" was not copied to "%s": its permissions could not be set (%s), so %s.' % (
                name, target, error, undone)
    change["copied"] = True
    return "applied", 'Copied %s "%s" to "%s".' % (label, name, target)


def _squash(text):
    """Whitespace-insensitive form, to compare a value with what the file holds.

    A conf file keeps a multi-line value with continuation backslashes, and
    trims the ends, so the comparison ignores the whitespace layout only.
    """
    return " ".join((text or "").replace("\\\n", "\n").split())


def _apply_settings(gateway, change, user):
    """Write the staged settings of one object. Returns (status, message).

    The write goes to ``configs/conf-<conf>/<stanza>`` and not to the type's
    own endpoint: on 10.6.1 that wrote exactly the posted keys into the app's
    local file (or the owner's folder for a private object, or etc/system/
    local), kept the object's sharing and roles, and created the file when
    the app had none. The type endpoints refuse partial edits (a macro needs
    ``definition`` and ``args`` again, a transform its REGEX) and one dropped
    an alias that was not posted. splunkd can answer 200 and write nothing
    for props and tags, so the result is read back from the files.
    """
    type_id, ns, app, name = change["type"], change["ns"], change["app"], change["name"]
    label = TYPES[type_id]["label"].lower()
    settings = change["settings"]
    try:
        entry = get_in_app(gateway, type_id, ns, app, name, full=True)
    except GatewayError as error:
        if error.status == 404:
            return ("error", '"%s" is no longer in "%s": it was moved, renamed or deleted elsewhere. '
                    "Reload to see where it is now." % (name, app))
        raise
    target = own_setting_target(type_id, entry, name)
    if target is None:
        return "error", 'The settings of "%s" cannot be edited here.' % name
    if "admin_all_objects" not in gateway.caller_capabilities():
        return "error", "Editing settings needs the admin_all_objects capability, as it reads the configuration files."
    acl = entry.get("acl") or {}
    if not _is_true(acl.get("can_write", False)):
        return "error", 'Your account cannot write to "%s".' % name
    conf, stanza, only = target
    reader_user = ns if ns != "nobody" else None
    layer = "user" if as_text(acl.get("sharing")) == "user" else "local"

    history = _own_history(gateway.read_own_conf(conf, app, reader_user), stanza, only)
    # Compare with the value in effect in the object's own files, where the
    # page saw it: a change made elsewhere since is not silently overwritten.
    for item in settings:
        current = history[item["name"]][-1][1] if item["name"] in history else None
        if current != item["previous"]:
            return "error", ('The settings of "%s" changed since the page loaded ("%s" is not as it was). '
                             "Reload to see the current values and decide again." % (name, item["name"]))

    fields = entry.get("fields") or {}
    allowed = set(fields.get("required") or []) | set(fields.get("optional") or [])
    wildcards = _wildcards(fields)
    for item in settings:
        setting = item["name"]
        if only is not None:
            # An object is exactly one line of a stanza shared with others:
            # any other key would change other objects.
            ok = setting == only
        else:
            ok = (setting in history or type_id in FREE_TEXT_TYPES or setting in allowed
                  or any(w.match(setting) for w in wildcards))
        if not ok:
            return "error", ('"%s" is not a setting splunkd lists for %s "%s", so it was not written.' % (
                setting, label, name) if only is None else
                '%s "%s" is the single setting "%s"; other settings of its stanza belong to other objects.' % (
                    TYPES[type_id]["label"], name, only))

    gateway.set_conf(ns, app, conf, stanza, dict((s["name"], s["value"]) for s in settings))

    after = _own_history(gateway.read_own_conf(conf, app, reader_user), stanza, only)
    missing = []
    for item in settings:
        seen = dict(after.get(item["name"], []))
        if layer not in seen or _squash(seen[layer]) != _squash(item["value"]):
            missing.append(item["name"])
    if missing:
        logger.warning("user=%s action=settings type=%s app=%s owner_ns=%s name=%s keys=%s did not reach the %s file",
                       user, type_id, app, ns, json.dumps(name), json.dumps(missing), layer)
        return "error", ('splunkd accepted the change to "%s" but %s did not reach %s\'s %s file; '
                         "nothing was changed for %s." % (name, ", ".join('"%s"' % m for m in missing), app,
                                                          "private" if layer == "user" else "local",
                                                          "them" if len(missing) > 1 else "it"))
    # Names only: a value can be a search, a path or a credential in a custom key.
    logger.info("user=%s action=settings type=%s app=%s owner_ns=%s name=%s keys=%s",
                user, type_id, app, ns, json.dumps(name), json.dumps([s["name"] for s in settings]))
    return "applied", 'Changed %s of %s "%s".' % (plural_settings(len(settings)), label, name)


def plural_settings(count):
    return "%d setting%s" % (count, "" if count == 1 else "s")


def _apply_one(gateway, change, user):
    """Apply one object's edits. Returns (status, message, moved_to).

    Settings go first, so the values checked against ``previous`` are the
    ones the page saw before anything moved. Each later step reports what
    already happened if it fails.
    """
    if not change.get("settings"):
        return _apply_object(gateway, change, user)
    status, message = _apply_settings(gateway, change, user)
    if status == "error":
        return status, message, None
    change["settings_applied"] = True
    if not (change["move_to"] or change["copy_to"] or change["acl"]):
        return status, message, None
    try:
        rest = _apply_object(gateway, change, user)
    except GatewayError as error:
        return ("error", 'The settings of "%s" were changed, but the rest was not: %s' % (change["name"], error), None)
    if rest[0] == "error":
        return "error", 'The settings of "%s" were changed, but the rest was not: %s' % (change["name"], rest[1]), rest[2]
    return "applied", "%s %s" % (message, rest[1]), rest[2]


def _apply_object(gateway, change, user):
    """Apply one object's move, copy, permissions or delete. (status, message, moved_to)."""
    type_id, ns, app, name = change["type"], change["ns"], change["app"], change["name"]
    label = TYPES[type_id]["label"].lower()
    path = object_path(type_id, ns, app, name)
    try:
        entry = get_in_app(gateway, type_id, ns, app, name)
    except GatewayError as error:
        if error.status == 404:
            return ("error", '"%s" is no longer in "%s": it was moved, renamed or deleted elsewhere. '
                    "Reload to see where it is now." % (name, app), None)
        raise
    links = entry.get("links") or {}

    removable = _is_true((entry.get("acl") or {}).get("removable", True))
    if change["delete"]:
        if "remove" not in links or not removable:
            return ("error", '"%s" ships in the "%s" app\'s default folder, so it cannot be deleted.' % (name, app), None)
        gateway.delete_object(path)
        logger.info("user=%s action=delete type=%s app=%s owner_ns=%s name=%s",
                    user, type_id, app, ns, json.dumps(name))
        return ("applied", 'Deleted %s "%s" from "%s".' % (label, name, app), None)

    if change["copy_to"]:
        status, message = _copy_one(gateway, change, entry, user)
        if status == "error" or not change["acl"]:
            return status, message, None

    moved_to = None
    if change["move_to"]:
        if "move" not in links or not removable:
            change["copy_instead"] = TYPES[type_id]["copy"] is not None
            return ("error", '"%s" ships in the "%s" app\'s default folder, so it cannot be moved.%s' % (
                name, app, " Copy it instead." if change["copy_instead"] else ""), None)
        # ``user`` keeps the object in its namespace: the owner's for a
        # private object, nobody's for a shared one (observed: the owner and
        # sharing are kept across the move).
        try:
            gateway.move_object(path, change["move_to"], ns)
        except GatewayError as error:
            # splunkd's own refusal for an object in a default folder, should
            # one reach it: say so in plain words, and let the page offer a copy.
            if "cannot be deleted" not in str(error):
                raise
            change["copy_instead"] = TYPES[type_id]["copy"] is not None
            return ("error", '"%s" ships in the "%s" app\'s default folder, so splunkd will not move it.%s' % (
                name, app, " Copy it instead." if change["copy_instead"] else ""), None)
        logger.info("user=%s action=move type=%s app=%s to=%s owner_ns=%s name=%s",
                    user, type_id, app, change["move_to"], ns, json.dumps(name))
        moved_to = app = change["move_to"]
        path = object_path(type_id, ns, app, name)

    if change["acl"]:
        # Moved or copied already: a refusal now must say that part was done.
        done = ('Moved to "%s"' % moved_to if moved_to else
                'Copied to "%s"' % change["copy_to"] if change.get("copied") else None)
        acl = entry.get("acl") or {}
        if not _is_true(acl.get("can_change_perms", True)):
            message = 'Your account cannot change the permissions of "%s".' % name
            return ("error", message if not done else "%s, but %s" % (
                done, message[0].lower() + message[1:]), moved_to)
        try:
            gateway.set_acl(path, acl_postargs(change["acl"]))
        except GatewayError as error:
            if not done:
                raise
            return ("error", "%s, but %s permissions were not changed: %s" % (
                done, "the original's" if change.get("copied") else "its", error), moved_to)
        logger.info("user=%s action=acl type=%s app=%s owner_ns=%s name=%s acl=%s",
                    user, type_id, app, ns, json.dumps(name), json.dumps(change["acl"], sort_keys=True))

    if change["copy_to"]:
        return ("applied", 'Copied %s "%s" to "%s" and changed the original\'s permissions.' % (
            label, name, change["copy_to"]), None)
    if moved_to and change["acl"]:
        return ("applied", 'Moved %s "%s" to "%s" and changed its permissions.' % (label, name, moved_to), moved_to)
    if moved_to:
        return ("applied", 'Moved %s "%s" to "%s".' % (label, name, moved_to), moved_to)
    return ("applied", 'Changed the permissions of %s "%s".' % (label, name), None)


def submit_changes(gateway, raw_changes, user="unknown", raw_apps=None):
    """Create the requested apps, then apply every change, and report each outcome.

    splunkd has no transaction across objects, so a failure on one does not
    stop the rest; the page keeps the failed ones pending to retry. Apps come
    first so that a change can copy or move an object into one of them. A
    change aimed at an app that could not be created is not attempted.
    """
    if raw_apps is not None and not isinstance(raw_apps, list):
        raise EasyAdminError("'apps' must be a list.")
    wants_apps = bool(raw_apps)
    if wants_apps and not can_create_apps({"capabilities": gateway.caller_capabilities()}):
        # splunkd would refuse as well; saying so first creates nothing.
        raise EasyAdminError("Creating apps needs the admin_all_objects or edit_local_apps capability.",
                             status=403)
    specs = parse_new_apps(raw_apps, [a.get("name") or "" for a in gateway.list_apps()]) if wants_apps else []
    changes = parse_changes(raw_changes, allow_empty=wants_apps)
    if not specs and not changes:
        raise EasyAdminError("There is nothing to apply.")
    app_results = [_create_one(gateway, spec, user) for spec in specs]
    not_created = set(r["name"] for r in app_results if r["status"] != "applied")
    results = []
    for change in changes:
        target = change["move_to"] or change["copy_to"]
        if target in not_created:
            results.append({"key": change["key"], "status": "error", "moved_to": None, "copied_to": None,
                            "copy_instead": False, "settings_applied": False,
                            "message": '"%s" was not %s: the app "%s" was not created.' % (
                                change["name"], "moved" if change["move_to"] else "copied", target)})
            continue
        try:
            status, message, moved_to = _apply_one(gateway, change, user)
        except GatewayError as error:
            logger.warning("user=%s object=%s change refused: status=%s %s",
                           user, json.dumps(change["key"]), error.status, error)
            status, message, moved_to = "error", '"%s": %s' % (change["name"], error), None
        # copied_to tells the page a copy exists even when a later step of
        # the same change failed, so it stops staging the copy.
        # copy_instead: the move was refused because the object cannot be
        # moved, and it can be copied; the page offers to stage a copy.
        results.append({"key": change["key"], "status": status, "message": message,
                        "moved_to": moved_to, "copied_to": change["copy_to"] if change.get("copied") else None,
                        "copy_instead": bool(change.get("copy_instead")),
                        # The settings were written even if a later step failed.
                        "settings_applied": bool(change.get("settings_applied"))})
    everything = app_results + results
    return {
        "apps": app_results,
        "results": results,
        "applied": sum(1 for r in everything if r["status"] == "applied"),
        "failed": sum(1 for r in everything if r["status"] == "error"),
        "restart_required": _restart_required(gateway),
    }


def _restart_required(gateway):
    """Whether splunkd now asks for a restart; a failed check never fails the apply."""
    try:
        return bool(gateway.restart_required())
    except GatewayError as error:
        logger.warning("Could not check whether a restart is required: %s", error)
        return False


def request_size(body):
    """The size of a POST body in bytes (UTF-8 for text), 0 for no body."""
    if body is None:
        return 0
    if isinstance(body, bytes):
        return len(body)
    return len(body.encode("utf-8", "replace"))


def megabytes(count):
    """A byte count for a message: "16 MB", "17.2 MB"; one decimal unless whole."""
    value = round(count / (1024.0 * 1024.0), 1)
    return ("%d MB" % value) if value == int(value) else ("%.1f MB" % value)


def check_request_size(body, user="unknown"):
    """Refuse a body over MAX_REQUEST_BYTES before it is parsed (HTTP 413)."""
    size = request_size(body)
    if size > MAX_REQUEST_BYTES:
        logger.warning("user=%s action=apply refused: request is %d bytes, over the %d byte limit",
                       user, size, MAX_REQUEST_BYTES)
        raise EasyAdminError(
            "This Apply is %s, and one Apply can send at most %s. Apply the changes in smaller batches."
            % (megabytes(size), megabytes(MAX_REQUEST_BYTES)), status=413)
    return size


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
                found = get_in_app(gateway, type_id, ns, app, name, full=True)
                return 200, add_explicit(build_details(type_id, found), gateway, type_id, ns, app, name, found)
            return 200, read_model(gateway)
        if method == "POST":
            check_request_size(body, user)
            document = extract_document(body)
            return 200, submit_changes(gateway, document.get("changes"), user=user,
                                       raw_apps=document.get("apps"))
        return 405, error_payload("Method %s is not supported." % method)
    except EasyAdminError as error:
        return error.status, error_payload(str(error))
    except GatewayError as error:
        return error.status, error_payload(str(error))
