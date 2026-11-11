"""Unit tests for easyadmin_core: the role x index matrix and bulk updates.

The module imports nothing from Splunk; splunkd is replaced by FakeGateway,
which holds roles in memory and records every write.
"""

import json

import pytest

import easyadmin_core as core


class FakeGateway(object):
    """An in-memory stand-in for easyadmin_rest.SplunkdGateway."""

    def __init__(self, roles=None, indexes=None, capabilities=("edit_roles",), refuse=()):
        self.roles = {name: dict(content) for name, content in (roles or {}).items()}
        self.indexes = list(indexes or [])
        self._capabilities = list(capabilities)
        self.refuse = set(refuse)  # role names splunkd will not let us write
        self.writes = []

    def list_roles(self):
        return [{"name": name, "content": content} for name, content in self.roles.items()]

    def list_indexes(self):
        return [{"name": name, "content": {"datatype": "event", "disabled": False}}
                for name in self.indexes]

    def capabilities(self):
        return self._capabilities

    def get_role(self, name):
        if name not in self.roles:
            raise core.GatewayError("Role %s was not found." % name, status=404)
        return self.roles[name]

    def update_role(self, name, fields):
        if name in self.refuse:
            raise core.GatewayError("You do not have permission to edit %s." % name, status=403)
        self.writes.append((name, {field: list(values) for field, values in fields.items()}))
        self.roles[name].update(fields)


def change(role, index, grant, field="srchIndexesAllowed"):
    return {"role": role, "field": field, "index": index, "grant": grant}


# ------------------------------------------------------------------ helpers

@pytest.mark.parametrize("value, expected", [
    (None, []),
    ("", []),
    ("main", ["main"]),
    (["main", "", None, "web"], ["main", "web"]),
])
def test_as_list_normalises_rest_values(value, expected):
    assert core.as_list(value) == expected


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


# ------------------------------------------------------------------- matrix

def _matrix(roles, indexes, capabilities=("edit_roles",)):
    return core.read_matrix(FakeGateway(roles, indexes, capabilities))


def test_matrix_lists_fields_roles_and_indexes():
    matrix = _matrix({"user": {"srchIndexesAllowed": ["main"], "srchIndexesDefault": ["main"]}},
                     ["main", "web"])
    assert [f["name"] for f in matrix["fields"]] == ["srchIndexesAllowed", "srchIndexesDefault"]
    assert [r["name"] for r in matrix["roles"]] == ["user"]
    assert [i["name"] for i in matrix["indexes"]] == ["main", "web"]
    assert matrix["roles"][0]["srchIndexesAllowed"] == {"explicit": ["main"], "effective": {}}


def test_matrix_adds_rows_for_wildcards_and_unknown_indexes():
    """Entries a role holds that are not real indexes still get a row to untick."""
    matrix = _matrix({"power": {"srchIndexesAllowed": ["*", "retired_idx", "main"]}},
                     ["main", "_internal"])
    rows = [(i["name"], i["kind"]) for i in matrix["indexes"]]
    # Wildcards, then ordinary indexes, then internal, then unknown names.
    assert rows == [("*", "wildcard"), ("main", "index"), ("_internal", "index"),
                    ("retired_idx", "unknown")]
    assert matrix["indexes"][2]["internal"] is True


def test_matrix_explains_wildcard_and_inherited_access():
    matrix = _matrix({
        "analyst": {
            "srchIndexesAllowed": ["web*"],
            "imported_srchIndexesAllowed": ["main", "_*"],
            "imported_roles": ["user"],
        },
    }, ["main", "web_prod", "_internal", "secure"])
    role = matrix["roles"][0]
    assert role["imported_roles"] == ["user"]
    assert role["srchIndexesAllowed"]["explicit"] == ["web*"]
    assert role["srchIndexesAllowed"]["effective"] == {
        "main": "Inherited from an imported role",
        "_*": "Inherited from an imported role",
        "web_prod": "Matched by wildcard web* on this role",
        "_internal": "Matched by wildcard _* inherited from an imported role",
    }
    # Nothing reaches "secure", so it carries no explanation.
    assert "secure" not in role["srchIndexesAllowed"]["effective"]


@pytest.mark.parametrize("capabilities, expected", [
    (["search"], False),
    (["edit_roles"], True),
    (["search", "edit_roles_grantable"], True),  # what sc_admin holds on Splunk Cloud
])
def test_matrix_reports_whether_user_can_edit(capabilities, expected):
    assert _matrix({}, [], capabilities)["can_edit"] is expected


def test_matrix_sorts_roles_case_insensitively():
    matrix = _matrix({"zeta": {}, "Alpha": {}, "beta": {}}, [])
    assert [r["name"] for r in matrix["roles"]] == ["Alpha", "beta", "zeta"]


# ------------------------------------------------------------------ changes

def test_parse_changes_groups_by_role_and_field():
    plan = core.parse_changes([
        change("user", "main", True),
        change("user", "web", False),
        change("user", "main", True, field="srchIndexesDefault"),
        change("power", "web", True),
        change("user", "main", True),  # exact repeat is applied once
    ])
    assert list(plan) == ["user", "power"]
    assert plan["user"]["srchIndexesAllowed"] == {"grant": ["main"], "revoke": ["web"]}
    assert plan["user"]["srchIndexesDefault"] == {"grant": ["main"], "revoke": []}


@pytest.mark.parametrize("raw, fragment", [
    ("not a list", "must be a list"),
    ([], "No changes"),
    (["x"], "not an object"),
    ([change("", "main", True)], "role must be"),
    ([change("user", " main", True)], "index must be"),
    ([change("user", "main", True, field="capabilities")], "field must be one of"),
    ([change("user", "main", "yes")], "grant must be"),
    ([change("user", "main", True), change("user", "main", False)], "both grants and revokes"),
    ([change("user", "x" * 600, True)], "longer than"),
])
def test_parse_changes_rejects_malformed_input(raw, fragment):
    with pytest.raises(core.EasyAdminError) as caught:
        core.parse_changes(raw)
    assert fragment in str(caught.value)
    assert caught.value.status == 400


def test_parse_changes_enforces_the_size_cap():
    raw = [change("user", "idx%d" % n, True) for n in range(core.MAX_CHANGES + 1)]
    with pytest.raises(core.EasyAdminError) as caught:
        core.parse_changes(raw)
    assert "Too many changes" in str(caught.value)


def test_apply_delta_preserves_order_and_drops_duplicates():
    assert core.apply_delta(["a", "b", "c"], ["d", "a"], ["b"]) == ["a", "c", "d"]
    assert core.apply_delta(["a"], [], ["a"]) == []
    assert core.apply_delta([], ["a", "a"], []) == ["a"]


# ------------------------------------------------------------------- submit

def test_submit_writes_each_role_once_with_only_changed_fields():
    gateway = FakeGateway({
        "user": {"srchIndexesAllowed": ["main"], "srchIndexesDefault": ["main"]},
        "power": {"srchIndexesAllowed": ["main", "web"]},
    })
    summary = core.submit_changes(gateway, [
        change("user", "web", True),
        change("user", "main", False),
        change("power", "web", False),
    ], user="alice")

    assert gateway.writes == [
        ("user", {"srchIndexesAllowed": ["web"]}),
        ("power", {"srchIndexesAllowed": ["main"]}),
    ]
    assert summary["updated"] == 2 and summary["failed"] == 0 and summary["unchanged"] == 0
    assert [r["status"] for r in summary["results"]] == ["updated", "updated"]


def test_submit_applies_deltas_to_current_state_not_the_page_snapshot():
    """An index added to the role elsewhere since page load is not clobbered."""
    gateway = FakeGateway({"user": {"srchIndexesAllowed": ["main", "added_elsewhere"]}})
    core.submit_changes(gateway, [change("user", "web", True)])
    assert gateway.writes == [("user", {"srchIndexesAllowed": ["main", "added_elsewhere", "web"]})]


def test_submit_skips_a_role_already_in_the_requested_state():
    gateway = FakeGateway({"user": {"srchIndexesAllowed": ["main"]}})
    summary = core.submit_changes(gateway, [change("user", "main", True), change("user", "web", False)])
    assert gateway.writes == []
    assert summary["results"][0]["status"] == "unchanged"
    assert summary["unchanged"] == 1


def test_submit_can_empty_a_list():
    gateway = FakeGateway({"user": {"srchIndexesAllowed": ["main"]}})
    core.submit_changes(gateway, [change("user", "main", False)])
    assert gateway.writes == [("user", {"srchIndexesAllowed": []})]


def test_submit_reports_failures_per_role_and_carries_on():
    gateway = FakeGateway({"locked": {}, "user": {}}, refuse=["locked"])
    summary = core.submit_changes(gateway, [
        change("locked", "main", True),
        change("missing", "main", True),
        change("user", "main", True),
    ])
    statuses = {r["role"]: r["status"] for r in summary["results"]}
    assert statuses == {"locked": "error", "missing": "error", "user": "updated"}
    assert summary["failed"] == 2 and summary["updated"] == 1
    assert "permission" in summary["results"][0]["message"]
    assert gateway.writes == [("user", {"srchIndexesAllowed": ["main"]})]


def test_submit_with_invalid_payload_writes_nothing():
    gateway = FakeGateway({"user": {}})
    with pytest.raises(core.EasyAdminError):
        core.submit_changes(gateway, [change("user", "main", True), {"role": "user"}])
    assert gateway.writes == []


# ------------------------------------------------------------------ routing

def test_extract_changes_from_json_and_form_bodies():
    changes = [change("user", "main", True)]
    assert core.extract_changes(json.dumps({"changes": changes})) == changes
    assert core.extract_changes(json.dumps({"changes": changes}).encode("utf-8")) == changes
    form = "output_mode=json&changes=%5B%7B%22role%22%3A%22user%22%2C%22field%22%3A%22srchIndexesAllowed%22%2C%22index%22%3A%22main%22%2C%22grant%22%3Atrue%7D%5D"
    assert core.extract_changes(form) == changes


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


def test_handle_request_get_returns_the_matrix():
    status, payload = core.handle_request("get", None, FakeGateway({"user": {}}, ["main"]))
    assert status == 200
    assert [r["name"] for r in payload["roles"]] == ["user"]


def test_handle_request_post_applies_changes():
    gateway = FakeGateway({"user": {}})
    body = json.dumps({"changes": [change("user", "main", True)]})
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
