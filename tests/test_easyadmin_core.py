"""Unit tests for easyadmin_core: the role model and bulk updates.

The module imports nothing from Splunk; splunkd is replaced by FakeGateway,
which holds roles in memory and records every write.
"""

import json

import pytest

import easyadmin_core as core


class FakeGateway(object):
    """An in-memory stand-in for easyadmin_rest.SplunkdGateway."""

    def __init__(self, roles=None, indexes=None, capabilities=(),
                 user_capabilities=("edit_roles",), user_roles=("admin",), refuse=()):
        self.roles = {name: dict(content) for name, content in (roles or {}).items()}
        self.indexes = list(indexes or [])
        self.capabilities = list(capabilities)
        self.context = {"capabilities": list(user_capabilities), "roles": list(user_roles)}
        self.refuse = set(refuse)  # role names splunkd will not let us write
        self.writes = []

    def list_roles(self):
        return [{"name": name, "content": content} for name, content in self.roles.items()]

    def list_indexes(self):
        return [{"name": name, "content": {"datatype": "event", "disabled": False}}
                for name in self.indexes]

    def list_capabilities(self):
        return self.capabilities

    def current_context(self):
        return self.context

    def get_role(self, name):
        if name not in self.roles:
            raise core.GatewayError("Role %s was not found." % name, status=404)
        return self.roles[name]

    def update_role(self, name, fields):
        if name in self.refuse:
            raise core.GatewayError("You do not have permission to edit %s." % name, status=403)
        self.writes.append((name, dict(fields)))
        self.roles[name].update(fields)


def grant(role, item, on=True, field="srchIndexesAllowed"):
    return {"role": role, "field": field, "item": item, "grant": on}


def setting(role, field, value, previous):
    return {"role": role, "field": field, "value": value, "previous": previous}


def tab(model, tab_id):
    return next(t for t in model["tabs"] if t["id"] == tab_id)


def model(roles, indexes=(), capabilities=(), **context):
    return core.read_model(FakeGateway(roles, indexes, capabilities, **context))


# ------------------------------------------------------------------ helpers

@pytest.mark.parametrize("value, expected", [
    (None, []),
    ("", []),
    ("main", ["main"]),  # splunkd sends a lone value as a bare string
    (["main", "", None, "web"], ["main", "web"]),
])
def test_as_list_normalises_rest_values(value, expected):
    assert core.as_list(value) == expected


@pytest.mark.parametrize("value, expected", [
    (None, ""), ("", ""), ("10", "10"), (10, "10"), (True, "1"), (["a", "b"], "a,b"),
])
def test_as_text_normalises_rest_values(value, expected):
    assert core.as_text(value) == expected


@pytest.mark.parametrize("pattern, index, expected", [
    ("main", "main", True),
    ("main", "main2", False),
    ("*", "main", True),
    ("web*", "web_prod", True),
    ("web*", "myweb", False),
    ("*_prod", "web_prod", True),
    # Splunk's rule: a pattern must itself start with _ to reach internal indexes.
    ("*", "_internal", False),
    ("_*", "_internal", True),
    ("_*", "main", False),
    # Regex metacharacters in a name are literal.
    ("a.c*", "abc", False),
    ("a.c*", "a.c1", True),
])
def test_pattern_matches(pattern, index, expected):
    assert core.pattern_matches(pattern, index) is expected


# -------------------------------------------------------------------- model

def test_model_has_every_tab_in_order():
    m = model({"user": {}})
    assert [(t["id"], t["type"]) for t in m["tabs"]] == [
        ("indexes", "matrix"), ("capabilities", "matrix"), ("inheritance", "matrix"),
        ("limits", "settings"), ("federated", "settings"),
    ]
    assert [f["name"] for f in tab(m, "indexes")["fields"]] == [
        "srchIndexesAllowed", "srchIndexesDefault", "srchIndexesDisallowed", "deleteIndexesAllowed"]


def test_every_edited_attribute_appears_once():
    names = list(core.MATRIX_FIELDS) + list(core.SETTING_KINDS)
    assert len(names) == len(set(names))
    # The writable fields splunkd 10.6.1 lists for authorization/roles/_new,
    # less the wildcard srchMinScheduleInterval.* family, which is not edited.
    assert set(names) == {
        "capabilities", "cumulativeRTSrchJobsQuota", "cumulativeSrchJobsQuota", "defaultApp",
        "deleteIndexesAllowed", "federatedProviders", "fieldFilterExemption", "grantable_roles",
        "imported_roles", "kvstore_create.deny_list", "kvstore_create.implicit_deny_list",
        "kvstore_delete.deny_list", "kvstore_delete.implicit_deny_list",
        "kvstore_update.deny_list", "kvstore_update.implicit_deny_list", "queuedSearchQuota",
        "rtSrchJobsQuota", "srchAllowAdvancedCron", "srchDiskQuota",
        "srchFederatedProvidersAllowed", "srchFederatedProvidersDefault", "srchFilter",
        "srchIndexesAllowed", "srchIndexesDefault", "srchIndexesDisallowed", "srchJobsQuota",
        "srchMinScheduleInterval", "srchTimeEarliest", "srchTimeWin",
    }


def test_index_tab_columns_include_wildcards_and_unknown_names():
    """Entries a role holds that are not real indexes still get a column to untick."""
    t = tab(model({"power": {"srchIndexesAllowed": ["*", "retired_idx", "main"]}},
                  ["main", "_internal"]), "indexes")
    assert [(c["name"], c["kind"]) for c in t["columns"]] == [
        ("*", "wildcard"), ("main", "known"), ("_internal", "known"), ("retired_idx", "unknown")]
    assert t["columns"][2]["internal"] is True
    assert t["cells"]["power"]["srchIndexesAllowed"]["explicit"] == ["*", "retired_idx", "main"]


def test_index_tab_explains_wildcard_and_inherited_access():
    t = tab(model({
        "analyst": {
            "srchIndexesAllowed": ["web*"],
            "imported_srchIndexesAllowed": ["main", "_*"],
            "imported_roles": ["user"],
        },
    }, ["main", "web_prod", "_internal", "secure"]), "indexes")
    assert t["cells"]["analyst"]["srchIndexesAllowed"]["effective"] == {
        "main": "Inherited from an imported role",
        "_*": "Inherited from an imported role",
        "web_prod": "Matched by wildcard web* on this role",
        "_internal": "Matched by wildcard _* inherited from an imported role",
    }


def test_capabilities_tab_lists_every_capability_and_marks_imported_ones():
    t = tab(model({"power": {"capabilities": ["schedule_search"],
                             "imported_capabilities": ["search"]}},
                  capabilities=["search", "schedule_search", "edit_roles"]), "capabilities")
    assert [c["name"] for c in t["columns"]] == ["edit_roles", "schedule_search", "search"]
    cell = t["cells"]["power"]["capabilities"]
    assert cell["explicit"] == ["schedule_search"]
    assert cell["effective"] == {"search": "Inherited from an imported role"}


def test_capabilities_tab_does_not_treat_names_as_wildcards():
    t = tab(model({"r": {"capabilities": ["*"]}}, capabilities=["search"]), "capabilities")
    assert ("*", "unknown") in [(c["name"], c["kind"]) for c in t["columns"]]
    assert t["cells"]["r"]["capabilities"]["effective"] == {}


def test_inheritance_tab_walks_the_import_chain():
    """admin -> power -> user: admin reaches user through power."""
    t = tab(model({
        "admin": {"imported_roles": ["power"]},
        "power": {"imported_roles": "user"},  # a lone value arrives as a string
        "user": {},
    }), "inheritance")
    assert [c["name"] for c in t["columns"]] == ["admin", "power", "user"]
    assert t["cells"]["admin"]["imported_roles"] == {
        "explicit": ["power"], "effective": {"user": "Inherited through power"}}
    assert t["cells"]["power"]["imported_roles"]["effective"] == {}


def test_inheritance_chain_tolerates_a_cycle():
    t = tab(model({"a": {"imported_roles": ["b"]}, "b": {"imported_roles": ["a"]}}), "inheritance")
    assert t["cells"]["a"]["imported_roles"]["effective"] == {}


def test_settings_tab_reports_value_and_imported_value():
    t = tab(model({"power": {"srchJobsQuota": "10", "imported_srchJobsQuota": "3",
                             "srchFilter": ""}}), "limits")
    values = t["values"]["power"]
    assert values["srchJobsQuota"] == {"value": "10", "imported": "3"}
    assert values["srchFilter"] == {"value": "", "imported": None}
    assert values["defaultApp"] == {"value": "", "imported": None}
    assert {f["name"]: f["kind"] for f in t["fields"]}["srchAllowAdvancedCron"] == "flag"


def test_list_settings_are_lists():
    t = tab(model({"admin": {"srchFederatedProvidersAllowed": "*",
                             "imported_srchFederatedProvidersAllowed": ["a", "b"]}}), "federated")
    assert t["values"]["admin"]["srchFederatedProvidersAllowed"] == {"value": ["*"], "imported": ["a", "b"]}


@pytest.mark.parametrize("capabilities, expected", [
    (["search"], False),
    (["edit_roles"], True),
    (["search", "edit_roles_grantable"], True),  # what sc_admin holds on Splunk Cloud
])
def test_model_reports_whether_user_can_edit(capabilities, expected):
    assert model({}, user_capabilities=capabilities)["can_edit"] is expected


@pytest.mark.parametrize("value, expected", [
    ("dark", "dark"),
    ("light", "light"),
    (" Dark ", "dark"),
    ("default_system_theme", None),  # leave Splunk's own choice alone
    ("", None),
    (None, None),
    ("purple", None),
])
def test_theme_preference(value, expected):
    assert core.theme_preference(value) == expected


def test_model_carries_the_users_theme_preference():
    gateway = FakeGateway({})
    gateway.context["theme"] = "dark"
    assert core.read_model(gateway)["theme"] == "dark"
    assert model({})["theme"] is None


def test_model_reports_the_users_own_roles_and_sorts_roles():
    m = model({"zeta": {}, "Alpha": {}, "beta": {}}, user_roles=["beta"])
    assert [r["name"] for r in m["roles"]] == ["Alpha", "beta", "zeta"]
    assert m["user_roles"] == ["beta"]


# ------------------------------------------------------------------ parsing

def test_parse_changes_groups_by_role():
    plan = core.parse_changes([
        grant("user", "main"),
        grant("user", "web", on=False),
        grant("user", "search", field="capabilities"),
        setting("user", "srchJobsQuota", "5", "3"),
        grant("power", "web"),
        grant("user", "main"),  # exact repeat is applied once
    ])
    assert list(plan) == ["user", "power"]
    assert plan["user"]["matrix"] == {
        "srchIndexesAllowed": {"grant": ["main"], "revoke": ["web"]},
        "capabilities": {"grant": ["search"], "revoke": []},
    }
    assert plan["user"]["settings"] == {"srchJobsQuota": ("5", "3")}


@pytest.mark.parametrize("raw, fragment", [
    ("not a list", "must be a list"),
    ([], "No changes"),
    (["x"], "not an object"),
    ([grant("", "main")], "role must be"),
    ([grant("user", " main")], "item must be"),
    ([grant("user", "main", field="srchIndexesAllowedX")], "not a role attribute"),
    ([grant("user", "main", field="imported_capabilities")], "not a role attribute"),
    ([{"role": "user", "field": "capabilities", "item": "x", "grant": "yes"}], "grant must be"),
    ([grant("user", "main"), grant("user", "main", on=False)], "both grants and revokes"),
    ([grant("user", "x" * 5000)], "longer than"),
    ([setting("user", "srchJobsQuota", "ten", "3")], "whole number"),
    ([setting("user", "srchJobsQuota", "", "3")], "must be non-empty"),
    ([setting("user", "srchAllowAdvancedCron", "2", "1")], "0 or 1"),
    ([setting("user", "federatedProviders", "a,b", [])], "takes a list"),
    ([setting("user", "srchJobsQuota", "5", None)], "previous must be"),
    ([setting("user", "srchJobsQuota", "5", "3"), setting("user", "srchJobsQuota", "6", "3")], "twice"),
])
def test_parse_changes_rejects_malformed_input(raw, fragment):
    with pytest.raises(core.EasyAdminError) as caught:
        core.parse_changes(raw)
    assert fragment in str(caught.value)
    assert caught.value.status == 400


def test_parse_changes_accepts_valid_settings():
    plan = core.parse_changes([
        setting("r", "srchTimeWin", "-1", "0"),
        setting("r", "srchFilter", "", "host=a"),
        setting("r", "srchAllowAdvancedCron", "0", "1"),
        setting("r", "federatedProviders", ["a", "b", "a"], ["a"]),
    ])
    assert plan["r"]["settings"] == {
        "srchTimeWin": ("-1", "0"),
        "srchFilter": ("", "host=a"),
        "srchAllowAdvancedCron": ("0", "1"),
        "federatedProviders": (["a", "b"], ["a"]),
    }


def test_parse_changes_enforces_the_size_cap():
    raw = [grant("user", "idx%d" % n) for n in range(core.MAX_CHANGES + 1)]
    with pytest.raises(core.EasyAdminError) as caught:
        core.parse_changes(raw)
    assert "Too many changes" in str(caught.value)


def test_apply_delta_preserves_order_and_drops_duplicates():
    assert core.apply_delta(["a", "b", "c"], ["d", "a"], ["b"]) == ["a", "c", "d"]
    assert core.apply_delta(["a"], [], ["a"]) == []
    assert core.apply_delta([], ["a", "a"], []) == ["a"]


# ------------------------------------------------------------------- submit

def test_submit_writes_each_role_once_across_tabs():
    gateway = FakeGateway({
        "user": {"srchIndexesAllowed": ["main"], "capabilities": ["search"], "srchJobsQuota": "3"},
        "power": {"srchIndexesAllowed": ["main", "web"]},
    })
    summary = core.submit_changes(gateway, [
        grant("user", "web"),
        grant("user", "main", on=False),
        grant("user", "schedule_search", field="capabilities"),
        setting("user", "srchJobsQuota", "5", "3"),
        grant("power", "web", on=False),
    ], user="alice")

    assert gateway.writes == [
        ("user", {"srchIndexesAllowed": ["web"], "capabilities": ["search", "schedule_search"],
                  "srchJobsQuota": "5"}),
        ("power", {"srchIndexesAllowed": ["main"]}),
    ]
    assert summary["updated"] == 2 and summary["failed"] == 0 and summary["unchanged"] == 0


def test_submit_applies_deltas_to_current_state_not_the_page_snapshot():
    """An item added to the role elsewhere since page load is not clobbered."""
    gateway = FakeGateway({"user": {"srchIndexesAllowed": ["main", "added_elsewhere"]}})
    core.submit_changes(gateway, [grant("user", "web")])
    assert gateway.writes == [("user", {"srchIndexesAllowed": ["main", "added_elsewhere", "web"]})]


def test_submit_refuses_a_setting_changed_since_the_page_loaded():
    gateway = FakeGateway({"user": {"srchJobsQuota": "7", "srchIndexesAllowed": []}})
    summary = core.submit_changes(gateway, [
        setting("user", "srchJobsQuota", "5", "3"),
        grant("user", "main"),
    ])
    assert gateway.writes == []  # the whole role is held back, not half-written
    assert summary["results"][0]["status"] == "error"
    assert "Changed elsewhere since the page loaded: srchJobsQuota" in summary["results"][0]["message"]


def test_submit_compares_list_settings_as_sets():
    """splunkd stores lists sorted; a reordered previous value is not a conflict."""
    gateway = FakeGateway({"user": {"federatedProviders": ["a", "b"]}})
    summary = core.submit_changes(gateway, [setting("user", "federatedProviders", ["c"], ["b", "a"])])
    assert summary["updated"] == 1
    assert gateway.writes == [("user", {"federatedProviders": ["c"]})]


def test_submit_skips_a_role_already_in_the_requested_state():
    gateway = FakeGateway({"user": {"srchIndexesAllowed": ["main"], "srchJobsQuota": "3"}})
    summary = core.submit_changes(gateway, [
        grant("user", "main"), grant("user", "web", on=False),
        setting("user", "srchJobsQuota", "3", "3"),
    ])
    assert gateway.writes == []
    assert summary["results"][0]["status"] == "unchanged"


def test_submit_can_empty_a_list():
    gateway = FakeGateway({"user": {"srchIndexesAllowed": ["main"]}})
    core.submit_changes(gateway, [grant("user", "main", on=False)])
    assert gateway.writes == [("user", {"srchIndexesAllowed": []})]


def test_append_only_setting_writes_only_new_entries():
    """splunkd appends posted fieldFilterExemption values, so only new ones are sent."""
    gateway = FakeGateway({"user": {"fieldFilterExemption": ["a"]}})
    summary = core.submit_changes(gateway, [setting("user", "fieldFilterExemption", ["a", "b"], ["a"])])
    assert summary["updated"] == 1
    assert gateway.writes == [("user", {"fieldFilterExemption": ["b"]})]


def test_append_only_setting_refuses_a_removal_and_writes_nothing():
    gateway = FakeGateway({"user": {"fieldFilterExemption": ["a", "b"], "srchIndexesAllowed": []}})
    summary = core.submit_changes(gateway, [
        setting("user", "fieldFilterExemption", ["b", "c"], ["a", "b"]),
        grant("user", "main"),
    ])
    assert gateway.writes == []
    assert summary["failed"] == 1
    assert summary["results"][0]["message"] == (
        "Splunk cannot remove fieldFilterExemption entries through its REST API (a); "
        "nothing on this role was written.")


def test_submit_reports_failures_per_role_and_carries_on():
    gateway = FakeGateway({"locked": {}, "user": {}}, refuse=["locked"])
    summary = core.submit_changes(gateway, [
        grant("locked", "main"),
        grant("missing", "main"),
        grant("user", "main"),
    ])
    statuses = {r["role"]: r["status"] for r in summary["results"]}
    assert statuses == {"locked": "error", "missing": "error", "user": "updated"}
    assert summary["failed"] == 2 and summary["updated"] == 1
    assert "permission" in summary["results"][0]["message"]
    assert gateway.writes == [("user", {"srchIndexesAllowed": ["main"]})]


def test_submit_with_invalid_payload_writes_nothing():
    gateway = FakeGateway({"user": {}})
    with pytest.raises(core.EasyAdminError):
        core.submit_changes(gateway, [grant("user", "main"), {"role": "user"}])
    assert gateway.writes == []


# ------------------------------------------------------------------ routing

def test_extract_changes_from_json_and_form_bodies():
    changes = [grant("user", "main")]
    assert core.extract_changes(json.dumps({"changes": changes})) == changes
    assert core.extract_changes(json.dumps({"changes": changes}).encode("utf-8")) == changes
    from urllib.parse import urlencode
    assert core.extract_changes(urlencode({"output_mode": "json",
                                           "changes": json.dumps(changes)})) == changes


@pytest.mark.parametrize("body, fragment", [
    ("", "empty"),
    (None, "empty"),
    ("{not json", "not valid JSON"),
    ("output_mode=json", "no 'changes' field"),
    ("changes=nope", "not valid JSON"),
])
def test_extract_changes_rejects_bad_bodies(body, fragment):
    with pytest.raises(core.EasyAdminError) as caught:
        core.extract_changes(body)
    assert fragment in str(caught.value)


def test_handle_request_get_returns_the_model():
    status, payload = core.handle_request("get", None, FakeGateway({"user": {}}, ["main"]))
    assert status == 200
    assert [r["name"] for r in payload["roles"]] == ["user"]


def test_handle_request_post_applies_changes():
    gateway = FakeGateway({"user": {}})
    body = json.dumps({"changes": [grant("user", "main")]})
    status, payload = core.handle_request("POST", body, gateway, user="alice")
    assert status == 200
    assert payload["updated"] == 1
    assert gateway.roles["user"]["srchIndexesAllowed"] == ["main"]


def test_handle_request_maps_errors_to_status_and_splunk_style_messages():
    gateway = FakeGateway({"user": {}})
    status, payload = core.handle_request("POST", json.dumps({"changes": []}), gateway)
    assert status == 400
    assert payload == {"messages": [{"type": "ERROR", "text": "No changes were submitted."}]}

    status, payload = core.handle_request("DELETE", None, gateway)
    assert status == 405

    class Forbidden(FakeGateway):
        def list_roles(self):
            raise core.GatewayError("insufficient permission", status=403)

    status, payload = core.handle_request("GET", None, Forbidden())
    assert status == 403
    assert payload["messages"][0]["text"] == "insufficient permission"
