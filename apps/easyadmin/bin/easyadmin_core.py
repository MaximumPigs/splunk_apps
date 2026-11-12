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

"""Pure logic for Easy Admin role management.

Nothing here imports from Splunk, so all of it is unit tested without a Splunk
install. Everything that talks to splunkd goes through a *gateway* object the
caller supplies (see easyadmin_rest.SplunkdGateway); tests pass a fake one.

A gateway provides:

    list_roles()            -> [{"name": str, "content": dict}, ...]
    list_indexes()          -> [{"name": str, "content": dict}, ...]
    list_capabilities()     -> [str, ...]   every capability splunkd defines
    current_context()       -> {"capabilities": [...], "roles": [...]}
    get_role(name)          -> content dict of one role
    update_role(name, {field: [value, ...] or "value"})

and raises GatewayError when splunkd refuses a call.

The page has two kinds of tab:

* matrix tabs: multi-valued attributes, one checkbox per role and item. A
  change grants or revokes one item and is applied as a delta.
* settings tabs: one editable value per role and attribute. A change carries
  the value the page loaded; it is refused if the role has changed since.

Must remain valid on Python 3.9 as well as 3.13: no match statements, no
"X | Y" annotations.
"""

import json
import logging
import re
from collections import OrderedDict

try:  # Python 3
    from urllib.parse import parse_qs
except ImportError:  # pragma: no cover - Splunk no longer ships Python 2
    from urlparse import parse_qs

logger = logging.getLogger("easyadmin")

# ---------------------------------------------------------------- the tabs
#
# Attribute names are the writable fields splunkd 10.6 lists for
# authorization/roles (its _new endpoint's optionalFields). The labels are the
# page's wording; each column also shows the attribute name, so nothing is
# hidden behind a paraphrase.

MATRIX_TABS = (
    {
        "id": "indexes",
        "label": "Indexes",
        "columns": "indexes",
        # Index attributes accept * wildcards, which the page explains.
        "wildcards": True,
        "fields": (
            ("srchIndexesAllowed", "Searchable indexes"),
            ("srchIndexesDefault", "Indexes searched by default"),
            ("srchIndexesDisallowed", "Indexes never searchable"),
            ("deleteIndexesAllowed", "Indexes events can be deleted from"),
        ),
    },
    {
        "id": "capabilities",
        "label": "Capabilities",
        "columns": "capabilities",
        "wildcards": False,
        "fields": (("capabilities", "Capabilities"),),
    },
    {
        "id": "inheritance",
        "label": "Inheritance",
        "columns": "roles",
        "wildcards": False,
        "fields": (
            ("imported_roles", "Inherits from roles"),
            ("grantable_roles", "Roles it can grant"),
        ),
    },
)

# kind: "int" (whole number, may be negative), "flag" (0 or 1), "text" (any
# string, may be empty) or "list" (several values, edited comma-separated).
SETTINGS_TABS = (
    {
        "id": "limits",
        "label": "Search limits",
        "fields": (
            ("srchJobsQuota", "Search jobs quota", "int"),
            ("rtSrchJobsQuota", "Real-time search jobs quota", "int"),
            ("cumulativeSrchJobsQuota", "Cumulative search jobs quota", "int"),
            ("cumulativeRTSrchJobsQuota", "Cumulative real-time search jobs quota", "int"),
            ("queuedSearchQuota", "Queued search quota", "int"),
            ("srchDiskQuota", "Search disk quota", "int"),
            ("srchTimeWin", "Search time window", "int"),
            ("srchTimeEarliest", "Earliest search time", "int"),
            ("srchMinScheduleInterval", "Minimum schedule interval", "int"),
            ("srchAllowAdvancedCron", "Advanced cron allowed", "flag"),
            ("srchFilter", "Search filter", "text"),
            ("defaultApp", "Default app", "text"),
        ),
    },
    {
        "id": "federated",
        "label": "Federated and KV store",
        "fields": (
            ("federatedProviders", "Federated providers", "list"),
            ("srchFederatedProvidersAllowed", "Searchable federated providers", "list"),
            ("srchFederatedProvidersDefault", "Federated providers searched by default", "list"),
            ("fieldFilterExemption", "Field filter exemptions", "list"),
            ("kvstore_create.deny_list", "KV store create deny list", "list"),
            ("kvstore_create.implicit_deny_list", "KV store create implicit deny list", "list"),
            ("kvstore_update.deny_list", "KV store update deny list", "list"),
            ("kvstore_update.implicit_deny_list", "KV store update implicit deny list", "list"),
            ("kvstore_delete.deny_list", "KV store delete deny list", "list"),
            ("kvstore_delete.implicit_deny_list", "KV store delete implicit deny list", "list"),
        ),
    },
)

MATRIX_FIELDS = OrderedDict(
    (name, tab) for tab in MATRIX_TABS for name, _label in tab["fields"])
SETTING_KINDS = OrderedDict(
    (name, kind) for tab in SETTINGS_TABS for name, _label, kind in tab["fields"])

# Holding either capability lets a user edit roles. Splunk Cloud administrators
# (sc_admin) have edit_roles_grantable rather than edit_roles.
EDIT_CAPABILITIES = ("edit_roles", "edit_roles_grantable")

# One submit carries the whole page's pending edits. The cap only stops a
# runaway or hostile payload from making the handler issue unbounded writes.
MAX_CHANGES = 5000

# Longest single name or value accepted in a change. This bounds what gets
# logged and forwarded; splunkd applies its own, tighter limits.
MAX_VALUE_LENGTH = 4096

INT_RE = re.compile(r"^-?[0-9]+$")


class EasyAdminError(Exception):
    """A request this app rejects itself, before anything reaches splunkd."""

    def __init__(self, message, status=400):
        super(EasyAdminError, self).__init__(message)
        self.status = status


class GatewayError(Exception):
    """splunkd refused or failed a call made on the user's behalf."""

    def __init__(self, message, status=502):
        super(GatewayError, self).__init__(message)
        self.status = status


def as_list(value):
    """Normalise a multi-valued REST field to a list of non-empty strings.

    splunkd returns a list for a multi-valued attribute with several values,
    but a bare string when it has one (observed: imported_roles = "user"), and
    an unset attribute can arrive as None, "" or be absent altogether.
    """
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value if item is not None and str(item) != ""]
    text = str(value)
    return [text] if text else []


def as_text(value):
    """Normalise a single-valued REST field to a string ("" when unset)."""
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        # A scalar attribute should never be a list; join rather than lose data.
        return ",".join(as_list(value))
    if isinstance(value, bool):
        return "1" if value else "0"
    return str(value)


def is_wildcard(name):
    return "*" in name


def pattern_matches(pattern, item):
    """True when a role's index entry covers ``item``.

    Mirrors how Splunk reads srchIndexesAllowed: ``*`` is the only wildcard,
    and a pattern that does not itself start with an underscore never matches
    an internal index. That is why roles carry ``*`` and ``_*`` separately.
    """
    if not is_wildcard(pattern):
        return pattern == item
    if item.startswith("_") and not pattern.startswith("_"):
        return False
    regex = ".*".join(re.escape(part) for part in pattern.split("*"))
    return re.match("^%s$" % regex, item) is not None


def _is_true(value):
    """splunkd JSON booleans arrive as bool, 0/1 or "0"/"1" depending on field."""
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "t", "yes")


# ------------------------------------------------------------------ reading

def _column(name, kind, internal=False, disabled=False):
    return {"name": name, "kind": kind, "internal": internal, "disabled": disabled}


def _column_sort_key(column):
    # Wildcards first (they explain the most), then ordinary entries, then
    # internal indexes, then names splunkd does not know about.
    order = {"wildcard": 0, "known": 1, "unknown": 3}[column["kind"]]
    if column["kind"] == "known" and column["internal"]:
        order = 2
    return (order, column["name"].lower())


def _effective_by_import(explicit, imported, columns, wildcards):
    """Explain why a role reaches columns it does not list explicitly.

    Returns {column name: reason}. The page ticks only explicit entries,
    because those are what a save can change; this map lets it mark the cells
    that are nevertheless effective, so an empty checkbox is not read as "no".
    """
    explicit_set = set(explicit)
    imported_set = set(imported)
    explicit_patterns = [name for name in explicit if is_wildcard(name)] if wildcards else []
    imported_patterns = [name for name in imported if is_wildcard(name)] if wildcards else []
    reasons = {}
    for name in columns:
        if name in explicit_set:
            continue
        if name in imported_set:
            reasons[name] = "Inherited from an imported role"
            continue
        if not wildcards or is_wildcard(name):
            # A wildcard column is only "effective" when listed verbatim.
            continue
        match = next((p for p in explicit_patterns if pattern_matches(p, name)), None)
        if match is not None:
            reasons[name] = "Matched by wildcard %s on this role" % match
            continue
        match = next((p for p in imported_patterns if pattern_matches(p, name)), None)
        if match is not None:
            reasons[name] = "Matched by wildcard %s inherited from an imported role" % match
    return reasons


def _inherited_roles(role_name, imports):
    """Roles reached through imported roles of imported roles.

    Returns {role: the directly imported role it comes through}. splunkd
    reports only the direct list in imported_roles, so the chain is walked
    here. Guards against cycles, which splunkd should refuse but which would
    otherwise loop forever.
    """
    reasons = {}
    for direct in imports.get(role_name, []):
        stack = list(imports.get(direct, []))
        seen = {role_name, direct}
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            reasons.setdefault(current, "Inherited through %s" % direct)
            stack.extend(imports.get(current, []))
    return reasons


def _matrix_tab(tab, roles, known_columns):
    """Build one matrix tab: its columns and every role's cells."""
    columns = OrderedDict()
    for column in known_columns:
        columns.setdefault(column["name"], column)

    field_names = [name for name, _label in tab["fields"]]
    for role in roles:
        content = role["content"]
        for field in field_names:
            for item in as_list(content.get(field)) + as_list(content.get("imported_" + field)):
                if item not in columns:
                    kind = "wildcard" if tab["wildcards"] and is_wildcard(item) else "unknown"
                    internal = tab["columns"] == "indexes" and item.startswith("_")
                    columns[item] = _column(item, kind, internal=internal)

    ordered = sorted(columns.values(), key=_column_sort_key)
    column_names = [column["name"] for column in ordered]

    imports = dict((role["name"], as_list(role["content"].get("imported_roles"))) for role in roles)
    cells = OrderedDict()
    for role in roles:
        content = role["content"]
        per_field = OrderedDict()
        for field in field_names:
            explicit = as_list(content.get(field))
            if field == "imported_roles":
                # splunkd has no imported_imported_roles; derive the chain.
                effective = dict((name, reason) for name, reason
                                 in _inherited_roles(role["name"], imports).items()
                                 if name not in explicit)
            else:
                effective = _effective_by_import(
                    explicit, as_list(content.get("imported_" + field)),
                    column_names, tab["wildcards"])
            per_field[field] = {"explicit": explicit, "effective": effective}
        cells[role["name"]] = per_field

    return {
        "id": tab["id"],
        "label": tab["label"],
        "type": "matrix",
        "fields": [{"name": name, "label": label} for name, label in tab["fields"]],
        "columns": ordered,
        "cells": cells,
    }


def _settings_tab(tab, roles):
    """Build one settings tab: every role's current and imported values."""
    values = OrderedDict()
    for role in roles:
        content = role["content"]
        per_field = OrderedDict()
        for field, _label, kind in tab["fields"]:
            if kind == "list":
                value = as_list(content.get(field))
                imported = as_list(content.get("imported_" + field))
            else:
                value = as_text(content.get(field))
                imported = as_text(content.get("imported_" + field)) if (
                    "imported_" + field) in content else None
            per_field[field] = {"value": value, "imported": imported}
        values[role["name"]] = per_field
    return {
        "id": tab["id"],
        "label": tab["label"],
        "type": "settings",
        "fields": [{"name": name, "label": label, "kind": kind}
                   for name, label, kind in tab["fields"]],
        "values": values,
    }


def build_model(role_entries, index_entries, capability_names, context):
    """Shape roles, indexes and capabilities into the payload the page renders."""
    roles = []
    for entry in role_entries:
        if entry.get("name"):
            roles.append({"name": entry["name"], "content": entry.get("content") or {}})
    roles.sort(key=lambda role: role["name"].lower())

    index_columns = []
    for entry in index_entries:
        name = entry.get("name")
        if not name:
            continue
        content = entry.get("content") or {}
        index_columns.append(_column(
            name, "known",
            internal=name.startswith("_") or _is_true(content.get("isInternal")),
            disabled=_is_true(content.get("disabled"))))

    known = {
        "indexes": index_columns,
        "capabilities": [_column(name, "known") for name in as_list(capability_names)],
        "roles": [_column(role["name"], "known") for role in roles],
    }

    tabs = [_matrix_tab(tab, roles, known[tab["columns"]]) for tab in MATRIX_TABS]
    tabs.extend(_settings_tab(tab, roles) for tab in SETTINGS_TABS)

    context = context or {}
    return {
        "can_edit": any(cap in EDIT_CAPABILITIES for cap in as_list(context.get("capabilities"))),
        "user_roles": as_list(context.get("roles")),
        "roles": [{"name": role["name"],
                   "imported_roles": as_list(role["content"].get("imported_roles"))}
                  for role in roles],
        "tabs": tabs,
    }


def read_model(gateway):
    return build_model(gateway.list_roles(), gateway.list_indexes(),
                       gateway.list_capabilities(), gateway.current_context())


# ------------------------------------------------------------------ changes

def _clean_string(value, what, position, allow_empty=False):
    if not isinstance(value, str):
        raise EasyAdminError("Change %d: %s must be a string." % (position, what))
    if value != value.strip() or (not value and not allow_empty):
        raise EasyAdminError("Change %d: %s must be non-empty, without surrounding spaces."
                             % (position, what))
    if len(value) > MAX_VALUE_LENGTH:
        raise EasyAdminError("Change %d: %s is longer than %d characters."
                             % (position, what, MAX_VALUE_LENGTH))
    return value


def _clean_setting(value, kind, field, position):
    """Validate a settings value against its kind; returns the value to write."""
    if kind == "list":
        if not isinstance(value, list):
            raise EasyAdminError("Change %d: %s takes a list of values." % (position, field))
        cleaned = []
        for item in value:
            item = _clean_string(item, field + " value", position)
            if item not in cleaned:
                cleaned.append(item)
        return cleaned
    text = _clean_string(value, field, position, allow_empty=(kind == "text"))
    if kind == "int" and not INT_RE.match(text):
        raise EasyAdminError("Change %d: %s must be a whole number." % (position, field))
    if kind == "flag" and text not in ("0", "1"):
        raise EasyAdminError("Change %d: %s must be 0 or 1." % (position, field))
    return text


def parse_changes(raw):
    """Validate a submitted change list and group it by role.

    Two shapes, by field:

    * matrix field:   ``{"role", "field", "item", "grant": bool}``
    * settings field: ``{"role", "field", "value", "previous"}``, where
      ``previous`` is the value the page showed when it loaded.

    Returns ``OrderedDict(role -> {"matrix": {field -> {"grant": [...],
    "revoke": [...]}}, "settings": {field -> (value, previous)}})`` in
    first-seen order. Raises EasyAdminError on anything malformed, so a bad
    payload changes nothing at all.
    """
    if not isinstance(raw, list):
        raise EasyAdminError("'changes' must be a list.")
    if not raw:
        raise EasyAdminError("No changes were submitted.")
    if len(raw) > MAX_CHANGES:
        raise EasyAdminError("Too many changes in one submit (%d, limit %d)."
                             % (len(raw), MAX_CHANGES))

    seen = {}
    plan = OrderedDict()
    for position, change in enumerate(raw, 1):
        if not isinstance(change, dict):
            raise EasyAdminError("Change %d is not an object." % position)
        role = _clean_string(change.get("role"), "role", position)
        field = change.get("field")
        per_role = plan.setdefault(role, {"matrix": OrderedDict(), "settings": OrderedDict()})

        if field in MATRIX_FIELDS:
            item = _clean_string(change.get("item"), "item", position)
            grant = change.get("grant")
            if not isinstance(grant, bool):
                raise EasyAdminError("Change %d: grant must be true or false." % position)
            key = (role, field, item)
            if key in seen:
                if seen[key] != grant:
                    raise EasyAdminError("Change %d both grants and revokes %s on role %s."
                                         % (position, item, role))
                continue  # An exact repeat is harmless; apply it once.
            seen[key] = grant
            delta = per_role["matrix"].setdefault(field, {"grant": [], "revoke": []})
            delta["grant" if grant else "revoke"].append(item)
        elif field in SETTING_KINDS:
            kind = SETTING_KINDS[field]
            value = _clean_setting(change.get("value"), kind, field, position)
            previous = change.get("previous")
            if kind == "list":
                previous = as_list(previous) if isinstance(previous, list) else None
            elif not isinstance(previous, str):
                previous = None
            if previous is None:
                raise EasyAdminError("Change %d: previous must be the value the page loaded."
                                     % position)
            if field in per_role["settings"]:
                raise EasyAdminError("Change %d sets %s on role %s twice." % (position, field, role))
            per_role["settings"][field] = (value, previous)
        else:
            raise EasyAdminError("Change %d: %r is not a role attribute this app edits."
                                 % (position, field))

    # A role whose only changes were exact repeats can be left empty: drop it.
    return OrderedDict((role, entry) for role, entry in plan.items()
                       if entry["matrix"] or entry["settings"])


def apply_delta(current, grant, revoke):
    """Return ``current`` with ``revoke`` removed and ``grant`` appended.

    Existing order is preserved and duplicates are dropped. (splunkd stores
    these lists sorted anyway, but the request should not depend on that.)
    """
    revoked = set(revoke)
    result = []
    for name in list(current) + list(grant):
        if name not in revoked and name not in result:
            result.append(name)
    return result


def _plan_role_update(content, entry):
    """Work out the fields to write for one role, or raise on a stale setting.

    Returns (update, conflicts): ``update`` maps field -> new value for every
    field that actually changes, ``conflicts`` lists settings changed by
    someone else since the page loaded.
    """
    update = OrderedDict()
    for field, delta in entry["matrix"].items():
        current = as_list(content.get(field))
        wanted = apply_delta(current, delta["grant"], delta["revoke"])
        if set(wanted) != set(current):
            update[field] = wanted

    conflicts = []
    for field, (value, previous) in entry["settings"].items():
        if SETTING_KINDS[field] == "list":
            current = as_list(content.get(field))
            if set(current) != set(previous):
                conflicts.append(field)
            elif set(value) != set(current):
                update[field] = value
        else:
            current = as_text(content.get(field))
            if current != previous:
                conflicts.append(field)
            elif value != current:
                update[field] = value
    return update, conflicts


def submit_changes(gateway, raw_changes, user="unknown"):
    """Apply a validated change list, one write per role.

    Checkbox changes are deltas: each role is re-read just before its write
    and only the submitted items are altered, so an edit made elsewhere since
    the page loaded is not overwritten. A settings change replaces the value,
    so it is refused for that role if the value is no longer what the page
    loaded; the person reloads and decides again.

    splunkd has no transaction across roles, so this is not atomic. Every role
    is attempted and reported individually; one refusal does not stop the rest.
    """
    plan = parse_changes(raw_changes)
    results = []
    for role, entry in plan.items():
        try:
            content = gateway.get_role(role)
            update, conflicts = _plan_role_update(content, entry)
            if conflicts:
                results.append({"role": role, "status": "error", "message":
                                "Changed elsewhere since the page loaded: %s. Reload and try again."
                                % ", ".join(conflicts)})
                continue
            if not update:
                results.append({"role": role, "status": "unchanged",
                                "message": "Role already matched the requested state."})
                continue
            gateway.update_role(role, update)
        except GatewayError as error:
            logger.warning("user=%s role=%s update refused: status=%s %s",
                           user, role, error.status, error)
            results.append({"role": role, "status": "error", "message": str(error)})
            continue
        # An audit trail of who changed which role, in the app's own log.
        logger.info("user=%s role=%s updated %s", user, role, json.dumps(update, sort_keys=True))
        results.append({"role": role, "status": "updated", "message": ""})

    return {
        "results": results,
        "updated": sum(1 for r in results if r["status"] == "updated"),
        "unchanged": sum(1 for r in results if r["status"] == "unchanged"),
        "failed": sum(1 for r in results if r["status"] == "error"),
    }


def extract_changes(body):
    """Pull the change list out of a POST body.

    The page sends JSON (``{"changes": [...]}``). A form-encoded body with a
    ``changes`` field holding that JSON list is accepted too, because that is
    what generic REST clients (and this repo's live tests) send.
    """
    if isinstance(body, bytes):
        body = body.decode("utf-8", "replace")
    text = (body or "").strip()
    if not text:
        raise EasyAdminError("Request body is empty.")
    try:
        if text.startswith("{"):
            document = json.loads(text)
            return document.get("changes")
        fields = parse_qs(text, keep_blank_values=True)
        if "changes" not in fields:
            raise EasyAdminError("Request has no 'changes' field.")
        return json.loads(fields["changes"][0])
    except ValueError:
        raise EasyAdminError("Request body is not valid JSON.")


def error_payload(message):
    # Same shape as splunkd's own errors, so clients need one parser.
    return {"messages": [{"type": "ERROR", "text": message}]}


def handle_request(method, body, gateway, user="unknown"):
    """Route one REST call. Returns ``(http_status, json_serialisable_payload)``."""
    method = (method or "").upper()
    try:
        if method == "GET":
            return 200, read_model(gateway)
        if method == "POST":
            return 200, submit_changes(gateway, extract_changes(body), user=user)
        return 405, error_payload("Method %s is not supported." % method)
    except EasyAdminError as error:
        return error.status, error_payload(str(error))
    except GatewayError as error:
        return error.status, error_payload(str(error))
