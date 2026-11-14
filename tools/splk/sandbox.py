"""Make live changes to a Splunk target and put everything back afterwards.

Live and UI tests may create users and roles, edit existing ones, and change
app permissions on the dev target. This module is what makes that safe:

* ``Sandbox`` is the per-test ledger. Every object a test creates through it
  is deleted at the end, and every existing object it changes has the touched
  attributes recorded first and written back at the end, newest change first.
* ``snapshot`` / ``diff`` capture the users, roles and app permissions on
  the target as plain data, so the test fixtures can compare the target after
  a test with the target before it, and repair and report any difference,
  including changes made behind the sandbox's back (by the app under test,
  say, or a browser test clicking Save).
* ``sweep`` deletes objects that a killed run left behind. Everything a test
  creates is named with ``PREFIX``, so nothing else is ever swept.

The fixtures in ``tests/live/conftest.py`` and ``tests/ui/conftest.py`` wire
these together; tests only see the ``sandbox`` fixture.

Pure data handling (normalising, diffing, planning a restore) is kept free of
I/O so the unit suite covers it with a fake splunkd.

Two limits, stated where they bite:

* A password cannot be read back, so it cannot be restored. ``update`` refuses
  to change the password of a user it did not create.
* Restoring writes values back through REST. What the REST API then reports is
  what it reported before; the stanza in ``local/authorize.conf`` can still be
  spelled differently (splunkd writes an unlisted default capability as
  ``<capability> = disabled`` when ``capabilities`` is written in full).
"""

import json
import os
import secrets
import string
import time
import urllib.parse

from splk.logs import get_logger
from splk.rest import SplunkError

log = get_logger("sandbox")

# Every object a test creates is named PREFIX + random hex. Lower case, digits
# and underscores only: the strictest of splunkd's rules for role names.
PREFIX = "splktest_"

# How each kind of object is reached over REST, and which attributes can be
# written back to it. Attributes outside ``writable`` are still compared (so a
# change is noticed), but cannot be restored and are reported instead.
KINDS = {
    "role": {
        "collection": "/services/authorization/roles",
        # Every attribute splunkd 10.6.1 accepts on authorization/roles (the
        # _new endpoint's optionalFields), less the per-pattern
        # srchMinScheduleInterval.<pattern> family, which no test writes.
        "writable": (
            "capabilities", "cumulativeRTSrchJobsQuota", "cumulativeSrchJobsQuota",
            "defaultApp", "deleteIndexesAllowed", "federatedProviders", "fieldFilterExemption",
            "grantable_roles", "imported_roles", "kvstore_create.deny_list",
            "kvstore_create.implicit_deny_list", "kvstore_delete.deny_list",
            "kvstore_delete.implicit_deny_list", "kvstore_update.deny_list",
            "kvstore_update.implicit_deny_list", "queuedSearchQuota", "rtSrchJobsQuota",
            "srchAllowAdvancedCron", "srchDiskQuota", "srchFederatedProvidersAllowed",
            "srchFederatedProvidersDefault", "srchFilter", "srchIndexesAllowed",
            "srchIndexesDefault", "srchIndexesDisallowed", "srchJobsQuota",
            "srchMinScheduleInterval", "srchTimeEarliest", "srchTimeWin",
        ),
        # Derived from other roles (imported_capabilities and friends), so
        # they change when an imported role changes; that role is compared
        # in its own right. imported_roles is the role's own setting.
        # splunkd only ever appends to these (observed on 10.6.1 for
        # fieldFilterExemption), so a removal cannot be written back.
        "append_only": ("fieldFilterExemption",),
        "ignore_prefixes": ("eai:", "imported_"),
        "keep": ("imported_roles",),
        "ignore": (),
    },
    "user": {
        "collection": "/services/authentication/users",
        "writable": ("roles", "email", "realname", "defaultApp", "tz", "force_change_pass"),
        "append_only": (),
        "ignore_prefixes": ("eai:",),
        "keep": (),
        # Derived from roles, or changed by signing in (which every UI run
        # does as the admin), so not something a test can leave behind.
        "ignore": ("capabilities", "last_successful_login", "defaultAppIsUserOverride",
                   "defaultAppSourceRole", "lockedOut", "locked-out"),
    },
}

# Users are deleted before roles (a user cannot hold a role that is gone) and
# app permissions are restored last.
KIND_ORDER = ("user", "role")


class SandboxError(Exception):
    """The target could not be put back exactly as it was."""


# ------------------------------------------------------------- pure helpers

def new_name(label=""):
    """A unique, sweepable object name: ``splktest_<label>_<hex8>``."""
    label = "".join(ch for ch in label.lower() if ch in string.ascii_lowercase + string.digits)
    middle = (label[:20] + "_") if label else ""
    return "%s%s%s" % (PREFIX, middle, secrets.token_hex(4))


def new_password():
    """A random password that meets Splunk's default complexity rules.

    Mixed case, digits and a symbol, so a stricter password policy on the
    dev target does not refuse the throwaway user.
    """
    return "Sk-%s-9a" % secrets.token_urlsafe(18)


def is_sandbox_name(name):
    return str(name or "").startswith(PREFIX)


def normalise(value):
    """One comparable form for any REST value.

    splunkd returns a lone value of a multi-valued attribute as a bare string,
    stores lists sorted rather than as written, and gives numbers as JSON
    numbers: so every value becomes a sorted tuple of strings, and unset
    (None, "", []) becomes the empty tuple.
    """
    if value is None:
        return ()
    if isinstance(value, (list, tuple)):
        return tuple(sorted(str(item) for item in value if item is not None and str(item) != ""))
    if isinstance(value, bool):
        return ("1" if value else "0",)
    text = str(value)
    return (text,) if text != "" else ()


def comparable(kind, content):
    """The attributes of one object that a test could leave changed, normalised."""
    spec = KINDS[kind]
    result = {}
    for name, value in (content or {}).items():
        if name in spec["ignore"]:
            continue
        if name not in spec["keep"] and any(name.startswith(p) for p in spec["ignore_prefixes"]):
            continue
        result[name] = normalise(value)
    return result


def acl_comparable(acl):
    """The parts of an object's eai:acl a test could change: sharing, owner, perms."""
    acl = acl or {}
    perms = acl.get("perms") or {}
    return {
        "sharing": normalise(acl.get("sharing")),
        "owner": normalise(acl.get("owner")),
        "perms.read": normalise(perms.get("read")),
        "perms.write": normalise(perms.get("write")),
    }


def diff(before, after):
    """Compare two snapshots. Returns a list of differences, each a dict.

    ``{"kind", "name", "change": "created" | "deleted" | "changed", "fields"}``,
    where ``fields`` maps an attribute to ``(before, after)``.
    """
    differences = []
    for kind in sorted(set(before) | set(after)):
        old, new = before.get(kind, {}), after.get(kind, {})
        for name in sorted(set(old) | set(new)):
            if name not in new:
                differences.append({"kind": kind, "name": name, "change": "deleted", "fields": {}})
            elif name not in old:
                differences.append({"kind": kind, "name": name, "change": "created", "fields": {}})
            else:
                fields = {}
                for attr in sorted(set(old[name]) | set(new[name])):
                    was, now = old[name].get(attr, ()), new[name].get(attr, ())
                    if was != now:
                        fields[attr] = (was, now)
                if fields:
                    differences.append({"kind": kind, "name": name, "change": "changed",
                                        "fields": fields})
    return differences


def describe(difference):
    """One line for a log or a test failure."""
    if difference["change"] != "changed":
        return "%s %s was %s" % (difference["kind"], difference["name"], difference["change"])
    parts = ["%s: %s -> %s" % (attr, list(was), list(now))
             for attr, (was, now) in sorted(difference["fields"].items())]
    return "%s %s changed (%s)" % (difference["kind"], difference["name"], "; ".join(parts))


def restore_params(kind, fields):
    """POST parameters that write ``fields`` (attr -> normalised value) back.

    A list value is sent as one form value per item; an empty value is sent
    as "" which is how splunkd clears an attribute. Attributes that cannot be
    written are returned separately so the caller can report them.
    """
    writable = KINDS[kind]["writable"]
    append_only = KINDS[kind]["append_only"]
    params, unrestorable = {}, []
    for attr, value in sorted(fields.items()):
        if attr not in writable or attr in append_only:
            unrestorable.append(attr)
        elif not value:
            params[attr] = ""
        elif len(value) == 1:
            params[attr] = value[0]
        else:
            params[attr] = list(value)
    return params, unrestorable


# -------------------------------------------------------------- REST access

def object_path(kind, name):
    return "%s/%s" % (KINDS[kind]["collection"], urllib.parse.quote(name, safe=""))


def read_object(client, kind, name):
    """The content of one object, or None when it does not exist."""
    try:
        data = client.request("GET", object_path(kind, name))
    except SplunkError as exc:
        if exc.status == 404:
            return None
        raise
    entries = data.get("entry") or []
    return entries[0].get("content") or {} if entries else None


def list_objects(client, kind):
    """name -> content for every object of a kind (count=0 lifts the page size)."""
    data = client.request("GET", KINDS[kind]["collection"], {"count": 0})
    return {entry["name"]: entry.get("content") or {} for entry in data.get("entry") or []}


def app_acl(client, app):
    """The app's eai:acl (sharing, owner, perms)."""
    data = client.request("GET", "/services/apps/local/%s" % urllib.parse.quote(app, safe=""))
    return data["entry"][0].get("acl") or {}


def write_app_acl(client, app, sharing, owner, read, write):
    """Set an app's permissions (all four values together, as splunkd requires)."""
    params = {"sharing": sharing, "owner": owner,
              "perms.read": ",".join(read), "perms.write": ",".join(write)}
    client.request("POST", "/services/apps/local/%s/acl" % urllib.parse.quote(app, safe=""), params)


def snapshot(client, apps=()):
    """Capture every user and role, and the permissions of ``apps``.

    The result is plain data: ``{kind: {name: {attr: normalised value}}}``,
    with app permissions under the kind ``"app_acl"``.
    """
    state = {}
    for kind in KIND_ORDER:
        state[kind] = {name: comparable(kind, content)
                       for name, content in list_objects(client, kind).items()}
    state["app_acl"] = {}
    if apps:
        # One listing gives every app's ACL: one request instead of one per
        # app, since the guard snapshots twice around every test. An app
        # that is not installed is simply absent: nothing to protect.
        data = client.request("GET", "/services/apps/local", {"count": 0})
        for entry in data.get("entry") or []:
            if entry.get("name") in apps:
                state["app_acl"][entry["name"]] = acl_comparable(entry.get("acl"))
    return state


# ------------------------------------------------- interrupted-run recovery
#
# Fixture teardown does not run when the process is killed (a closed
# terminal, a CI timeout). So the snapshot taken before each test is also
# written to disk and removed once the test has been put back. A file still
# there at the next start means a run died mid-test: the next run repairs the
# target against it before testing anything.

def pending_path(directory, target_name):
    return os.path.join(directory, "sandbox-%s-pending.json" % target_name)


def save_pending(path, state):
    """Write a snapshot to ``path`` (tuples become lists in JSON)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(state, handle, sort_keys=True)
    # Replace in one step, so a crash mid-write never leaves half a snapshot.
    os.replace(temporary, path)


def load_pending(path):
    """The snapshot saved at ``path``, or None when there is none."""
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as handle:
        raw = json.load(handle)
    return {kind: {name: {attr: tuple(value) for attr, value in attrs.items()}
                   for name, attrs in objects.items()}
            for kind, objects in raw.items()}


def clear_pending(path):
    try:
        os.remove(path)
    except FileNotFoundError:
        pass


def _delete(client, kind, name):
    """Delete one object; an object that is already gone counts as deleted."""
    try:
        client.request("DELETE", object_path(kind, name))
        log.info("Deleted %s %s", kind, name)
    except SplunkError as exc:
        if exc.status != 404:
            raise


def sweep(client):
    """Delete objects left behind by an earlier, interrupted run.

    Only names starting with PREFIX are touched. Returns what was deleted.
    """
    removed = []
    for kind in KIND_ORDER:
        for name in sorted(list_objects(client, kind)):
            if is_sandbox_name(name):
                log.warning("Removing %s %s left behind by an earlier run", kind, name)
                _delete(client, kind, name)
                removed.append((kind, name))
    return removed


def repair(client, before, after):
    """Put the target back to ``before`` where it differs from ``after``.

    * created with PREFIX: deleted.
    * changed: the changed attributes written back (app permissions in full).
    * created without PREFIX, or deleted: cannot be undone safely (the object
      may be someone else's, and a deleted user's password is gone), so it is
      only reported.

    Returns a list of problems that could not be repaired.
    """
    problems = []
    differences = diff(before, after)
    # Users before roles, so a sandbox user never blocks deleting its role.
    order = {"user": 0, "role": 1, "app_acl": 2}
    for difference in sorted(differences, key=lambda d: order.get(d["kind"], 9)):
        kind, name, change = difference["kind"], difference["name"], difference["change"]
        try:
            if change == "created" and kind in KINDS and is_sandbox_name(name):
                _delete(client, kind, name)
            elif change == "changed" and kind == "app_acl":
                acl = before[kind][name]
                write_app_acl(client, name, acl["sharing"][0], acl["owner"][0],
                              acl["perms.read"], acl["perms.write"])
                log.warning("Restored the permissions of app %s", name)
            elif change == "changed":
                fields = {attr: was for attr, (was, _now) in difference["fields"].items()}
                params, unrestorable = restore_params(kind, fields)
                if params:
                    client.request("POST", object_path(kind, name), params)
                    log.warning("Restored %s on %s %s", ", ".join(sorted(params)), kind, name)
                if unrestorable:
                    problems.append("%s %s: cannot write back %s"
                                    % (kind, name, ", ".join(unrestorable)))
            else:
                problems.append("cannot undo: %s" % describe(difference))
        except SplunkError as exc:
            problems.append("repairing %s failed: %s" % (describe(difference), exc))
    return problems


# ------------------------------------------------------------------ ledger

class Sandbox(object):
    """Per-test ledger of everything a test created or changed on the target.

    Usage (the ``sandbox`` fixture does the cleanup)::

        role = sandbox.create_role(srchIndexesAllowed="main")
        user, password = sandbox.create_user(roles=[role])
        sandbox.update("role", "power", srchJobsQuota="7")   # recorded, put back
        sandbox.cleanup()
    """

    def __init__(self, client):
        self.client = client
        # (kind, name) in creation order; deleted newest first.
        self.created = []
        # (kind, name) -> {attr: original normalised value}, first record wins
        # so a second change to the same attribute still restores the first.
        self.originals = {}
        # app -> original eai:acl, for set_app_permissions.
        self.app_acls = {}

    # ------------------------------------------------------------ creating

    def create(self, kind, name=None, label="", **attributes):
        """Create an object of ``kind`` with a sandbox name and return the name."""
        name = name or new_name(label or kind)
        if not is_sandbox_name(name):
            raise ValueError("Sandbox objects must be named %s...; got %r" % (PREFIX, name))
        params = {"name": name}
        params.update(attributes)
        # Recorded before the call, so an object splunkd half-created (or
        # created before timing out) is still cleaned up.
        self.created.append((kind, name))
        self.client.request("POST", KINDS[kind]["collection"], params)
        log.info("Created %s %s", kind, name)
        return name

    def create_role(self, label="", **attributes):
        return self.create("role", label=label, **attributes)

    def create_user(self, roles, label="", password=None, **attributes):
        """Create a user holding ``roles``; returns ``(name, password)``.

        The user is not asked to change the password at first sign-in, so
        tests can sign in as it straight away.
        """
        password = password or new_password()
        params = {"password": password, "roles": list(roles), "force-change-pass": "0"}
        params.update(attributes)
        name = self.create("user", label=label, **params)
        return name, password

    def track(self, kind, name):
        """Adopt an object something else created (the app under test, a browser
        test) so it is deleted with the rest."""
        if not is_sandbox_name(name):
            raise ValueError("Only sandbox-named objects can be tracked; got %r" % name)
        if (kind, name) not in self.created:
            self.created.append((kind, name))

    # ------------------------------------------------------------ changing

    def remember(self, kind, name, attributes):
        """Record the current value of ``attributes`` on an existing object.

        Call before something other than ``update`` changes them (a browser
        test saving through the page, say). Objects the sandbox created need
        no record: they are deleted.
        """
        if (kind, name) in self.created:
            return
        append_only = [a for a in attributes if a in KINDS[kind]["append_only"]]
        if append_only:
            raise ValueError("Refusing to change %s on existing %s %r: splunkd only appends "
                             "to it, so it cannot be restored" % (", ".join(append_only), kind, name))
        if kind == "user" and "password" in attributes:
            raise ValueError("Refusing to change the password of existing user %r: "
                             "it cannot be read back, so it cannot be restored" % name)
        content = read_object(self.client, kind, name)
        if content is None:
            raise ValueError("%s %r does not exist" % (kind, name))
        record = self.originals.setdefault((kind, name), {})
        for attr in attributes:
            record.setdefault(attr, normalise(content.get(attr)))

    def update(self, kind, name, **attributes):
        """Change attributes of any object; existing objects are put back later."""
        self.remember(kind, name, list(attributes))
        self.client.request("POST", object_path(kind, name), attributes)
        log.info("Updated %s on %s %s", ", ".join(sorted(attributes)), kind, name)

    def set_app_permissions(self, app, read=None, write=None, sharing=None):
        """Change who can see or edit an app; the original permissions are put back."""
        current = app_acl(self.client, app)
        self.app_acls.setdefault(app, current)
        perms = current.get("perms") or {}
        write_app_acl(
            self.client, app,
            sharing or current.get("sharing") or "app",
            current.get("owner") or "nobody",
            read if read is not None else perms.get("read") or [],
            write if write is not None else perms.get("write") or [])
        log.info("Changed the permissions of app %s", app)

    # ------------------------------------------------------------- cleanup

    def cleanup(self):
        """Undo everything, attempting every step even when one fails.

        Raises SandboxError listing whatever could not be undone.
        """
        problems = []
        # Users first, then roles, each newest first: a role can only go once
        # nothing imports it or holds it.
        for kind in KIND_ORDER:
            for created_kind, name in reversed(self.created):
                if created_kind != kind:
                    continue
                try:
                    _delete(self.client, kind, name)
                except SplunkError as exc:
                    problems.append("deleting %s %s failed: %s" % (kind, name, exc))
        for (kind, name), fields in self.originals.items():
            params, unrestorable = restore_params(kind, fields)
            try:
                if params:
                    self.client.request("POST", object_path(kind, name), params)
                    log.info("Restored %s on %s %s", ", ".join(sorted(params)), kind, name)
            except SplunkError as exc:
                problems.append("restoring %s %s failed: %s" % (kind, name, exc))
            if unrestorable:
                problems.append("%s %s: cannot write back %s" % (kind, name, ", ".join(unrestorable)))
        for app, acl in self.app_acls.items():
            perms = acl.get("perms") or {}
            try:
                write_app_acl(self.client, app, acl.get("sharing") or "app",
                              acl.get("owner") or "nobody",
                              perms.get("read") or [], perms.get("write") or [])
                log.info("Restored the permissions of app %s", app)
            except SplunkError as exc:
                problems.append("restoring the permissions of app %s failed: %s" % (app, exc))
        self.created, self.originals, self.app_acls = [], {}, {}
        if problems:
            raise SandboxError("; ".join(problems))


def wait_for(check, timeout=30.0, interval=1.0):
    """Poll ``check()`` until it returns something truthy; returns it or None."""
    deadline = time.time() + timeout
    while True:
        result = check()
        if result or time.time() >= deadline:
            return result
        time.sleep(interval)
