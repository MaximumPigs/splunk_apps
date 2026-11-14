"""Unit tests for easyadmin_apps_core: the app model and staged object changes.

splunkd is replaced by FakeGateway, which keeps objects in memory under their
REST paths and copies the behaviour observed on 10.6.1 and pinned by
tests/live/easyadmin/test_easyadmin_apps_live.py: an object in default/
has no move or remove link and splunkd refuses to move or delete it; a move
keeps the owner and sharing; an acl POST without ``sharing`` is a 400.
"""

import json

import pytest

import easyadmin_apps_core as apps
from easyadmin_core import GatewayError

HOST = "https://127.0.0.1:8089"


def entry(type_id, name, app, owner="nobody", sharing="app", ns=None, local=True,
          read=("*",), write=("admin",), can_change_perms=True, content=None):
    ns = ns or (owner if sharing == "user" else "nobody")
    links = {"edit": "x", "list": "x"}
    if local:
        links.update({"move": "x", "remove": "x"})
    return {
        "name": name,
        "id": HOST + apps.object_path(type_id, ns, app, name),
        "acl": {"app": app, "owner": owner, "sharing": sharing,
                "perms": None if sharing == "user" else {"read": list(read), "write": list(write)},
                "can_change_perms": can_change_perms, "can_share_app": True,
                "can_share_global": True, "removable": local},
        "links": links,
        "content": dict(content or {"disabled": False}),
    }


class FakeGateway(object):
    def __init__(self, objects=(), app_names=("search", "myapp", "other"), refuse_acl=()):
        self.app_names = list(app_names)
        self.objects = {}   # path -> (type_id, entry)
        for type_id, item in objects:
            self.objects[self._path(type_id, item)] = (type_id, item)
        self.refuse_acl = set(refuse_acl)
        self.calls = []

    @staticmethod
    def _path(type_id, item):
        ns, app = apps.namespace_of(item["id"])
        return apps.object_path(type_id, ns, app, item["name"])

    def list_apps(self):
        return [{"name": name, "content": {"label": name.title(), "core": name in ("search", "launcher", "SplunkEnterpriseSecuritySuite"),
                                           "visible": True, "disabled": False, "version": "1.0"}}
                for name in self.app_names]

    def list_objects(self, endpoint):
        if endpoint == "datamodel/model":
            raise GatewayError("You do not have permission.", status=403)
        return [item for type_id, item in self.objects.values()
                if apps.TYPES[type_id]["endpoint"] == endpoint]

    def list_role_names(self):
        return ["user", "admin", "power"]

    def list_user_names(self):
        return ["admin", "alice"]

    def current_context(self):
        return {"username": "admin", "theme": "dark"}

    def get_object(self, path, full=False):
        self.calls.append(("get", path))
        if path not in self.objects:
            raise GatewayError("Object not found.", status=404)
        return self.objects[path][1]

    def move_object(self, path, app, user):
        self.calls.append(("move", path, app, user))
        type_id, item = self.objects[path]
        if "move" not in item["links"]:
            raise GatewayError("Object id=%s cannot be deleted and thus it cannot be moved" % item["name"],
                               status=400)
        del self.objects[path]
        item = json.loads(json.dumps(item))
        item["acl"]["app"] = app
        item["id"] = HOST + apps.object_path(type_id, user, app, item["name"])
        self.objects[self._path(type_id, item)] = (type_id, item)

    def set_acl(self, path, postargs):
        self.calls.append(("acl", path, dict(postargs)))
        if "sharing" not in postargs:
            raise GatewayError("The following required arguments are missing: sharing.", status=400)
        if path in self.refuse_acl:
            raise GatewayError("Permission denied.", status=403)
        type_id, item = self.objects[path]
        item["acl"]["sharing"] = postargs["sharing"]
        item["acl"]["owner"] = postargs["owner"]

    def delete_object(self, path):
        self.calls.append(("delete", path))
        del self.objects[path]


def change(type_id, name, app, ns="nobody", **edits):
    out = {"type": type_id, "ns": ns, "app": app, "name": name}
    out.update(edits)
    return out


# ------------------------------------------------------------------ model

def test_namespace_of_reads_user_and_app_from_the_id():
    assert apps.namespace_of(HOST + "/servicesNS/admin/search/admin/macros/x") == ("admin", "search")
    assert apps.namespace_of(HOST + "/servicesNS/nobody/my%20app/saved/searches/a%20b") == ("nobody", "my app")
    assert apps.namespace_of("") == (None, None)
    assert apps.namespace_of(HOST + "/services/apps/local/x") == (None, None)


def test_object_path_quotes_every_part():
    path = apps.object_path("savedsearch", "nobody", "search", "a/b ../c")
    assert path == "/servicesNS/nobody/search/saved/searches/a%2Fb%20..%2Fc"


def test_build_object_reads_what_splunkd_allows_from_links():
    local = apps.build_object("macro", entry("macro", "m1", "search"))
    shipped = apps.build_object("macro", entry("macro", "m2", "search", local=False))
    assert (local["movable"], local["removable"]) == (True, True)
    assert (shipped["movable"], shipped["removable"]) == (False, False)
    assert local["read"] == ["*"] and local["write"] == ["admin"]


def test_private_object_lives_in_its_owners_namespace():
    item = apps.build_object("macro", entry("macro", "mine", "search", owner="alice", sharing="user"))
    assert item["ns"] == "alice"
    assert item["read"] == [] and item["write"] == []
    assert item["key"] == apps.object_key("macro", "alice", "search", "mine")


def test_model_sorts_apps_and_objects_and_reports_unlistable_types():
    gateway = FakeGateway([
        ("macro", entry("macro", "zeta", "search")),
        ("savedsearch", entry("savedsearch", "Alpha", "search")),
        ("view", entry("view", "home", "myapp")),
        ("macro", entry("macro", "sysmacro", "system", local=False)),
        ("macro", entry("macro", "ghost", "hidden_app")),
    ], app_names=("search", "Myapp_b", "myapp"))
    model = apps.read_model(gateway)
    # By label (the fake titles each name; system is "System (etc/system)"), then name.
    assert [a["label"] for a in model["apps"]] == ["hidden_app", "Myapp", "Myapp_B", "Search",
                                                   "System (etc/system)"]
    by_name = {a["name"]: a for a in model["apps"]}
    # Splunk marks search as core, but it is where users keep their objects.
    assert by_name["search"]["builtin"] is False
    assert by_name["system"]["target"] is False and by_name["system"]["builtin"] is True
    assert by_name["hidden_app"]["target"] is False
    # Within an app: type order of the legend (reports before macros), then name.
    assert [o["name"] for o in model["objects"] if o["app"] == "search"] == ["Alpha", "zeta"]
    assert model["warnings"] == ["Data model could not be listed: You do not have permission."]
    assert model["roles"] == ["admin", "power", "user"]
    assert model["user"] == "admin" and model["theme"] == "dark"
    assert [t["id"] for t in model["types"]] == list(apps.TYPES)
    common = {t["id"] for t in model["types"] if t["common"]}
    assert {"savedsearch", "view", "macro", "lookupfile", "lookupdef"} <= common
    assert not common & {"panel", "timerange", "nav", "alertaction"}


def test_search_and_enterprise_security_are_not_hidden_as_built_in():
    gateway = FakeGateway(app_names=("search", "launcher", "SplunkEnterpriseSecuritySuite", "myapp"))
    by_name = {a["name"]: a for a in apps.read_model(gateway)["apps"]}
    assert by_name["launcher"]["builtin"] is True
    assert by_name["search"]["builtin"] is False
    assert by_name["SplunkEnterpriseSecuritySuite"]["builtin"] is False
    assert by_name["myapp"]["builtin"] is False


def test_details_list_settings_and_shorten_long_values():
    item = entry("view", "big", "search", content={"eai:data": "x" * (apps.MAX_DETAIL_VALUE + 10),
                                                   "eai:acl": {"app": "search"}, "disabled": False,
                                                   "isDashboard": True})
    details = apps.build_details("view", item)
    names = [s["name"] for s in details["settings"]]
    assert names == ["disabled", "eai:data", "isDashboard"]
    data = details["settings"][1]
    assert data["truncated"] is True and len(data["value"]) == apps.MAX_DETAIL_VALUE
    assert details["settings"][0]["value"] == "0"


def test_get_with_an_object_returns_its_details():
    gateway = FakeGateway([("macro", entry("macro", "m1", "search", content={"definition": "index=x"}))])
    status, body = apps.handle_request("GET", None, {"type": "macro", "ns": "nobody", "app": "search",
                                                     "name": "m1"}, gateway)
    assert status == 200
    assert body["settings"] == [{"name": "definition", "value": "index=x", "truncated": False}]


def test_get_for_a_missing_object_is_a_404():
    status, body = apps.handle_request("GET", None, {"type": "macro", "ns": "nobody", "app": "search",
                                                     "name": "nope"}, FakeGateway())
    assert status == 404


def test_get_rejects_an_unknown_type():
    status, body = apps.handle_request("GET", None, {"type": "../authorization/roles", "ns": "nobody",
                                                     "app": "search", "name": "x"}, FakeGateway())
    assert status == 400
    assert "unknown object type" in body["messages"][0]["text"]


# -------------------------------------------------------------- validation

@pytest.mark.parametrize("raw, message", [
    ("nope", "must be a list"),
    ([], "no changes"),
    ([{"type": "bogus", "ns": "nobody", "app": "a", "name": "n", "delete": True}], "unknown object type"),
    ([change("macro", "", "search", delete=True)], "name must be a non-empty string"),
    ([change("macro", "m\n", "search", delete=True)], "control characters"),
    ([change("macro", "..", "search", delete=True)], "not a valid name"),
    ([change("macro", "m", "..", delete=True)], "not a valid name"),
    ([change("macro", "m", "search", ns=".", delete=True)], "not a valid name"),
    ([change("macro", "m", "search", delete="yes")], "'delete' must be true"),
    ([change("macro", "m", "search", delete=True, move_to="other")], "cannot also be moved"),
    ([change("macro", "m", "search", move_to="search")], "already in search"),
    ([change("macro", "m", "search", move_to="system")], "not an app that objects can be moved to"),
    ([change("macro", "m", "search", move_to="../etc")], "not an app that objects can be moved to"),
    ([change("macro", "m", "search", acl={"sharing": "everyone", "owner": "a"})], "sharing must be one of"),
    ([change("macro", "m", "search", acl={"sharing": "app", "owner": ""})], "owner must be a non-empty"),
    ([change("macro", "m", "search", acl={"sharing": "app", "owner": "a", "read": "*"})], "list of role names"),
    ([change("macro", "m", "search", acl={"sharing": "app", "owner": "a", "read": ["a,b"]})], "cannot contain a comma"),
    ([change("macro", "m", "search")], "changes nothing"),
    ([change("macro", "m", "search", delete=True), change("macro", "m", "search", delete=True)], "repeats an object"),
])
def test_parse_changes_rejects(raw, message):
    with pytest.raises(apps.EasyAdminError) as caught:
        apps.parse_changes(raw)
    assert message in str(caught.value)


def test_parse_changes_limits_the_batch():
    raw = [change("macro", "m%d" % i, "search", delete=True) for i in range(apps.MAX_CHANGES + 1)]
    with pytest.raises(apps.EasyAdminError):
        apps.parse_changes(raw)


def test_private_acl_drops_role_lists():
    parsed = apps.parse_changes([change("macro", "m", "search", acl={
        "sharing": "user", "owner": "alice", "read": ["*"], "write": ["admin"]})])
    assert parsed[0]["acl"] == {"sharing": "user", "owner": "alice"}
    assert apps.acl_postargs(parsed[0]["acl"]) == {"sharing": "user", "owner": "alice"}


def test_acl_postargs_always_send_sharing_and_join_roles():
    args = apps.acl_postargs({"sharing": "global", "owner": "nobody", "read": ["*"], "write": ["admin", "sc_admin"]})
    assert args == {"sharing": "global", "owner": "nobody", "perms.read": "*", "perms.write": "admin,sc_admin"}
    assert apps.acl_postargs({"sharing": "app", "owner": "a", "read": [], "write": []})["perms.write"] == ""


# ----------------------------------------------------------------- applying

def test_move_keeps_namespace_and_reports_new_app():
    gateway = FakeGateway([("macro", entry("macro", "m1", "search"))])
    result = apps.submit_changes(gateway, [change("macro", "m1", "search", move_to="myapp")], user="admin")
    assert result["applied"] == 1 and result["failed"] == 0
    assert result["results"][0]["moved_to"] == "myapp"
    assert ("move", "/servicesNS/nobody/search/admin/macros/m1", "myapp", "nobody") in gateway.calls
    assert "/servicesNS/nobody/myapp/admin/macros/m1" in gateway.objects


def test_private_object_moves_within_its_owners_namespace():
    gateway = FakeGateway([("macro", entry("macro", "mine", "search", owner="alice", sharing="user"))])
    apps.submit_changes(gateway, [change("macro", "mine", "search", ns="alice", move_to="myapp")])
    assert ("move", "/servicesNS/alice/search/admin/macros/mine", "myapp", "alice") in gateway.calls


def test_object_in_default_is_neither_moved_nor_deleted():
    gateway = FakeGateway([("macro", entry("macro", "shipped", "search", local=False))])
    result = apps.submit_changes(gateway, [change("macro", "shipped", "search", move_to="myapp")])
    assert result["failed"] == 1
    assert "default folder" in result["results"][0]["message"]
    result = apps.submit_changes(gateway, [change("macro", "shipped", "search", delete=True)])
    assert result["failed"] == 1
    assert not [c for c in gateway.calls if c[0] in ("move", "delete")]


def test_object_in_default_can_still_be_repermissioned():
    gateway = FakeGateway([("macro", entry("macro", "shipped", "search", local=False))])
    result = apps.submit_changes(gateway, [change("macro", "shipped", "search", acl={
        "sharing": "global", "owner": "nobody", "read": ["*"], "write": ["admin"]})])
    assert result["applied"] == 1
    assert gateway.objects["/servicesNS/nobody/search/admin/macros/shipped"][1]["acl"]["sharing"] == "global"


def test_move_then_acl_writes_acl_at_the_new_location():
    gateway = FakeGateway([("savedsearch", entry("savedsearch", "Report A", "search"))])
    result = apps.submit_changes(gateway, [change("savedsearch", "Report A", "search", move_to="myapp", acl={
        "sharing": "global", "owner": "admin", "read": ["*"], "write": ["admin"]})])
    assert result["applied"] == 1
    acl_calls = [c for c in gateway.calls if c[0] == "acl"]
    assert acl_calls[0][1] == "/servicesNS/nobody/myapp/saved/searches/Report%20A"
    assert acl_calls[0][2]["perms.read"] == "*"


def test_acl_failure_after_move_reports_both():
    path = "/servicesNS/nobody/myapp/admin/macros/m1"
    gateway = FakeGateway([("macro", entry("macro", "m1", "search"))], refuse_acl=[path])
    result = apps.submit_changes(gateway, [change("macro", "m1", "search", move_to="myapp", acl={
        "sharing": "app", "owner": "admin", "read": ["*"], "write": []})])
    outcome = result["results"][0]
    assert outcome["status"] == "error" and outcome["moved_to"] == "myapp"
    assert outcome["message"].startswith("Moved to myapp, but its permissions were not changed")


def test_object_without_permission_rights_is_refused_before_writing():
    gateway = FakeGateway([("macro", entry("macro", "m1", "search", can_change_perms=False))])
    result = apps.submit_changes(gateway, [change("macro", "m1", "search", acl={
        "sharing": "app", "owner": "admin", "read": ["*"], "write": []})])
    assert result["failed"] == 1
    assert "cannot change the permissions" in result["results"][0]["message"]
    assert not [c for c in gateway.calls if c[0] == "acl"]


def test_missing_object_is_reported_and_others_still_apply():
    gateway = FakeGateway([("macro", entry("macro", "m1", "search"))])
    result = apps.submit_changes(gateway, [
        change("macro", "gone", "search", delete=True),
        change("macro", "m1", "search", delete=True),
    ])
    assert (result["applied"], result["failed"]) == (1, 1)
    assert "no longer in search" in result["results"][0]["message"]
    assert gateway.objects == {}


def test_post_accepts_json_and_form_bodies():
    gateway = FakeGateway([("macro", entry("macro", "m1", "search")), ("macro", entry("macro", "m2", "search"))])
    body = json.dumps({"changes": [change("macro", "m1", "search", delete=True)]})
    status, result = apps.handle_request("POST", body, {}, gateway)
    assert status == 200 and result["applied"] == 1
    form = "changes=" + json.dumps([change("macro", "m2", "search", delete=True)])
    status, result = apps.handle_request("POST", form, {}, gateway)
    assert status == 200 and result["applied"] == 1


@pytest.mark.parametrize("body, status", [("", 400), ("[1]", 400), ("{not json", 400), ("a=b", 400)])
def test_post_rejects_malformed_bodies(body, status):
    assert apps.handle_request("POST", body, {}, FakeGateway())[0] == status


def test_other_methods_are_refused():
    assert apps.handle_request("DELETE", None, {}, FakeGateway())[0] == 405
