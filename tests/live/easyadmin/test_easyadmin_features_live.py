"""Every easyadmin feature, exercised against the live target.

``test_easyadmin_live.py`` covers the endpoint's main paths. This module walks
the README feature by feature, so that every promise it makes has a live test:

* every role attribute on every tab can be written and read back, and put
  back to what it was (one parametrised test per attribute);
* attributes Splunk Web's role editor does not offer are refused;
* what a shaded (effective) cell means: wildcards, the underscore rule,
  inheritance through imported roles;
* the column kinds: wildcard, not known here;
* the save semantics: deltas keep other people's items, one request for the
  page's JSON body;
* validation: every malformed request is refused whole;
* permissions: the app never elevates, read-only users cannot save,
  ``edit_roles_grantable`` users are limited by splunkd;
* the audit trail in easyadmin.log.

Everything is written to roles and users created through ``sandbox``. The
environment guard snapshots every role, user and app permission around each
test and fails a test that leaves anything changed, so a green run also
proves the target was put back.
"""

import json

import pytest

from splk.rest import SplunkError

import easyadmin_live_support as ea

# ------------------------------------------------------------ attributes

# One item per checkbox attribute: something every stock 10.6 install has,
# that a new role (srchIndexesAllowed = main) does not already hold.
MATRIX_ITEMS = [
    ("srchIndexesAllowed", "_internal"),
    ("srchIndexesDefault", "_internal"),
    ("capabilities", "schedule_search"),
    ("imported_roles", "user"),
]

# One value per setting, of the kind the tab edits.
SETTING_VALUES = [
    ("srchJobsQuota", "7"),
    ("rtSrchJobsQuota", "4"),
    ("cumulativeSrchJobsQuota", "11"),
    ("cumulativeRTSrchJobsQuota", "5"),
    ("srchDiskQuota", "123"),
    ("srchTimeWin", "86400"),
    # A new role already has -1 (no limit) on 10.6.1, so write something else.
    ("srchTimeEarliest", "3600"),
    ("srchFilter", "index=main sourcetype=splktest"),
    ("defaultApp", "search"),
    ("srchFederatedProvidersAllowed", ["splktest_provider"]),
    ("srchFederatedProvidersDefault", ["splktest_provider"]),
]

# Writable through authorization/roles, but not offered by Splunk Web's role
# editor on 10.6.1, so the app must refuse them (the owner's rule: never do
# more than Settings > Roles can). Each is sent as a checkbox change and as
# both kinds of setting; every shape must be refused.
NOT_IN_EDITOR = [
    "srchIndexesDisallowed", "deleteIndexesAllowed", "grantable_roles", "queuedSearchQuota",
    "srchMinScheduleInterval", "srchAllowAdvancedCron", "federatedProviders",
    "fieldFilterExemption", "kvstore_create.deny_list", "kvstore_create.implicit_deny_list",
    "kvstore_update.deny_list", "kvstore_update.implicit_deny_list",
    "kvstore_delete.deny_list", "kvstore_delete.implicit_deny_list",
]


@pytest.fixture
def role(sandbox):
    """A throwaway role holding only the main index."""
    return sandbox.create_role(label="easyadmin", srchIndexesAllowed="main")


def test_every_attribute_the_app_edits_is_covered_here(splunk):
    """If the app gains a tab or attribute, this module must gain a test for it."""
    document = ea.model(splunk)
    matrix = {f["name"] for t in document["tabs"] if t["type"] == "matrix" for f in t["fields"]}
    settings = {f["name"] for t in document["tabs"] if t["type"] == "settings" for f in t["fields"]}
    assert matrix | settings == ({field for field, _item in MATRIX_ITEMS}
                                 | {field for field, _value in SETTING_VALUES})
    assert not (matrix | settings) & set(NOT_IN_EDITOR)


@pytest.mark.parametrize("field,item", MATRIX_ITEMS, ids=[f for f, _ in MATRIX_ITEMS])
def test_checkbox_attribute_grants_and_revokes(splunk, role, field, item):
    """Ticking writes the item to the role; unticking removes it again."""
    before = ea.as_set(ea.role_content(splunk, role).get(field))
    assert item not in before

    summary = ea.submit(splunk, [ea.grant(role, item, field=field)])
    assert summary["results"] == [{"role": role, "status": "updated", "message": ""}]
    after_grant = ea.role_content(splunk, role)
    assert ea.as_set(after_grant.get(field)) == before | {item}
    # The page shows it as a tick on that role.
    tab = ea.tab_of_field(ea.model(splunk), field)
    assert item in tab["cells"][role][field]["explicit"]

    summary = ea.submit(splunk, [ea.grant(role, item, on=False, field=field)])
    assert summary["updated"] == 1
    assert ea.as_set(ea.role_content(splunk, role).get(field)) == before


@pytest.mark.parametrize("field,value", SETTING_VALUES, ids=[f for f, _ in SETTING_VALUES])
def test_setting_is_written_read_back_and_put_back(splunk, role, field, value):
    """Each setting round-trips: the page shows what was written, and the old
    value can be written back (an empty one clears the attribute)."""
    document = ea.model(splunk)
    original = ea.loaded_value(document, role, field)

    summary = ea.submit(splunk, [ea.setting(role, field, value, original)])
    assert summary["results"][0]["status"] == "updated", summary
    shown = ea.loaded_value(ea.model(splunk), role, field)
    stored = ea.role_content(splunk, role).get(field)
    if isinstance(value, list):
        assert set(shown) == set(value)
        assert ea.as_set(stored) == set(value)
    else:
        assert shown == value
        assert ea.text(stored) == value

    summary = ea.submit(splunk, [ea.setting(role, field, original, value)])
    assert summary["results"][0]["status"] == "updated", summary
    assert ea.loaded_value(ea.model(splunk), role, field) == original


@pytest.mark.parametrize("field", NOT_IN_EDITOR)
def test_attribute_the_role_editor_lacks_is_refused(splunk, role, field):
    """The endpoint answers 400 and writes nothing, whichever shape the change takes."""
    before = ea.role_content(splunk, role)
    shapes = (ea.grant(role, "splktest_x", field=field),
              ea.setting(role, field, "1", ea.text(before.get(field))),
              ea.setting(role, field, ["splktest_x"], sorted(ea.as_set(before.get(field)))))
    for change in shapes:
        # A valid change after it proves the request is refused whole.
        with pytest.raises(SplunkError) as caught:
            ea.submit_json(splunk, {"changes": [change, ea.grant(role, "_internal")]})
        assert caught.value.status == 400
        assert "not a role attribute this app edits" in str(caught.value)
    after = ea.role_content(splunk, role)
    assert ea.as_set(after.get(field)) == ea.as_set(before.get(field))
    assert ea.as_set(after["srchIndexesAllowed"]) == {"main"}


# ------------------------------------------------------- shaded cells

def test_wildcard_shades_ordinary_indexes_but_not_internal_ones(splunk, sandbox):
    """``*`` covers main but, as in Splunk, not _internal; ``_*`` covers _internal."""
    star = sandbox.create_role(label="easyadmin", srchIndexesAllowed="*")
    under = sandbox.create_role(label="easyadmin", srchIndexesAllowed="_*")
    cells = ea.tab(ea.model(splunk), "indexes")["cells"]

    assert cells[star]["srchIndexesAllowed"]["effective"].get("main") == \
        "Matched by wildcard * on this role"
    assert "_internal" not in cells[star]["srchIndexesAllowed"]["effective"]
    assert cells[under]["srchIndexesAllowed"]["effective"].get("_internal") == \
        "Matched by wildcard _* on this role"
    assert "main" not in cells[under]["srchIndexesAllowed"]["effective"]


def test_inherited_wildcard_is_explained(splunk, sandbox):
    """A wildcard on an imported role shades the importing role's cells."""
    parent = sandbox.create_role(label="easyadmin", srchIndexesAllowed="*")
    child = sandbox.create_role(label="easyadmin", srchIndexesAllowed="main",
                                imported_roles=parent)
    cell = ea.tab(ea.model(splunk), "indexes")["cells"][child]["srchIndexesAllowed"]
    assert cell["explicit"] == ["main"]
    # summary is a stock, non-internal index the child does not list itself.
    # splunkd may expand the parent's * into imported_srchIndexesAllowed or
    # pass the pattern through; either way the cell must say why it is shaded.
    assert cell["effective"].get("summary") in (
        "Inherited from an imported role",
        "Matched by wildcard * inherited from an imported role")
    assert "_internal" not in cell["effective"]


def test_inherited_capability_is_shaded_not_ticked(splunk, sandbox):
    """A capability that comes from an imported role is effective, not explicit."""
    child = sandbox.create_role(label="easyadmin", srchIndexesAllowed="main",
                                imported_roles="user")
    cell = ea.tab(ea.model(splunk), "capabilities")["cells"][child]["capabilities"]
    assert "change_own_password" not in cell["explicit"]
    assert cell["effective"]["change_own_password"] == "Inherited from an imported role"


def test_inheritance_through_three_levels(splunk, sandbox):
    """Roles further up the chain are shaded with the role they come through."""
    grandparent = sandbox.create_role(label="easyadmin", srchIndexesAllowed="main")
    parent = sandbox.create_role(label="easyadmin", srchIndexesAllowed="main",
                                 imported_roles=grandparent)
    child = sandbox.create_role(label="easyadmin", srchIndexesAllowed="main",
                                imported_roles=parent)
    cell = ea.tab(ea.model(splunk), "inheritance")["cells"][child]["imported_roles"]
    assert cell == {"explicit": [parent],
                    "effective": {grandparent: "Inherited through %s" % parent}}
    roles = {r["name"]: r["imported_roles"] for r in ea.model(splunk)["roles"]}
    assert roles[child] == [parent]


# ------------------------------------------------------ column kinds

def test_unknown_and_wildcard_entries_become_columns(splunk, sandbox):
    """Entries that are not indexes on this instance are shown so they can be removed."""
    held = sandbox.create_role(label="easyadmin",
                               srchIndexesAllowed=["main", "splktest_missing_index", "splk*"])
    columns = {c["name"]: c for c in ea.tab(ea.model(splunk), "indexes")["columns"]}
    assert columns["splktest_missing_index"]["kind"] == "unknown"
    assert columns["splk*"]["kind"] == "wildcard"

    # And they can be unticked like any other column.
    summary = ea.submit(splunk, [ea.grant(held, "splktest_missing_index", on=False),
                                 ea.grant(held, "splk*", on=False)])
    assert summary["updated"] == 1
    assert ea.as_set(ea.role_content(splunk, held)["srchIndexesAllowed"]) == {"main"}


def test_a_name_added_by_hand_can_be_granted(splunk, role):
    """'Add a column by name' sends an item no role holds yet; it is written as is."""
    summary = ea.submit(splunk, [ea.grant(role, "splktest_web_*")])
    assert summary["updated"] == 1
    assert "splktest_web_*" in ea.as_set(ea.role_content(splunk, role)["srchIndexesAllowed"])


def test_role_columns_include_every_role(splunk, role):
    """The Inheritance tab's columns are the roles on the instance."""
    names = {c["name"] for c in ea.tab(ea.model(splunk), "inheritance")["columns"]}
    roles = {r["name"] for r in ea.model(splunk)["roles"]}
    assert role in names and roles <= names


# ---------------------------------------------------- save semantics

def test_checkbox_save_is_a_delta_and_keeps_concurrent_items(splunk, sandbox, role):
    """An item someone else added after the page loaded survives a save."""
    sandbox.update("role", role, srchIndexesAllowed=["main", "_audit"])  # "someone else"
    summary = ea.submit(splunk, [ea.grant(role, "_internal")])
    assert summary["updated"] == 1
    assert ea.as_set(ea.role_content(splunk, role)["srchIndexesAllowed"]) == \
        {"main", "_audit", "_internal"}


def test_page_json_body_is_accepted(splunk, role):
    """The page posts {"changes": [...]} as application/json."""
    summary = ea.submit_json(splunk, {"changes": [ea.grant(role, "_internal")]})
    assert summary["updated"] == 1
    assert "_internal" in ea.as_set(ea.role_content(splunk, role)["srchIndexesAllowed"])


def test_one_submit_changes_several_roles(splunk, sandbox):
    """One request, several roles: each gets one write and its own result."""
    first = sandbox.create_role(label="easyadmin", srchIndexesAllowed="main")
    second = sandbox.create_role(label="easyadmin", srchIndexesAllowed="main")
    summary = ea.submit(splunk, [ea.grant(first, "_internal"), ea.grant(second, "_audit"),
                                 ea.grant(first, "schedule_search", field="capabilities")])
    assert summary["updated"] == 2
    assert [r["role"] for r in summary["results"]] == [first, second]


def test_an_exact_repeat_in_one_submit_is_applied_once(splunk, role):
    summary = ea.submit(splunk, [ea.grant(role, "_internal"), ea.grant(role, "_internal")])
    assert summary["updated"] == 1


def test_stale_list_setting_is_refused(splunk, sandbox, role):
    """List settings are compared as sets before writing, like other settings."""
    field = "srchFederatedProvidersAllowed"
    loaded = ea.loaded_value(ea.model(splunk), role, field)
    sandbox.update("role", role, **{field: "splktest_other"})   # "someone else"
    summary = ea.submit(splunk, [ea.setting(role, field, ["splktest_provider"], loaded)])
    assert summary["failed"] == 1
    assert field in summary["results"][0]["message"]
    assert ea.as_set(ea.role_content(splunk, role).get(field)) == {"splktest_other"}


# --------------------------------------------------------- validation

BAD_REQUESTS = [
    ("not a list", {"changes": {"role": "x"}}, "'changes' must be a list."),
    ("empty", {"changes": []}, "No changes were submitted."),
    ("not an object", {"changes": ["x"]}, "Change 1 is not an object."),
    ("grant not bool", {"changes": [{"role": "{role}", "field": "capabilities",
                                     "item": "search", "grant": "yes"}]},
     "grant must be true or false"),
    ("both ways", {"changes": [{"role": "{role}", "field": "capabilities", "item": "search",
                                "grant": True},
                               {"role": "{role}", "field": "capabilities", "item": "search",
                                "grant": False}]},
     "both grants and revokes"),
    ("int kind", {"changes": [{"role": "{role}", "field": "srchJobsQuota", "value": "lots",
                               "previous": ""}]}, "must be a whole number"),
    ("list kind", {"changes": [{"role": "{role}", "field": "srchFederatedProvidersAllowed",
                                "value": "a", "previous": []}]}, "takes a list of values"),
    ("no previous", {"changes": [{"role": "{role}", "field": "srchJobsQuota", "value": "3"}]},
     "previous must be the value the page loaded"),
    ("twice", {"changes": [{"role": "{role}", "field": "srchFilter", "value": "a", "previous": ""},
                           {"role": "{role}", "field": "srchFilter", "value": "b", "previous": ""}]},
     "sets srchFilter on role"),
    ("padded role", {"changes": [{"role": " {role}", "field": "capabilities", "item": "search",
                                  "grant": True}]}, "without surrounding spaces"),
    ("too long", {"changes": [{"role": "{role}", "field": "capabilities", "item": "x" * 5000,
                               "grant": True}]}, "longer than 4096 characters"),
    ("unknown field", {"changes": [{"role": "{role}", "field": "imported_capabilities",
                                    "item": "x", "grant": True}]},
     "not a role attribute this app edits"),
]


def _fill(document, role):
    """Substitute the throwaway role's name into a template request."""
    return json.loads(json.dumps(document).replace("{role}", role))


@pytest.mark.parametrize("label,document,message", BAD_REQUESTS, ids=[b[0] for b in BAD_REQUESTS])
def test_malformed_request_is_refused_whole(splunk, role, label, document, message):
    """Any malformed change rejects the whole request with 400 and writes nothing."""
    before = ea.role_content(splunk, role)
    # A valid change after the bad one proves nothing at all is written. It
    # goes last so error positions ("Change 1") stay as written, and not into
    # the empty list, which must stay empty.
    body = _fill(document, role)
    if isinstance(body["changes"], list) and body["changes"]:
        body["changes"].append(ea.grant(role, "_internal"))
    with pytest.raises(SplunkError) as caught:
        ea.submit_json(splunk, body)
    assert caught.value.status == 400
    assert message in str(caught.value)
    assert ea.role_content(splunk, role).get("srchIndexesAllowed") == before.get("srchIndexesAllowed")


def test_too_many_changes_are_refused(splunk, role):
    changes = [ea.grant(role, "splktest_%d" % n) for n in range(5001)]
    with pytest.raises(SplunkError) as caught:
        ea.submit_json(splunk, {"changes": changes})
    assert caught.value.status == 400
    assert "Too many changes in one submit (5001, limit 5000)." in str(caught.value)


def test_empty_and_non_json_bodies_are_refused(splunk):
    with pytest.raises(SplunkError) as caught:
        splunk.request("POST", ea.ENDPOINT, {"other": "x"})
    assert caught.value.status == 400 and "no 'changes' field" in str(caught.value)
    with pytest.raises(SplunkError) as caught:
        splunk.request("POST", ea.ENDPOINT, {"changes": "{not json"})
    assert caught.value.status == 400 and "not valid JSON" in str(caught.value)


def test_other_methods_are_refused(splunk):
    with pytest.raises(SplunkError) as caught:
        splunk.request("DELETE", ea.ENDPOINT)
    assert caught.value.status in (405, 404)


# -------------------------------------------------------- permissions

@pytest.fixture
def read_only_user(sandbox, splunk):
    """A user whose only role cannot edit roles, signed in over REST."""
    role = sandbox.create_role(label="easyadmin_ro", imported_roles="user",
                               srchIndexesAllowed="main")
    name, password = sandbox.create_user(roles=[role], label="easyadmin_ro")
    return name, role, splunk.as_user(name, password)


def test_read_only_user_sees_the_model_but_cannot_edit(read_only_user):
    """Without edit_roles or edit_roles_grantable the page is read-only."""
    name, role, client = read_only_user
    document = ea.model(client)
    assert document["can_edit"] is False
    assert role in document["user_roles"]


def test_read_only_user_cannot_change_a_role(splunk, read_only_user, sandbox):
    """The app never elevates: splunkd refuses the write made with the user's session."""
    _name, _role, client = read_only_user
    victim = sandbox.create_role(label="easyadmin", srchIndexesAllowed="main")
    summary = ea.submit(client, [ea.grant(victim, "_internal")])
    assert summary["failed"] == 1 and summary["updated"] == 0
    assert summary["results"][0]["message"]
    assert ea.as_set(ea.role_content(splunk, victim)["srchIndexesAllowed"]) == {"main"}


def test_admin_user_roles_are_reported(splunk):
    """The page warns before a save touches a role the user holds: it needs user_roles."""
    assert "admin" in ea.model(splunk)["user_roles"]


def test_grantable_user_can_edit(splunk, sandbox):
    """edit_roles_grantable (sc_admin's capability on Splunk Cloud) makes the page editable."""
    target_role = sandbox.create_role(label="easyadmin", srchIndexesAllowed="main")
    # grantable_roles is set through sandbox: the app itself does not edit it.
    editor = sandbox.create_role(label="easyadmin_ga", imported_roles="user",
                                 srchIndexesAllowed="main",
                                 capabilities="edit_roles_grantable",
                                 grantable_roles=target_role)
    name, password = sandbox.create_user(roles=[editor], label="easyadmin_ga")
    client = splunk.as_user(name, password)
    assert ea.model(client)["can_edit"] is True


# ------------------------------------------------------------ audit

def test_role_edits_are_written_to_the_audit_log(splunk, search, role):
    """Each write is logged to easyadmin.log with the user, role and attributes."""
    ea.submit(splunk, [ea.grant(role, "_internal")])
    rows = ea.wait_for_audit_line(search, role)
    assert rows, "no easyadmin.log line for %s in _internal within 90s" % role
    line = rows[0]["_raw"]
    assert "role=%s updated" % role in line
    assert "srchIndexesAllowed" in line and "_internal" in line
    assert "user=" in line
