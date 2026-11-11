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

"""Pure logic for Easy Admin: the role x index permission matrix.

Nothing here imports from Splunk, so all of it is unit tested without a Splunk
install. Everything that talks to splunkd goes through a *gateway* object the
caller supplies (see easyadmin_rest.SplunkdGateway); tests pass a fake one.

A gateway provides:

    list_roles()            -> [{"name": str, "content": dict}, ...]
    list_indexes()          -> [{"name": str, "content": dict}, ...]
    capabilities()          -> [str, ...]   of the calling user
    get_role(name)          -> content dict of one role
    update_role(name, {field: [index, ...]})

and raises GatewayError when splunkd refuses a call.

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

# The role attributes this page edits, in display order. Both are multi-valued
# lists of index names or wildcard patterns on authorization/roles.
FIELDS = ("srchIndexesAllowed", "srchIndexesDefault")

FIELD_LABELS = {
    "srchIndexesAllowed": "Searchable indexes",
    "srchIndexesDefault": "Indexes searched by default",
}

# Holding either capability lets a user edit roles. Splunk Cloud administrators
# (sc_admin) have edit_roles_grantable rather than edit_roles.
EDIT_CAPABILITIES = ("edit_roles", "edit_roles_grantable")

# One submit carries the whole page's pending edits. The cap only stops a
# runaway or hostile payload from making the handler issue unbounded writes.
MAX_CHANGES = 5000

# Longest index name or pattern accepted in a change. Splunk's own limit on an
# index name is far lower; this just bounds what gets logged and forwarded.
MAX_NAME_LENGTH = 512


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

    splunkd returns a list for multi-valued attributes, but an attribute that
    was never set can arrive as None, an empty string or be absent altogether.
    """
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value if item is not None and str(item) != ""]
    text = str(value)
    return [text] if text else []


def is_wildcard(name):
    return "*" in name


def pattern_matches(pattern, index):
    """True when a role's index entry covers ``index``.

    Mirrors how Splunk reads srchIndexesAllowed: ``*`` is the only wildcard,
    and a pattern that does not itself start with an underscore never matches
    an internal index. That is why roles carry ``*`` and ``_*`` separately.
    """
    if not is_wildcard(pattern):
        return pattern == index
    if index.startswith("_") and not pattern.startswith("_"):
        return False
    regex = ".*".join(re.escape(part) for part in pattern.split("*"))
    return re.match("^%s$" % regex, index) is not None


def _is_true(value):
    """splunkd JSON booleans arrive as bool, 0/1 or "0"/"1" depending on field."""
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "t", "yes")


def _row_sort_key(row):
    # Wildcards first (they explain the most), then ordinary indexes, then
    # internal ones, then names this search head does not know about.
    order = {"wildcard": 0, "index": 1, "unknown": 3}[row["kind"]]
    if row["kind"] == "index" and row["internal"]:
        order = 2
    return (order, row["name"].lower())


def _effective(explicit, imported, row_names):
    """Explain why a role reaches rows it does not list explicitly.

    Returns {row name: reason}. The page ticks only explicit entries, because
    those are what a save can change; this map lets it mark the cells that are
    nevertheless effective, so an empty checkbox is not read as "no access".
    """
    explicit_set = set(explicit)
    imported_set = set(imported)
    explicit_patterns = [name for name in explicit if is_wildcard(name)]
    imported_patterns = [name for name in imported if is_wildcard(name)]
    reasons = {}
    for name in row_names:
        if name in explicit_set:
            continue
        if name in imported_set:
            reasons[name] = "Inherited from an imported role"
            continue
        if is_wildcard(name):
            # A wildcard row is only "effective" when listed verbatim.
            continue
        match = next((p for p in explicit_patterns if pattern_matches(p, name)), None)
        if match is not None:
            reasons[name] = "Matched by wildcard %s on this role" % match
            continue
        match = next((p for p in imported_patterns if pattern_matches(p, name)), None)
        if match is not None:
            reasons[name] = "Matched by wildcard %s inherited from an imported role" % match
    return reasons


def build_matrix(role_entries, index_entries, capabilities):
    """Shape roles and indexes into the payload the page renders.

    Rows are every index splunkd reported plus every entry any role holds that
    is not one of those: wildcard patterns, and names of indexes this search
    head has no definition for (common when indexes live only on indexers).
    Keeping those as rows means every entry on every role can be unticked.
    """
    rows = OrderedDict()
    for entry in index_entries:
        name = entry.get("name")
        if not name or name in rows:
            continue
        content = entry.get("content") or {}
        rows[name] = {
            "name": name,
            "kind": "index",
            "internal": name.startswith("_") or _is_true(content.get("isInternal")),
            "datatype": content.get("datatype") or "event",
            "disabled": _is_true(content.get("disabled")),
        }

    roles = []
    for entry in role_entries:
        name = entry.get("name")
        if not name:
            continue
        content = entry.get("content") or {}
        role = {"name": name, "imported_roles": as_list(content.get("imported_roles"))}
        for field in FIELDS:
            role[field] = {
                "explicit": as_list(content.get(field)),
                "imported": as_list(content.get("imported_" + field)),
            }
            for item in role[field]["explicit"] + role[field]["imported"]:
                if item not in rows:
                    rows[item] = {
                        "name": item,
                        "kind": "wildcard" if is_wildcard(item) else "unknown",
                        "internal": item.startswith("_"),
                        "datatype": None,
                        "disabled": False,
                    }
        roles.append(role)

    indexes = sorted(rows.values(), key=_row_sort_key)
    row_names = [row["name"] for row in indexes]
    for role in roles:
        for field in FIELDS:
            cell = role[field]
            cell["effective"] = _effective(cell["explicit"], cell.pop("imported"), row_names)

    roles.sort(key=lambda role: role["name"].lower())
    return {
        "fields": [{"name": field, "label": FIELD_LABELS[field]} for field in FIELDS],
        "can_edit": any(cap in EDIT_CAPABILITIES for cap in as_list(capabilities)),
        "indexes": indexes,
        "roles": roles,
    }


def _clean_name(value, what, position):
    if not isinstance(value, str) or not value or value != value.strip():
        raise EasyAdminError("Change %d: %s must be a non-empty string without surrounding spaces."
                             % (position, what))
    if len(value) > MAX_NAME_LENGTH:
        raise EasyAdminError("Change %d: %s is longer than %d characters."
                             % (position, what, MAX_NAME_LENGTH))
    return value


def parse_changes(raw):
    """Validate a submitted change list and group it by role.

    Each change is one cell of the matrix: ``{"role", "field", "index",
    "grant"}``. Returns ``OrderedDict(role -> {field -> {"grant": [...],
    "revoke": [...]}})`` in first-seen order. Raises EasyAdminError on anything
    malformed, so a bad payload changes nothing at all.
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
        role = _clean_name(change.get("role"), "role", position)
        index = _clean_name(change.get("index"), "index", position)
        field = change.get("field")
        if field not in FIELDS:
            raise EasyAdminError("Change %d: field must be one of %s."
                                 % (position, ", ".join(FIELDS)))
        grant = change.get("grant")
        if not isinstance(grant, bool):
            raise EasyAdminError("Change %d: grant must be true or false." % position)

        key = (role, field, index)
        if key in seen:
            if seen[key] != grant:
                raise EasyAdminError(
                    "Change %d both grants and revokes %s on role %s." % (position, index, role))
            continue  # An exact repeat is harmless; apply it once.
        seen[key] = grant

        per_field = plan.setdefault(role, OrderedDict())
        delta = per_field.setdefault(field, {"grant": [], "revoke": []})
        delta["grant" if grant else "revoke"].append(index)
    return plan


def apply_delta(current, grant, revoke):
    """Return ``current`` with ``revoke`` removed and ``grant`` appended.

    Existing order is preserved and duplicates are dropped, so a role that is
    edited comes back as close to how it was written as possible.
    """
    revoked = set(revoke)
    result = []
    for name in list(current) + list(grant):
        if name not in revoked and name not in result:
            result.append(name)
    return result


def read_matrix(gateway):
    return build_matrix(gateway.list_roles(), gateway.list_indexes(), gateway.capabilities())


def submit_changes(gateway, raw_changes, user="unknown"):
    """Apply a validated change list, one write per role.

    Changes are deltas, not a full replacement: each role is re-read just
    before its write and only the submitted cells are altered, so an edit made
    elsewhere since the page loaded is not overwritten.

    splunkd has no transaction across roles, so this is not atomic. Every role
    is attempted and reported individually; one refusal does not stop the rest.
    """
    plan = parse_changes(raw_changes)
    results = []
    for role, per_field in plan.items():
        try:
            content = gateway.get_role(role)
            update = OrderedDict()
            for field, delta in per_field.items():
                current = as_list(content.get(field))
                wanted = apply_delta(current, delta["grant"], delta["revoke"])
                if wanted != current:
                    update[field] = wanted
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
        logger.info("user=%s role=%s updated %s", user, role, json.dumps(per_field, sort_keys=True))
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
            return 200, read_matrix(gateway)
        if method == "POST":
            return 200, submit_changes(gateway, extract_changes(body), user=user)
        return 405, error_payload("Method %s is not supported." % method)
    except EasyAdminError as error:
        return error.status, error_payload(str(error))
    except GatewayError as error:
        return error.status, error_payload(str(error))
