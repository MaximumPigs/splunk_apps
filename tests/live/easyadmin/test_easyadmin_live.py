"""Live tests for easyadmin on a real Splunk instance.

The unit suite proves the matrix and delta logic against a fake gateway; these
prove the packaged app registers its endpoint, that the handler's real calls to
splunkd read and write roles correctly, and that the page is installed.

The app has no SPL surface, so these go through the ``splunk`` REST client
rather than ``search``. Writes only ever touch a throwaway role created for the
test and deleted afterwards.
"""

import json
import urllib.parse
import uuid

import pytest

from splk.rest import SplunkError

APP = "easyadmin"
ENDPOINT = "/services/easyadmin/index_permissions"


def _change(role, index, grant, field="srchIndexesAllowed"):
    return {"role": role, "field": field, "index": index, "grant": grant}


def _submit(splunk, changes):
    # Form-encoded with the list as JSON in one field: what the splk client
    # sends, and one of the two body shapes the endpoint accepts.
    return splunk.request("POST", ENDPOINT, {"changes": json.dumps(changes)})


def _role_content(splunk, role):
    data = splunk.request("GET", "/services/authorization/roles/%s" % urllib.parse.quote(role))
    return data["entry"][0]["content"]


def _indexes(splunk, role, field="srchIndexesAllowed"):
    # splunkd stores these lists sorted, not in the order written, so compare
    # as sets. Observed on 10.6: writing [main, _internal] reads back reversed.
    return set(_role_content(splunk, role).get(field) or [])


@pytest.fixture
def scratch_role(splunk):
    """A role that exists only for one test, starting with access to main."""
    name = "easyadmin_live_%s" % uuid.uuid4().hex[:8]
    splunk.request("POST", "/services/authorization/roles",
                   {"name": name, "srchIndexesAllowed": "main"})
    yield name
    splunk.request("DELETE", "/services/authorization/roles/%s" % urllib.parse.quote(name))


def test_app_installed_at_repo_version(splunk, expected_version):
    """The deploy stage put the version from app.conf on the instance."""
    info = splunk.app_info(APP)
    assert info is not None, "%s is not installed on the target" % APP
    assert info.get("version") == expected_version(APP)


def test_page_is_installed_and_loads_the_script(splunk):
    """The Index permissions view exists and points at the app's script."""
    data = splunk.request("GET", "/servicesNS/nobody/%s/data/ui/views/index_permissions" % APP)
    xml = data["entry"][0]["content"]["eai:data"]
    assert 'script="easyadmin_index_permissions.js"' in xml
    assert 'id="easyadmin-index-permissions"' in xml


def test_matrix_lists_roles_indexes_and_both_fields(splunk):
    """GET returns every role and index, typed, for both editable attributes."""
    matrix = splunk.request("GET", ENDPOINT)

    assert matrix["fields"] == [
        {"name": "srchIndexesAllowed", "label": "Searchable indexes"},
        {"name": "srchIndexesDefault", "label": "Indexes searched by default"},
    ]
    # The splk token belongs to an administrator on the dev target.
    assert matrix["can_edit"] is True

    indexes = {row["name"]: row for row in matrix["indexes"]}
    assert indexes["main"]["kind"] == "index" and indexes["main"]["internal"] is False
    assert indexes["_internal"]["kind"] == "index" and indexes["_internal"]["internal"] is True

    roles = {role["name"]: role for role in matrix["roles"]}
    assert "admin" in roles and "user" in roles
    # A stock install gives admin both wildcards explicitly.
    assert "*" in roles["admin"]["srchIndexesAllowed"]["explicit"]
    assert indexes["*"]["kind"] == "wildcard"


def test_bulk_update_grants_and_revokes_in_one_submit(splunk, scratch_role):
    """One POST applies several cell changes to a role, visible in splunkd itself."""
    summary = _submit(splunk, [
        _change(scratch_role, "_internal", True),
        _change(scratch_role, "easyadmin_*", True),
        _change(scratch_role, "main", False),
        _change(scratch_role, "_internal", True, field="srchIndexesDefault"),
    ])
    assert summary["updated"] == 1 and summary["failed"] == 0
    assert summary["results"] == [{"role": scratch_role, "status": "updated", "message": ""}]

    # Read back from splunkd directly, not through the app.
    assert _indexes(splunk, scratch_role) == {"_internal", "easyadmin_*"}
    assert _indexes(splunk, scratch_role, "srchIndexesDefault") == {"_internal"}

    # And the matrix now shows those entries as explicit ticks.
    roles = {role["name"]: role for role in splunk.request("GET", ENDPOINT)["roles"]}
    assert set(roles[scratch_role]["srchIndexesAllowed"]["explicit"]) == {"_internal", "easyadmin_*"}


def test_revoking_the_last_index_empties_the_list(splunk, scratch_role):
    """Unticking a role's only index clears the attribute rather than failing."""
    summary = _submit(splunk, [_change(scratch_role, "main", False)])
    assert summary["updated"] == 1
    assert _indexes(splunk, scratch_role) == set()


def test_repeating_a_submit_reports_unchanged(splunk, scratch_role):
    """A change the role already satisfies is reported, not rewritten."""
    summary = _submit(splunk, [_change(scratch_role, "main", True)])
    assert summary["results"][0]["status"] == "unchanged"
    assert summary["updated"] == 0 and summary["unchanged"] == 1


def test_unknown_role_is_reported_without_failing_the_rest(splunk, scratch_role):
    """One role splunkd refuses does not stop the other roles in the submit."""
    summary = _submit(splunk, [
        _change("easyadmin_no_such_role", "main", True),
        _change(scratch_role, "_internal", True),
    ])
    statuses = {result["role"]: result["status"] for result in summary["results"]}
    assert statuses == {"easyadmin_no_such_role": "error", scratch_role: "updated"}
    assert _indexes(splunk, scratch_role) == {"main", "_internal"}


def test_malformed_submit_is_rejected_with_400(splunk, scratch_role):
    """A payload naming an attribute outside the two this page edits changes nothing."""
    with pytest.raises(SplunkError) as caught:
        _submit(splunk, [_change(scratch_role, "main", False, field="capabilities")])
    assert caught.value.status == 400
    assert "field must be one of" in str(caught.value)
    assert _indexes(splunk, scratch_role) == {"main"}
