"""Live tests for easyadmin on a real Splunk instance.

The unit suite proves the model and update logic against a fake gateway; these
prove the packaged app registers its endpoint, that the handler's real calls to
splunkd read and write roles correctly, and that the page is installed.

The app has no SPL surface, so these go through the ``splunk`` REST client
rather than ``search``. Writes only ever touch throwaway roles created through
the ``sandbox`` fixture, which deletes them afterwards; the environment guard
checks that every other role and user is exactly as it was.
"""

import json
import urllib.parse

import pytest

from splk.rest import SplunkError

APP = "easyadmin"
ENDPOINT = "/services/easyadmin/roles"


def _grant(role, item, on=True, field="srchIndexesAllowed"):
    return {"role": role, "field": field, "item": item, "grant": on}


def _setting(role, field, value, previous):
    return {"role": role, "field": field, "value": value, "previous": previous}


def _submit(splunk, changes):
    # Form-encoded with the list as JSON in one field: what the splk client
    # sends, and one of the two body shapes the endpoint accepts.
    return splunk.request("POST", ENDPOINT, {"changes": json.dumps(changes)})


def _role_path(role):
    return "/services/authorization/roles/%s" % urllib.parse.quote(role)


def _role_content(splunk, role):
    return splunk.request("GET", _role_path(role))["entry"][0]["content"]


def _as_set(value):
    # splunkd returns a lone value as a bare string, and stores lists sorted
    # rather than as written, so compare as sets.
    if value in (None, ""):
        return set()
    return set(value) if isinstance(value, list) else {value}


def _text(splunk, role, field):
    # splunkd's JSON gives numeric settings as numbers; the page and the
    # endpoint deal in their text form.
    value = _role_content(splunk, role).get(field)
    return "" if value is None else str(value)


def _values(splunk, role, field="srchIndexesAllowed"):
    return _as_set(_role_content(splunk, role).get(field))


def _tab(model, tab_id):
    return next(t for t in model["tabs"] if t["id"] == tab_id)


@pytest.fixture
def make_role(sandbox):
    """Create throwaway roles through the sandbox, which deletes them afterwards."""
    def make(**attributes):
        params = {"srchIndexesAllowed": "main"}
        params.update(attributes)
        return sandbox.create_role(label="easyadmin", **params)
    return make


@pytest.fixture
def scratch_role(make_role):
    return make_role()


def test_app_installed_at_repo_version(splunk, expected_version):
    """The deploy stage put the version from app.conf on the instance."""
    info = splunk.app_info(APP)
    assert info is not None, "%s is not installed on the target" % APP
    assert info.get("version") == expected_version(APP)


def test_role_management_page_is_installed(splunk):
    """The Role management view exists, loads the app's script, and is the default."""
    data = splunk.request("GET", "/servicesNS/nobody/%s/data/ui/views/role_management" % APP)
    content = data["entry"][0]["content"]
    assert content["label"] == "Role management"
    assert 'script="easyadmin_roles.js"' in content["eai:data"]
    assert 'id="easyadmin-roles"' in content["eai:data"]

    nav = splunk.request("GET", "/servicesNS/nobody/%s/data/ui/nav/default" % APP)
    assert '<view name="role_management" default="true"' in nav["entry"][0]["content"]["eai:data"]


def test_app_declares_light_and_dark_themes(splunk):
    """Splunk Web applies a user's dark theme only to apps that declare it."""
    data = splunk.request("GET", "/servicesNS/nobody/%s/configs/conf-app/ui" % APP)
    themes = data["entry"][0]["content"]["supported_themes"]
    assert {t.strip() for t in themes.split(",")} == {"light", "dark"}


def test_model_reports_the_callers_theme_preference(splunk):
    """The page reloads into the user's theme, so the endpoint must report it."""
    context = splunk.request("GET", "/services/authentication/current-context")
    username = context["entry"][0]["content"]["username"]
    prefs = splunk.request("GET", "/servicesNS/%s/user-prefs/data/user-prefs/general"
                           % urllib.parse.quote(username))
    stored = str(prefs["entry"][0]["content"].get("theme") or "").strip().lower()
    expected = stored if stored in ("light", "dark") else None

    assert splunk.request("GET", ENDPOINT)["theme"] == expected


def test_model_has_every_tab(splunk):
    """GET returns the five tabs, and the caller (an admin) can edit."""
    model = splunk.request("GET", ENDPOINT)
    assert [(t["id"], t["type"]) for t in model["tabs"]] == [
        ("indexes", "matrix"), ("capabilities", "matrix"), ("inheritance", "matrix"),
        ("limits", "settings"), ("federated", "settings"),
    ]
    assert model["can_edit"] is True
    assert "admin" in model["user_roles"]


def test_index_tab_lists_indexes_and_wildcards(splunk):
    indexes = _tab(splunk.request("GET", ENDPOINT), "indexes")
    columns = {column["name"]: column for column in indexes["columns"]}
    assert columns["main"]["kind"] == "known" and columns["main"]["internal"] is False
    assert columns["_internal"]["kind"] == "known" and columns["_internal"]["internal"] is True
    # A stock install gives admin both wildcards explicitly.
    assert {"*", "_*"} <= set(indexes["cells"]["admin"]["srchIndexesAllowed"]["explicit"])
    assert columns["*"]["kind"] == "wildcard"


def test_capabilities_tab_has_every_capability_splunkd_defines(splunk):
    """Columns are splunkd's own capability list, and user's grants show as ticks."""
    defined = splunk.request("GET", "/services/authorization/capabilities")
    expected = set(defined["entry"][0]["content"]["capabilities"])

    tab = _tab(splunk.request("GET", ENDPOINT), "capabilities")
    known = {c["name"] for c in tab["columns"] if c["kind"] == "known"}
    assert known == expected
    assert set(tab["cells"]["user"]["capabilities"]["explicit"]) == _values(splunk, "user", "capabilities")
    # power imports user, so user's capabilities show as effective on power.
    assert tab["cells"]["power"]["capabilities"]["effective"].get("change_own_password") == \
        "Inherited from an imported role"


def test_inheritance_tab_shows_the_import_chain(splunk, make_role):
    """A role importing a role that imports user reaches user through it."""
    middle = make_role(imported_roles="user")
    top = make_role(imported_roles=middle)

    tab = _tab(splunk.request("GET", ENDPOINT), "inheritance")
    assert tab["cells"][top]["imported_roles"] == {
        "explicit": [middle], "effective": {"user": "Inherited through %s" % middle}}
    assert {c["name"] for c in tab["columns"]} >= {top, middle, "user", "admin"}


def test_bulk_update_across_tabs_in_one_submit(splunk, scratch_role):
    """One POST changes indexes, capabilities, inheritance and settings of a role."""
    # A role created over REST already holds some capabilities on 10.6.
    capabilities_before = _values(splunk, scratch_role, "capabilities")
    summary = _submit(splunk, [
        _grant(scratch_role, "_internal"),
        _grant(scratch_role, "easyadmin_*"),
        _grant(scratch_role, "main", on=False),
        _grant(scratch_role, "_internal", field="srchIndexesDefault"),
        _grant(scratch_role, "schedule_search", field="capabilities"),
        _grant(scratch_role, "user", field="imported_roles"),
        _setting(scratch_role, "srchJobsQuota", "7", _text(splunk, scratch_role, "srchJobsQuota")),
        _setting(scratch_role, "srchFilter", "index=main", ""),
    ])
    assert summary["results"] == [{"role": scratch_role, "status": "updated", "message": ""}]

    # Read back from splunkd directly, not through the app.
    content = _role_content(splunk, scratch_role)
    assert _as_set(content["srchIndexesAllowed"]) == {"_internal", "easyadmin_*"}
    assert _as_set(content["srchIndexesDefault"]) == {"_internal"}
    # splunkd reports a capability the role also imports under
    # imported_capabilities only (observed on 10.6.1: a new role's default
    # capabilities move there once it imports user). So check the total.
    own = _as_set(content["capabilities"])
    assert "schedule_search" in own
    assert capabilities_before <= own | _as_set(content.get("imported_capabilities"))
    assert _as_set(content["imported_roles"]) == {"user"}
    assert str(content["srchJobsQuota"]) == "7"
    assert content["srchFilter"] == "index=main"


def test_settings_tab_reads_back_what_was_written(splunk, scratch_role):
    """The settings model reflects a written value and its imported counterpart."""
    previous = _text(splunk, scratch_role, "srchJobsQuota")
    _submit(splunk, [_setting(scratch_role, "srchJobsQuota", "9", previous),
                     _grant(scratch_role, "user", field="imported_roles")])
    limits = _tab(splunk.request("GET", ENDPOINT), "limits")
    value = limits["values"][scratch_role]["srchJobsQuota"]
    assert value["value"] == "9"
    assert value["imported"] == _text(splunk, "user", "srchJobsQuota")


def test_text_setting_can_be_cleared(splunk, make_role):
    role = make_role(srchFilter="index=main")
    summary = _submit(splunk, [_setting(role, "srchFilter", "", "index=main")])
    assert summary["updated"] == 1
    assert _role_content(splunk, role).get("srchFilter", "") == ""


def test_stale_setting_is_refused_and_nothing_is_written(splunk, scratch_role):
    """A setting changed since the page loaded holds back that role's whole write."""
    actual = _text(splunk, scratch_role, "srchJobsQuota")
    stale = str(int(actual) + 1)
    summary = _submit(splunk, [
        _setting(scratch_role, "srchJobsQuota", "42", stale),
        _grant(scratch_role, "_internal"),
    ])
    assert summary["failed"] == 1
    assert "Changed elsewhere since the page loaded: srchJobsQuota" in summary["results"][0]["message"]
    content = _role_content(splunk, scratch_role)
    assert str(content["srchJobsQuota"]) == actual
    assert _as_set(content["srchIndexesAllowed"]) == {"main"}


def test_revoking_the_last_index_empties_the_list(splunk, scratch_role):
    """Unticking a role's only index clears the attribute rather than failing."""
    summary = _submit(splunk, [_grant(scratch_role, "main", on=False)])
    assert summary["updated"] == 1
    assert _values(splunk, scratch_role) == set()


def test_repeating_a_submit_reports_unchanged(splunk, scratch_role):
    """A change the role already satisfies is reported, not rewritten."""
    summary = _submit(splunk, [_grant(scratch_role, "main")])
    assert summary["results"][0]["status"] == "unchanged"
    assert summary["updated"] == 0 and summary["unchanged"] == 1


def test_unknown_role_is_reported_without_failing_the_rest(splunk, scratch_role):
    """One role splunkd refuses does not stop the other roles in the submit."""
    summary = _submit(splunk, [
        _grant("easyadmin_no_such_role", "main"),
        _grant(scratch_role, "_internal"),
    ])
    statuses = {result["role"]: result["status"] for result in summary["results"]}
    assert statuses == {"easyadmin_no_such_role": "error", scratch_role: "updated"}
    assert _values(splunk, scratch_role) == {"main", "_internal"}


def test_splunkd_refusal_is_reported_per_role(splunk, scratch_role):
    """A value splunkd itself rejects comes back as that role's error, unwritten."""
    before = _values(splunk, scratch_role, "capabilities")
    summary = _submit(splunk, [_grant(scratch_role, "easyadmin_no_such_capability",
                                      field="capabilities")])
    assert summary["failed"] == 1
    assert summary["results"][0]["message"]
    assert _values(splunk, scratch_role, "capabilities") == before


def test_malformed_submit_is_rejected_with_400(splunk, scratch_role):
    """A payload naming an attribute this app does not edit changes nothing."""
    with pytest.raises(SplunkError) as caught:
        _submit(splunk, [_grant(scratch_role, "x", field="imported_capabilities")])
    assert caught.value.status == 400
    assert "not a role attribute this app edits" in str(caught.value)
    assert _values(splunk, scratch_role) == {"main"}
