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
          read=("*",), write=("admin",), can_change_perms=True, content=None, fields=None, can_write=True):
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
                "can_share_global": True, "removable": local, "can_write": can_write},
        "links": links,
        "fields": fields or {},
        "content": dict(content or {"disabled": False}),
    }


class FakeGateway(object):
    def __init__(self, objects=(), app_names=("search", "myapp", "other"), refuse_acl=(),
                 refuse_create=None, restart=False, capabilities=("edit_local_apps",)):
        self.app_names = list(app_names)
        self.refuse_create = dict(refuse_create or {})   # app name -> HTTP status splunkd answers
        self.restart = restart                           # True, False or a GatewayError to raise
        self.capabilities = list(capabilities)
        self.objects = {}   # path -> (type_id, entry)
        for type_id, item in objects:
            self.objects[self._path(type_id, item)] = (type_id, item)
        self.refuse_acl = set(refuse_acl)
        self.calls = []
        # Kept apart from calls: some tests assert calls exactly. Which of the
        # two context reads ran matters, since current_context costs a second
        # splunkd request (the theme) that capability checks do not need.
        self.context_reads = []

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
        self.context_reads.append("current_context")
        return {"username": "admin", "theme": "dark", "capabilities": self.capabilities}

    def caller_capabilities(self):
        self.context_reads.append("caller_capabilities")
        return list(self.capabilities)

    def create_app(self, args):
        self.calls.append(("create_app", dict(args)))
        if args["name"] in self.refuse_create:
            raise GatewayError("App '%s' already exists. Nothing was created." % args["name"],
                               status=self.refuse_create[args["name"]])
        self.app_names.append(args["name"])

    def restart_required(self):
        if isinstance(self.restart, Exception):
            raise self.restart
        return self.restart

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
        if path not in self.objects:
            return   # a copy made through a conf file: nothing to update here
        type_id, item = self.objects[path]
        item["acl"]["sharing"] = postargs["sharing"]
        item["acl"]["owner"] = postargs["owner"]

    def create_object(self, collection, args):
        self.calls.append(("create", collection, dict(args)))
        type_id = next(t for t, spec in apps.TYPES.items() if collection.endswith("/" + spec["endpoint"]))
        ns, app = apps.namespace_of(HOST + collection)
        item = entry(type_id, args["name"], app, ns=ns)
        self.objects[apps.object_path(type_id, ns, app, args["name"])] = (type_id, item)

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
    ([change("macro", "m", "search", move_to="search")], 'already in "search"'),
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
    assert outcome["message"].startswith('Moved to "myapp", but its permissions were not changed')


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
    assert 'no longer in "search"' in result["results"][0]["message"]
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


# ------------------------------------------------------------------- copying

MACRO_FIELDS = {"required": ["definition"], "optional": ["args", "description", "iseval", "disabled"],
                "wildcard": []}


def test_copy_args_send_only_writable_fields_as_text():
    item = entry("savedsearch", "Report", "search", content={
        "search": "index=x", "is_scheduled": False, "dispatch.earliest_time": "-1h", "cron_schedule": "",
        "max_concurrent": 1, "eai:acl": {"app": "search"}, "eai:appName": "search", "next_scheduled_time": "x",
        "embed.enabled": None}, fields={"required": [], "optional": ["search", "is_scheduled", "cron_schedule",
                                                                    "max_concurrent", "embed.enabled"],
                                         "wildcard": ["dispatch\\..*"]})
    assert apps.copy_args(item) == {"name": "Report", "search": "index=x", "is_scheduled": "0",
                                    "dispatch.earliest_time": "-1h", "cron_schedule": "",
                                    "max_concurrent": "1"}


def test_copy_args_keep_a_dashboards_source():
    item = entry("view", "home", "search", content={"eai:data": "<dashboard/>", "isDashboard": True},
                 fields={"required": ["eai:data"], "optional": [], "wildcard": []})
    assert apps.copy_args(item) == {"name": "home", "eai:data": "<dashboard/>"}


def test_copy_creates_the_object_in_the_target_with_the_sources_permissions():
    source = entry("macro", "m1", "search", sharing="global", read=("*",), write=("admin", "power"),
                   content={"definition": "index=x", "disabled": False}, fields=MACRO_FIELDS)
    gateway = FakeGateway([("macro", source)])
    result = apps.submit_changes(gateway, [change("macro", "m1", "search", copy_to="myapp")], user="admin")
    assert result["applied"] == 1, result
    assert 'Copied search macro "m1" to "myapp".' == result["results"][0]["message"]
    create = [c for c in gateway.calls if c[0] == "create"][0]
    assert create[1] == "/servicesNS/nobody/myapp/admin/macros"
    assert create[2] == {"name": "m1", "definition": "index=x", "disabled": "0"}
    acl = [c for c in gateway.calls if c[0] == "acl"][0]
    assert acl[1] == "/servicesNS/nobody/myapp/admin/macros/m1"
    assert acl[2] == {"sharing": "global", "owner": "nobody", "perms.read": "*", "perms.write": "admin,power"}
    # The original stays where it was.
    assert "/servicesNS/nobody/search/admin/macros/m1" in gateway.objects


def test_an_object_in_default_can_be_copied():
    source = entry("macro", "shipped", "search", local=False, content={"definition": "x"}, fields=MACRO_FIELDS)
    gateway = FakeGateway([("macro", source)])
    result = apps.submit_changes(gateway, [change("macro", "shipped", "search", copy_to="myapp")])
    assert result["applied"] == 1, result


def test_private_copy_stays_in_its_owners_namespace():
    source = entry("macro", "mine", "search", owner="alice", sharing="user", content={"definition": "x"},
                   fields=MACRO_FIELDS)
    gateway = FakeGateway([("macro", source)])
    apps.submit_changes(gateway, [change("macro", "mine", "search", ns="alice", copy_to="myapp")])
    assert [c[1] for c in gateway.calls if c[0] == "create"] == ["/servicesNS/alice/myapp/admin/macros"]
    assert not [c for c in gateway.calls if c[0] == "acl"]


def test_copy_refuses_to_overwrite_an_object_in_the_target():
    gateway = FakeGateway([("macro", entry("macro", "m1", "search", fields=MACRO_FIELDS)),
                           ("macro", entry("macro", "m1", "myapp"))])
    result = apps.submit_changes(gateway, [change("macro", "m1", "search", copy_to="myapp")])
    assert result["failed"] == 1
    assert 'already exists in "myapp"' in result["results"][0]["message"]
    assert not [c for c in gateway.calls if c[0] == "create"]


def test_copy_and_a_permission_change_on_the_original():
    gateway = FakeGateway([("macro", entry("macro", "m1", "search", content={"definition": "x"},
                                           fields=MACRO_FIELDS))])
    result = apps.submit_changes(gateway, [change("macro", "m1", "search", copy_to="myapp", acl={
        "sharing": "global", "owner": "nobody", "read": ["*"], "write": []})])
    assert result["applied"] == 1
    assert "changed the original's permissions" in result["results"][0]["message"]
    assert gateway.objects["/servicesNS/nobody/search/admin/macros/m1"][1]["acl"]["sharing"] == "global"


@pytest.mark.parametrize("raw, message", [
    ([change("macro", "m", "search", copy_to="other", move_to="myapp")], "either moved or copied"),
    ([change("macro", "m", "search", copy_to="other", delete=True)], "cannot also be moved, copied"),
    ([change("lookupfile", "a.csv", "search", copy_to="other")], "cannot be copied"),
    ([change("nav", "default", "search", copy_to="other")], "cannot be copied"),
    ([change("extraction", "st : EXTRACT-x", "search", copy_to="other")], "cannot be copied"),
    ([change("tag", "eventtype=web", "search", copy_to="other")], "cannot be copied"),
    ([change("macro", "m", "search", copy_to="search")], 'already in "search"'),
    ([change("macro", "m", "search", copy_to="system")], "not an app that objects can be copied to"),
])
def test_copy_requests_are_validated(raw, message):
    with pytest.raises(apps.EasyAdminError) as caught:
        apps.parse_changes(raw)
    assert message in str(caught.value)


def test_model_says_which_objects_can_be_copied():
    gateway = FakeGateway([("macro", entry("macro", "m1", "search")),
                           ("lookupfile", entry("lookupfile", "a.csv", "search"))])
    by_type = {o["type"]: o for o in apps.read_model(gateway)["objects"]}
    assert by_type["macro"]["copyable"] is True
    assert by_type["lookupfile"]["copyable"] is False


class VisibleGateway(FakeGateway):
    """splunkd's visibility: a global object answers under every app's namespace."""

    def get_object(self, path, full=False):
        self.calls.append(("get", path))
        if path in self.objects:
            return self.objects[path][1]
        ns, app = apps.namespace_of(HOST + path)
        name = path.rsplit("/", 1)[1]
        for type_id, item in self.objects.values():
            if item["acl"]["sharing"] == "global" and path.endswith(
                    "/%s/%s" % (apps.TYPES[type_id]["endpoint"], name)):
                return item
        raise GatewayError("Object not found.", status=404)


def test_a_global_object_seen_from_the_target_app_is_not_a_clash():
    source = entry("macro", "m1", "search", sharing="global", content={"definition": "x"}, fields=MACRO_FIELDS)
    gateway = VisibleGateway([("macro", source)])
    result = apps.submit_changes(gateway, [change("macro", "m1", "search", copy_to="myapp")])
    assert result["applied"] == 1, result


def test_a_change_never_lands_on_another_apps_object_of_the_same_name():
    # m1 is no longer in myapp; a global m1 in search is still visible from
    # there, and must not be deleted in its place.
    gateway = VisibleGateway([("macro", entry("macro", "m1", "search", sharing="global"))])
    result = apps.submit_changes(gateway, [change("macro", "m1", "myapp", delete=True)])
    assert result["failed"] == 1 and 'no longer in "myapp"' in result["results"][0]["message"]
    assert not [c for c in gateway.calls if c[0] == "delete"]


def test_details_of_an_object_in_another_app_are_not_returned():
    gateway = VisibleGateway([("macro", entry("macro", "m1", "search", sharing="global"))])
    status, _ = apps.handle_request("GET", None, {"type": "macro", "ns": "nobody", "app": "myapp",
                                                  "name": "m1"}, gateway)
    assert status == 404


def test_a_copy_whose_permissions_cannot_be_set_is_removed_again():
    source = entry("savedsearch", "Runs as owner", "search", owner="alice", sharing="global",
                   content={"search": "index=x"}, fields={"required": [], "optional": ["search"], "wildcard": []})
    gateway = FakeGateway([("savedsearch", source)],
                          refuse_acl=["/servicesNS/nobody/myapp/saved/searches/Runs%20as%20owner"])
    result = apps.submit_changes(gateway, [change("savedsearch", "Runs as owner", "search", copy_to="myapp")])
    outcome = result["results"][0]
    assert outcome["status"] == "error" and outcome["copied_to"] is None
    assert 'was not copied to "myapp"' in outcome["message"] and "removed again" in outcome["message"]
    assert ("delete", "/servicesNS/nobody/myapp/saved/searches/Runs%20as%20owner") in gateway.calls
    assert "/servicesNS/nobody/myapp/saved/searches/Runs%20as%20owner" not in gateway.objects


def test_copy_done_but_original_permissions_refused_reports_the_copy():
    gateway = FakeGateway([("macro", entry("macro", "m1", "search", content={"definition": "x"},
                                           fields=MACRO_FIELDS))],
                          refuse_acl=["/servicesNS/nobody/search/admin/macros/m1"])
    result = apps.submit_changes(gateway, [change("macro", "m1", "search", copy_to="myapp", acl={
        "sharing": "global", "owner": "nobody", "read": ["*"], "write": []})])
    outcome = result["results"][0]
    assert outcome["status"] == "error" and outcome["copied_to"] == "myapp"
    assert outcome["message"].startswith('Copied to "myapp", but the original\'s permissions were not changed')
    assert "/servicesNS/nobody/myapp/admin/macros/m1" in gateway.objects


# ------------------------------------------------------- explicit settings

def test_explicit_settings_merge_the_objects_own_layers():
    files = {
        "default": "[default]\ndispatch.earliest_time = -24h\n[Report]\nsearch = index=a\ndescription = old\n",
        "local": "[Report]\ndescription = new\ncron_schedule = 0 * * * *\n[Other]\nsearch = index=b\n",
        "user": None,
    }
    settings = apps.explicit_settings({k: v for k, v in files.items() if v}, "Report")
    assert [(s["name"], s["value"], s["layer"]) for s in settings] == [
        ("cron_schedule", "0 * * * *", "local"),
        ("description", "new", "local"),
        ("search", "index=a", "default"),
    ]


def test_explicit_settings_mask_secrets_and_ignore_the_default_stanza():
    settings = apps.explicit_settings({"local": "[a]\npassword = hunter2\n[default]\nx = 1\n"}, "a")
    assert settings == [{"name": "password", "layer": "local", "value": "********", "truncated": False,
                         "secret": True, "overrides": []}]


def test_private_object_settings_come_from_the_owners_folder():
    settings = apps.explicit_settings({"local": "[m]\ndefinition = shared\n", "user": "[m]\ndefinition = mine\n"}, "m")
    assert settings == [{"name": "definition", "layer": "user", "value": "mine", "truncated": False,
                         "secret": False, "overrides": [{"layer": "local", "value": "shared", "truncated": False}]}]


class ConfGateway(FakeGateway):
    def __init__(self, objects=(), capabilities=("admin_all_objects",), files=None):
        FakeGateway.__init__(self, objects, capabilities=capabilities)
        self.files = files or {}
        self.reads = []

    def read_own_conf(self, conf, app, user):
        self.reads.append((conf, app, user))
        return self.files


def test_details_include_the_objects_own_settings_for_admins():
    gateway = ConfGateway([("macro", entry("macro", "m1", "search", content={"definition": "x", "iseval": False}))],
                          files={"local": "[m1]\ndefinition = x\n"})
    status, body = apps.handle_request("GET", None, {"type": "macro", "ns": "nobody", "app": "search", "name": "m1"},
                                       gateway)
    assert status == 200
    assert body["explicit"] == [{"name": "definition", "layer": "local", "value": "x", "truncated": False,
                                 "secret": False, "overrides": []}]
    assert body["explicit_conf"] == "macros" and body["explicit_note"] is None
    assert gateway.reads == [("macros", "search", None)]
    assert len(body["settings"]) == 2   # the full list is still there, for "show all"


def test_private_objects_also_read_the_owners_folder():
    gateway = ConfGateway([("macro", entry("macro", "mine", "search", owner="alice", sharing="user"))])
    apps.handle_request("GET", None, {"type": "macro", "ns": "alice", "app": "search", "name": "mine"}, gateway)
    assert gateway.reads == [("macros", "search", "alice")]


def test_without_admin_all_objects_no_files_are_read():
    gateway = ConfGateway([("macro", entry("macro", "m1", "search"))], capabilities=("search",))
    status, body = apps.handle_request("GET", None, {"type": "macro", "ns": "nobody", "app": "search", "name": "m1"},
                                       gateway)
    assert status == 200 and body["explicit"] is None and body["explicit_note"] == "capability"
    assert gateway.reads == []


def test_types_without_a_stanza_say_so():
    gateway = ConfGateway([("view", entry("view", "home", "search"))])
    status, body = apps.handle_request("GET", None, {"type": "view", "ns": "nobody", "app": "search", "name": "home"},
                                       gateway)
    assert body["explicit"] is None and body["explicit_note"] == "kind" and gateway.reads == []


# -------------------------------------------- objects in default with links

def _shipped_report(name="Shipped report"):
    # As splunkd lists a saved search from a default folder: move and remove
    # links, but acl.removable false (observed on 10.6.1).
    item = entry("savedsearch", name, "search", content={"search": "index=x"},
                 fields={"required": [], "optional": ["search"], "wildcard": []})
    item["acl"]["removable"] = False
    return item


def test_a_link_without_removable_does_not_make_an_object_movable():
    obj = apps.build_object("savedsearch", _shipped_report())
    assert obj["movable"] is False and obj["removable"] is False and obj["copyable"] is True


def test_moving_it_is_refused_before_splunkd_and_a_copy_is_offered():
    gateway = FakeGateway([("savedsearch", _shipped_report())])
    result = apps.submit_changes(gateway, [change("savedsearch", "Shipped report", "search", move_to="myapp")])
    outcome = result["results"][0]
    assert outcome["status"] == "error" and outcome["copy_instead"] is True
    assert outcome["message"] == ('"Shipped report" ships in the "search" app\'s default folder, '
                                  'so it cannot be moved. Copy it instead.')
    assert not [c for c in gateway.calls if c[0] == "move"]


def test_splunkds_own_refusal_reads_plainly_and_offers_a_copy():
    class Refusing(FakeGateway):
        def move_object(self, path, app, user):
            raise GatewayError("This saved search failed to handle move request due to Object id=x cannot "
                               "be deleted and thus it cannot be moved in config=savedsearches", status=400)
    gateway = Refusing([("macro", entry("macro", "m1", "search"))])
    outcome = apps.submit_changes(gateway, [change("macro", "m1", "search", move_to="myapp")])["results"][0]
    assert outcome["copy_instead"] is True
    assert outcome["message"].startswith('"m1" ships in the "search" app\'s default folder, so splunkd will not')


def test_deleting_it_is_refused_too():
    gateway = FakeGateway([("savedsearch", _shipped_report())])
    outcome = apps.submit_changes(gateway, [change("savedsearch", "Shipped report", "search",
                                                   delete=True)])["results"][0]
    assert outcome["status"] == "error" and "cannot be deleted" in outcome["message"]
    assert not [c for c in gateway.calls if c[0] == "delete"]


# ------------------------------------------------------------- creating apps

def new_app(name="my_app", **fields):
    spec = {"name": name, "label": "My App"}
    spec.update(fields)
    return spec


def test_new_app_sends_exactly_the_allowed_postargs():
    gateway = FakeGateway()
    result = apps.submit_changes(gateway, None, user="admin", raw_apps=[
        new_app(description="Notes", author="alice", visible=False, version="2.1")])
    assert gateway.calls == [("create_app", {"name": "my_app", "template": "barebones", "label": "My App",
                                             "visible": "0", "version": "2.1", "description": "Notes",
                                             "author": "alice"})]
    assert result["apps"] == [{"name": "my_app", "status": "applied", "message": 'Created the app "my_app".'}]
    assert (result["applied"], result["failed"], result["results"]) == (1, 0, [])


def test_new_app_defaults_to_version_1_0_0_and_omits_empty_text():
    gateway = FakeGateway()
    apps.submit_changes(gateway, [], raw_apps=[new_app(description="", author="  ")])
    assert gateway.calls[0][1] == {"name": "my_app", "template": "barebones", "label": "My App",
                                   "visible": "1", "version": "1.0.0"}


@pytest.mark.parametrize("spec, text", [
    (new_app(filename="/tmp/x.tgz"), "filename"),
    (new_app(template="sample_app"), "template"),
    (new_app("has space"), "not a valid app ID"),
    (new_app("a/b"), "not a valid app ID"),
    (new_app(".."), "not a valid app ID"),
    (new_app("-lead"), "not a valid app ID"),
    (new_app("x" * 101), "longer than 100"),
    (new_app(""), "needs an app ID"),
    (new_app("system"), "already exists"),
    (new_app("myapp"), "already exists"),
    (new_app("MyApp"), "already exists"),
    (new_app(label="abcd"), "at least 5"),
    (new_app(label="x" * 81), "longer than 80"),
    (new_app(label="Splunk for Things"), "Splunk for"),
    (new_app(label="splunk FOR things"), "Splunk for"),
    (new_app(label="    "), "label is required"),
    (new_app(label=5), "must be text"),
    (new_app(description="a\x00b"), "control characters"),
    (new_app(author="a\nb"), "control characters"),
    (new_app(version="1.0 beta"), "not a valid version"),
    (new_app(version="../1"), "not a valid version"),
    (new_app(visible="yes"), "true or false"),
    ("my_app", "must be an object"),
])
def test_new_app_refusals_create_nothing(spec, text):
    gateway = FakeGateway()
    with pytest.raises(apps.EasyAdminError) as caught:
        apps.submit_changes(gateway, None, raw_apps=[spec])
    assert text in str(caught.value) and caught.value.status == 400
    assert not [c for c in gateway.calls if c[0] == "create_app"]


def test_new_apps_must_be_a_short_list_of_distinct_names():
    gateway = FakeGateway()
    with pytest.raises(apps.EasyAdminError, match="must be a list"):
        apps.submit_changes(gateway, None, raw_apps={"name": "x"})
    with pytest.raises(apps.EasyAdminError, match="At most 20"):
        apps.submit_changes(gateway, None, raw_apps=[new_app("a%d" % n) for n in range(21)])
    with pytest.raises(apps.EasyAdminError, match="named twice"):
        apps.submit_changes(gateway, None, raw_apps=[new_app("one"), new_app("ONE")])
    assert not [c for c in gateway.calls if c[0] == "create_app"]


def test_creating_apps_needs_one_of_the_two_capabilities():
    gateway = FakeGateway(capabilities=("search",))
    with pytest.raises(apps.EasyAdminError) as caught:
        apps.submit_changes(gateway, None, raw_apps=[new_app()])
    assert caught.value.status == 403 and not [c for c in gateway.calls if c[0] == "create_app"]
    for cap in apps.CREATE_APP_CAPS:
        gateway = FakeGateway(capabilities=(cap,))
        assert apps.submit_changes(gateway, None, raw_apps=[new_app()])["applied"] == 1


def test_changes_alone_need_no_create_capability():
    gateway = FakeGateway([("macro", entry("macro", "m1", "search"))], capabilities=())
    assert apps.submit_changes(gateway, [change("macro", "m1", "search", delete=True)])["applied"] == 1


def test_a_request_with_neither_apps_nor_changes_is_refused():
    for changes, new in ((None, None), ([], []), ([], None)):
        with pytest.raises(apps.EasyAdminError):
            apps.submit_changes(FakeGateway(), changes, raw_apps=new)


def test_apps_are_created_before_objects_are_copied_into_them():
    gateway = FakeGateway([("macro", entry("macro", "m1", "search"))])
    result = apps.submit_changes(gateway, [change("macro", "m1", "search", copy_to="my_app")],
                                 raw_apps=[new_app()])
    kinds = [c[0] for c in gateway.calls]
    assert kinds.index("create_app") < kinds.index("create")
    assert result["results"][0]["status"] == "applied" and result["failed"] == 0 and result["applied"] == 2


def test_a_change_into_an_app_that_was_not_created_is_not_attempted():
    gateway = FakeGateway([("macro", entry("macro", "m1", "search")), ("macro", entry("macro", "m2", "search"))],
                          refuse_create={"my_app": 409})
    result = apps.submit_changes(gateway, [change("macro", "m1", "search", copy_to="my_app"),
                                           change("macro", "m2", "search", move_to="my_app")],
                                 raw_apps=[new_app()])
    assert result["apps"][0]["status"] == "error"
    assert result["apps"][0]["message"] == 'An app called "my_app" already exists, so it was not created.'
    assert [r["message"] for r in result["results"]] == [
        '"m1" was not copied: the app "my_app" was not created.',
        '"m2" was not moved: the app "my_app" was not created.']
    assert [r["status"] for r in result["results"]] == ["error", "error"]
    assert (result["applied"], result["failed"]) == (0, 3)
    assert not [c for c in gateway.calls if c[0] in ("create", "move")]


def test_another_refusal_is_reported_per_app_and_the_rest_go_on():
    gateway = FakeGateway(refuse_create={"first": 403})
    result = apps.submit_changes(gateway, None, raw_apps=[new_app("first"), new_app("second")])
    assert [a["status"] for a in result["apps"]] == ["error", "applied"]
    assert result["apps"][0]["message"].startswith('The app "first" was not created: ')
    assert "second" in gateway.app_names


def test_restart_required_is_read_from_splunkd_after_everything_ran():
    assert apps.submit_changes(FakeGateway(restart=True), None, raw_apps=[new_app()])["restart_required"] is True
    assert apps.submit_changes(FakeGateway(restart=False), None, raw_apps=[new_app()])["restart_required"] is False


def test_a_failed_restart_check_never_fails_the_apply():
    gateway = FakeGateway(restart=GatewayError("no", status=403))
    result = apps.submit_changes(gateway, None, raw_apps=[new_app()])
    assert result["restart_required"] is False and result["applied"] == 1


def test_post_carries_apps_and_changes_in_one_json_document():
    gateway = FakeGateway([("macro", entry("macro", "m1", "search"))])
    body = json.dumps({"apps": [new_app()], "changes": [change("macro", "m1", "search", copy_to="my_app")]})
    status, result = apps.handle_request("POST", body, {}, gateway)
    assert status == 200 and result["applied"] == 2
    status, result = apps.handle_request("POST", json.dumps({"apps": [new_app("other_two")]}), {}, gateway)
    assert status == 200 and result["applied"] == 1
    status, result = apps.handle_request("POST", json.dumps({"apps": [new_app("third")]}), {},
                                         FakeGateway(capabilities=()))
    assert status == 403


def test_model_says_whether_the_caller_can_create_apps():
    for caps, expected in (((), False), (("search",), False), (("edit_local_apps",), True),
                           (("admin_all_objects",), True)):
        assert apps.read_model(FakeGateway(capabilities=caps))["can_create_apps"] is expected


# ------------------------------------- capability checks skip the theme lookup

def test_a_details_click_reads_the_context_once_and_not_the_theme():
    gateway = ConfGateway([("macro", entry("macro", "m1", "search", content={"definition": "x"}))],
                          files={"local": "[m1]\ndefinition = x\n"})
    status, body = apps.handle_request("GET", None, {"type": "macro", "ns": "nobody", "app": "search", "name": "m1"},
                                       gateway)
    assert status == 200 and body["explicit"] is not None
    assert gateway.context_reads == ["caller_capabilities"]


def test_a_details_click_without_admin_all_objects_still_reads_the_context_once():
    gateway = ConfGateway([("macro", entry("macro", "m1", "search"))], capabilities=("search",))
    status, body = apps.handle_request("GET", None, {"type": "macro", "ns": "nobody", "app": "search", "name": "m1"},
                                       gateway)
    assert status == 200 and body["explicit_note"] == "capability"
    assert gateway.context_reads == ["caller_capabilities"]


def test_the_model_still_reads_the_full_context_for_the_theme():
    gateway = FakeGateway()
    assert apps.read_model(gateway)["theme"] == "dark"
    assert gateway.context_reads == ["current_context"]


def test_creating_apps_checks_capabilities_without_the_theme():
    gateway = FakeGateway(capabilities=("edit_local_apps",))
    apps.submit_changes(gateway, None, raw_apps=[new_app()])
    assert gateway.context_reads == ["caller_capabilities"]
