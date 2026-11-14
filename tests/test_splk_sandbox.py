"""Tests for splk.sandbox: the ledger that puts the live target back after a test.

A stateful in-memory splunkd stands in for the target (users, roles and app
permissions), reached through SplunkClient's injectable opener, so these
tests exercise the real request code. What the real splunkd does is proven
by the live suites, which run inside the same guard.
"""

import io
import json
import logging
import urllib.error
import urllib.parse

import pytest

from splk import sandbox as sb
from splk.config import Target
from splk.rest import SplunkClient, SplunkError

log = logging.getLogger("test.sandbox")

ROLES = "/services/authorization/roles"
USERS = "/services/authentication/users"


class _Response(object):
    """Just enough of http.client.HTTPResponse for SplunkClient."""

    def __init__(self, status, body):
        self.status = status
        self._body = json.dumps(body).encode("utf-8")

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeSplunkd(object):
    """Users, roles and app ACLs held in dicts, with splunkd's REST shapes.

    Mirrors the splunkd behaviours the sandbox depends on: a lone value comes
    back as a bare string, "" clears an attribute, creating an existing name
    is refused, and a role held by a user cannot be deleted.
    """

    def __init__(self):
        self.objects = {
            ROLES: {"admin": {"capabilities": ["edit_roles", "search"], "srchJobsQuota": 50,
                              "imported_capabilities": ["x"]},
                    "user": {"capabilities": "search", "srchJobsQuota": 3}},
            USERS: {"admin": {"roles": "admin", "email": "", "last_successful_login": 1}},
        }
        self.acls = {"easyadmin": {"sharing": "app", "owner": "nobody",
                                   "perms": {"read": ["admin"], "write": ["admin"]}}}
        self.calls = []
        self.fail_deletes = set()

    # The opener interface SplunkClient uses.
    def open(self, req, timeout=None):
        url = urllib.parse.urlparse(req.full_url)
        method = req.get_method()
        form = urllib.parse.parse_qs(req.data.decode("utf-8"), keep_blank_values=True) \
            if req.data else {}
        form = {k: (v if len(v) > 1 else v[0]) for k, v in form.items() if k != "output_mode"}
        self.calls.append((method, url.path, form))
        status, body = self._route(method, urllib.parse.unquote(url.path), form)
        if status >= 400:
            raise urllib.error.HTTPError(req.full_url, status, "error", {},
                                         io.BytesIO(json.dumps(body).encode("utf-8")))
        return _Response(status, body)

    def _route(self, method, path, form):
        if path.startswith("/services/apps/local/"):
            app = path.split("/")[4]
            if app not in self.acls:
                return 404, {"messages": [{"text": "no app"}]}
            if path.endswith("/acl") and method == "POST":
                self.acls[app] = {"sharing": form["sharing"], "owner": form["owner"],
                                  "perms": {"read": form["perms.read"].split(","),
                                            "write": form["perms.write"].split(",")}}
                return 200, {}
            return 200, {"entry": [{"name": app, "acl": self.acls[app], "content": {}}]}
        for collection in (ROLES, USERS):
            if path == collection:
                if method == "GET":
                    return 200, {"entry": [{"name": n, "content": c}
                                           for n, c in self.objects[collection].items()]}
                name = form.pop("name")
                if name in self.objects[collection]:
                    return 409, {"messages": [{"text": "exists"}]}
                form.pop("password", None)
                form.pop("force-change-pass", None)
                self.objects[collection][name] = form
                return 201, {}
            if path.startswith(collection + "/"):
                name = path[len(collection) + 1:]
                if name not in self.objects[collection]:
                    return 404, {"messages": [{"text": "not found"}]}
                if method == "GET":
                    return 200, {"entry": [{"name": name,
                                            "content": self.objects[collection][name]}]}
                if method == "DELETE":
                    if name in self.fail_deletes:
                        return 500, {"messages": [{"text": "refused"}]}
                    held = any(name in sb.normalise(u.get("roles"))
                               for u in self.objects[USERS].values())
                    if collection == ROLES and held:
                        return 400, {"messages": [{"text": "role in use"}]}
                    del self.objects[collection][name]
                    return 200, {}
                if "password" in form:
                    return 400, {"messages": [{"text": "no"}]}
                for key, value in form.items():
                    if value == "":
                        self.objects[collection][name].pop(key, None)
                    else:
                        self.objects[collection][name][key] = value
                return 200, {}
        return 404, {"messages": [{"text": "unknown path"}]}


@pytest.fixture
def splunkd():
    return FakeSplunkd()


@pytest.fixture
def client(splunkd):
    target = Target("fake", "splunkd.invalid", token="tok")
    return SplunkClient(target, opener=splunkd)


# ------------------------------------------------------------------ pure

def test_normalise_gives_one_form_for_every_shape():
    assert sb.normalise(None) == sb.normalise("") == sb.normalise([]) == ()
    assert sb.normalise("user") == sb.normalise(["user"]) == ("user",)
    assert sb.normalise(["b", "a"]) == sb.normalise(["a", "b"])
    assert sb.normalise(3) == sb.normalise("3") == ("3",)
    assert sb.normalise(True) == ("1",)


def test_comparable_drops_derived_and_volatile_attributes():
    role = sb.comparable("role", {"imported_capabilities": ["x"], "imported_roles": "user",
                                  "eai:acl": {}, "srchJobsQuota": 3})
    assert role == {"imported_roles": ("user",), "srchJobsQuota": ("3",)}
    user = sb.comparable("user", {"roles": "admin", "last_successful_login": 5, "capabilities": []})
    assert user == {"roles": ("admin",)}


def test_diff_names_created_deleted_and_changed_objects():
    before = {"role": {"a": {"q": ("1",)}, "gone": {}}}
    after = {"role": {"a": {"q": ("2",)}, "new": {}}}
    found = {(d["name"], d["change"]): d for d in sb.diff(before, after)}
    assert set(found) == {("a", "changed"), ("gone", "deleted"), ("new", "created")}
    assert found[("a", "changed")]["fields"] == {"q": (("1",), ("2",))}
    assert "q: ['1'] -> ['2']" in sb.describe(found[("a", "changed")])


def test_restore_params_clears_empty_and_reports_unwritable():
    params, unrestorable = sb.restore_params(
        "role", {"srchFilter": (), "imported_roles": ("a", "b"), "srchJobsQuota": ("3",),
                 "made_up": ("x",)})
    assert params == {"srchFilter": "", "imported_roles": ["a", "b"], "srchJobsQuota": "3"}
    assert unrestorable == ["made_up"]


def test_new_names_are_sweepable_and_unique():
    names = {sb.new_name("Role Test!") for _ in range(50)}
    assert len(names) == 50
    assert all(sb.is_sandbox_name(n) and n.startswith("splktest_roletest_") for n in names)


# ---------------------------------------------------------------- ledger

def test_cleanup_deletes_users_before_the_roles_they_hold(client, splunkd):
    box = sb.Sandbox(client)
    role = box.create_role(srchIndexesAllowed="main")
    user, password = box.create_user(roles=[role])
    assert password and role in splunkd.objects[ROLES] and user in splunkd.objects[USERS]
    box.cleanup()
    assert role not in splunkd.objects[ROLES] and user not in splunkd.objects[USERS]


def test_update_of_an_existing_role_is_put_back(client, splunkd):
    box = sb.Sandbox(client)
    box.update("role", "user", srchJobsQuota="9", srchFilter="index=x")
    box.update("role", "user", srchJobsQuota="12")  # second change still restores the first
    assert splunkd.objects[ROLES]["user"]["srchJobsQuota"] == "12"
    box.cleanup()
    assert sb.normalise(splunkd.objects[ROLES]["user"]["srchJobsQuota"]) == ("3",)
    assert "srchFilter" not in splunkd.objects[ROLES]["user"]


def test_changing_an_existing_users_password_is_refused(client):
    with pytest.raises(ValueError, match="cannot be restored"):
        sb.Sandbox(client).update("user", "admin", password="x")


def test_only_sandbox_names_can_be_created_or_tracked(client):
    box = sb.Sandbox(client)
    with pytest.raises(ValueError):
        box.create("role", name="power2")
    with pytest.raises(ValueError):
        box.track("role", "admin")


def test_cleanup_tries_every_step_and_reports_failures(client, splunkd):
    box = sb.Sandbox(client)
    stuck = box.create_role()
    other = box.create_role()
    box.update("role", "user", srchJobsQuota="8")
    splunkd.fail_deletes.add(stuck)
    with pytest.raises(sb.SandboxError, match="deleting role %s failed" % stuck):
        box.cleanup()
    # The failure did not stop the other deletion or the restore.
    assert other not in splunkd.objects[ROLES]
    assert sb.normalise(splunkd.objects[ROLES]["user"]["srchJobsQuota"]) == ("3",)


def test_app_permissions_are_put_back(client, splunkd):
    box = sb.Sandbox(client)
    box.set_app_permissions("easyadmin", read=["admin", "user"])
    assert splunkd.acls["easyadmin"]["perms"]["read"] == ["admin", "user"]
    box.cleanup()
    assert splunkd.acls["easyadmin"]["perms"]["read"] == ["admin"]


# ------------------------------------------------- snapshot, sweep, repair

def test_snapshot_skips_apps_that_are_not_installed(client):
    state = sb.snapshot(client, apps=("easyadmin", "not_installed"))
    assert set(state["app_acl"]) == {"easyadmin"}
    assert state["role"]["admin"]["srchJobsQuota"] == ("50",)


def test_repair_undoes_changes_made_outside_the_sandbox(client, splunkd):
    before = sb.snapshot(client, apps=("easyadmin",))
    # What a browser test saving through a page might leave behind.
    splunkd.objects[ROLES]["user"]["srchJobsQuota"] = 99
    splunkd.objects[ROLES]["splktest_left_0001"] = {}
    splunkd.objects[ROLES]["someone_elses"] = {}
    splunkd.acls["easyadmin"]["perms"]["read"] = ["*"]
    problems = sb.repair(client, before, sb.snapshot(client, apps=("easyadmin",)))
    after = sb.snapshot(client, apps=("easyadmin",))
    # Only the role without the sandbox prefix is left, and it is reported.
    assert [sb.describe(d) for d in sb.diff(before, after)] == ["role someone_elses was created"]
    assert problems == ["cannot undo: role someone_elses was created"]


def test_sweep_removes_only_sandbox_objects(client, splunkd):
    splunkd.objects[ROLES]["splktest_old_0001"] = {}
    splunkd.objects[USERS]["splktest_old_0002"] = {"roles": "splktest_old_0001"}
    removed = sb.sweep(client)
    assert removed == [("user", "splktest_old_0002"), ("role", "splktest_old_0001")]
    assert set(splunkd.objects[ROLES]) == {"admin", "user"}


def test_pending_snapshot_round_trips_through_disk(tmp_path, client):
    path = sb.pending_path(str(tmp_path), "local")
    assert sb.load_pending(path) is None
    state = sb.snapshot(client, apps=("easyadmin",))
    sb.save_pending(path, state)
    assert sb.load_pending(path) == state
    sb.clear_pending(path)
    sb.clear_pending(path)  # clearing twice is harmless
    assert sb.load_pending(path) is None


def test_as_user_sends_the_session_key_not_the_token(client, splunkd):
    splunkd._route_orig = splunkd._route

    def route(method, path, form):
        if path == "/services/auth/login":
            return 200, {"sessionKey": "sess123"}
        return splunkd._route_orig(method, path, form)
    splunkd._route = route
    seen = []
    original_open = splunkd.open

    def recording_open(req, timeout=None):
        seen.append(req.get_header("Authorization"))
        return original_open(req, timeout)
    splunkd.open = recording_open
    other = client.as_user("bob", "pw")
    other.request("GET", ROLES)
    assert seen == ["Bearer tok", "Splunk sess123"]


def test_rest_errors_carry_status(client):
    with pytest.raises(SplunkError) as caught:
        client.request("GET", ROLES + "/nope")
    assert caught.value.status == 404
