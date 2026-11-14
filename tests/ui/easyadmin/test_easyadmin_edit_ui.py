"""UI tests for editing on easyadmin's role management page, in a real browser.

``test_easyadmin_ui.py`` is read-only. These click, type and save, so every
change lands on roles created through ``sandbox`` (named ``splktest_*``),
which are deleted after each test. The environment guard snapshots every
role, user and app permission around each test and fails any test that
leaves something changed; tests that could touch a real role (the own-role
warning) also record it with ``sandbox.remember`` so it is put back.

Each test checks the page (what a person sees) and, after a save, splunkd
itself through the admin REST client (what was really written).
"""

import os
import re

import pytest

from splk import ui as splk_ui
from splk.rest import SplunkError

APP = "easyadmin"
VIEW = "role_management"
ROOT = "#easyadmin-roles"
READY = ROOT + " table.ea-table"


# ------------------------------------------------------------------ helpers

def _box(page, role, item, field="srchIndexesAllowed"):
    """The checkbox for one role, attribute and item (the app's own data attributes)."""
    return page.locator('%s input[data-role="%s"][data-field="%s"][data-item="%s"]'
                        % (ROOT, role, field, item))


def _setting(page, role, field):
    return page.locator('%s .ea-setting-input[data-role="%s"][data-field="%s"]'
                        % (ROOT, role, field))


def _cell(locator):
    """The table cell around an input, which carries ea-changed / ea-effective."""
    return locator.locator("xpath=ancestor::td[1]")


def _classes(locator):
    return (locator.get_attribute("class") or "").split()


def _open_tab(page, label):
    page.locator(ROOT + " .ea-tab", has_text=label).first.click()
    page.wait_for_selector(READY)


def _save(page, accept=True):
    """Click Save; answer the confirmation. Returns the confirmation's text."""
    seen = {}

    def answer(dialog):
        seen["message"] = dialog.message
        if accept:
            dialog.accept()
        else:
            dialog.dismiss()
    page.once("dialog", answer)
    page.locator(ROOT + " .ea-save").click()
    if accept:
        page.wait_for_selector(ROOT + " .ea-message.ea-success, " + ROOT + " .ea-message.ea-error")
        # The page reloads the model after a save; wait until the grid is back.
        page.wait_for_selector(READY)
    return seen.get("message")


def _role(splunk_client, role):
    return splunk_client.request("GET", "/services/authorization/roles/%s" % role)["entry"][0]["content"]


def _as_set(value):
    if value in (None, ""):
        return set()
    return set(value) if isinstance(value, list) else {value}


@pytest.fixture
def role(sandbox):
    """A throwaway role with only the main index, created before the page opens."""
    return sandbox.create_role(label="easyadmin_ui", srchIndexesAllowed="main")


@pytest.fixture
def roles_page(open_view, role):
    return open_view(APP, VIEW, ready=READY)


# ------------------------------------------------------- pending changes

def test_ticking_marks_the_cell_and_counts_the_change(roles_page, role, shot):
    """An unsaved change is outlined, counted on its tab and on the Save button."""
    page = roles_page
    box = _box(page, role, "_internal")
    assert not box.is_checked()
    assert page.locator(ROOT + " .ea-save").is_disabled()

    box.check()
    shot(page, "edit-pending-change")
    assert "ea-changed" in _classes(_cell(box))
    assert page.locator(ROOT + " .ea-tab-active .ea-tab-count").inner_text() == "1"
    assert page.locator(ROOT + " .ea-save").inner_text().strip() == "Save 1 change(s)"

    # Flipping it back means there is nothing to save.
    box.uncheck()
    assert "ea-changed" not in _classes(_cell(box))
    assert page.locator(ROOT + " .ea-save").is_disabled()


def test_discard_drops_every_pending_change(roles_page, role):
    page = roles_page
    _box(page, role, "_internal").check()
    _open_tab(page, "Capabilities")
    _box(page, role, "schedule_search", field="capabilities").check()
    assert page.locator(ROOT + " .ea-save").inner_text().strip() == "Save 2 change(s)"

    page.locator(ROOT + " .ea-discard").click()
    assert not _box(page, role, "schedule_search", field="capabilities").is_checked()
    assert page.locator(ROOT + " .ea-save").is_disabled()
    assert page.locator(ROOT + " .ea-tab-count").count() == 0


def test_reload_keeps_pending_changes(roles_page, role):
    page = roles_page
    _box(page, role, "_internal").check()
    page.locator(ROOT + " .ea-actions button", has_text="Reload").click()
    page.wait_for_selector(READY)
    box = _box(page, role, "_internal")
    assert box.is_checked() and "ea-changed" in _classes(_cell(box))


def test_leaving_with_unsaved_changes_asks_first(roles_page, role):
    """The browser asks before a page with unsaved changes is left."""
    page = roles_page
    _box(page, role, "_internal").check()
    seen = []

    def answer(dialog):
        seen.append(dialog.type)
        dialog.accept()
    page.on("dialog", answer)
    page.close(run_before_unload=True)
    page.wait_for_event("close")
    assert seen == ["beforeunload"]


# ---------------------------------------------------------------- saving

def test_save_writes_the_change_to_splunkd(roles_page, role, sandbox_client, shot):
    """Save confirms, applies, reports success, and the cell becomes a plain tick."""
    page = roles_page
    _box(page, role, "_internal").check()
    message = _save(page)
    shot(page, "edit-saved")

    assert message == "Apply 1 change(s) to 1 role(s)?"
    assert page.locator(ROOT + " .ea-message.ea-success").inner_text().strip() == "Updated 1 role(s)."
    box = _box(page, role, "_internal")
    assert box.is_checked() and "ea-changed" not in _classes(_cell(box))
    assert _as_set(_role(sandbox_client, role)["srchIndexesAllowed"]) == {"main", "_internal"}


def test_one_save_covers_every_tab(roles_page, role, sandbox_client):
    """Changes on several tabs go in one save, one confirmation."""
    page = roles_page
    _box(page, role, "_internal").check()
    _open_tab(page, "Capabilities")
    _box(page, role, "schedule_search", field="capabilities").check()
    _open_tab(page, "Inheritance")
    _box(page, role, "user", field="imported_roles").check()
    _open_tab(page, "Search limits")
    quota = _setting(page, role, "srchJobsQuota")
    quota.fill("7")
    quota.press("Tab")

    assert _save(page) == "Apply 4 change(s) to 1 role(s)?"
    content = _role(sandbox_client, role)
    assert "_internal" in _as_set(content["srchIndexesAllowed"])
    assert "schedule_search" in _as_set(content["capabilities"])
    assert _as_set(content["imported_roles"]) == {"user"}
    assert str(content["srchJobsQuota"]) == "7"


def test_show_selector_switches_the_attribute(roles_page, role, sandbox_client):
    """The Indexes tab's Show selector edits the chosen attribute."""
    page = roles_page
    page.locator(ROOT + " select.ea-field").select_option("srchIndexesDefault")
    page.wait_for_selector(READY)
    box = _box(page, role, "_internal", field="srchIndexesDefault")
    box.check()
    _save(page)
    content = _role(sandbox_client, role)
    assert _as_set(content.get("srchIndexesDefault")) == {"_internal"}
    assert _as_set(content["srchIndexesAllowed"]) == {"main"}


def test_flag_and_list_settings_save(roles_page, role, sandbox_client):
    """A flag is a checkbox (on is 1); a list is typed comma-separated."""
    page = roles_page
    _open_tab(page, "Search limits")
    flag = _setting(page, role, "srchAllowAdvancedCron")
    was_on = flag.is_checked()
    flag.set_checked(not was_on)
    _open_tab(page, "Federated and KV store")
    exemptions = _setting(page, role, "fieldFilterExemption")
    exemptions.fill("splktest_a, splktest_b, splktest_a")
    exemptions.press("Tab")
    _save(page)

    content = _role(sandbox_client, role)
    assert str(content["srchAllowAdvancedCron"]) in (("0", "False") if was_on else ("1", "True"))
    assert _as_set(content["fieldFilterExemption"]) == {"splktest_a", "splktest_b"}


def test_add_a_column_by_name(roles_page, role, sandbox_client):
    """A typed name becomes an 'added here' column that can be ticked and saved."""
    page = roles_page
    page.locator(ROOT + " input.ea-add").fill("splktest_added_index")
    page.locator(ROOT + " input.ea-add").press("Enter")
    header = page.locator(ROOT + " th.ea-column", has_text="splktest_added_index")
    assert header.locator(".ea-badge").inner_text() == "added here"

    _box(page, role, "splktest_added_index").check()
    _save(page)
    assert "splktest_added_index" in _as_set(_role(sandbox_client, role)["srchIndexesAllowed"])
    # After the reload it is an entry this instance has no index for.
    header = page.locator(ROOT + " th.ea-column", has_text="splktest_added_index")
    assert header.locator(".ea-badge").inner_text() == "not known here"


# ---------------------------------------------------------------- errors

def test_setting_changed_elsewhere_is_refused_and_kept(roles_page, role, sandbox, sandbox_client):
    """If someone changes a setting after the page loaded, the save says so."""
    page = roles_page
    _open_tab(page, "Search limits")
    sandbox.update("role", role, srchJobsQuota="5")      # "someone else", after load
    quota = _setting(page, role, "srchJobsQuota")
    quota.fill("9")
    quota.press("Tab")
    _save(page)

    error = page.locator(ROOT + " .ea-message.ea-error").inner_text()
    assert "could not be updated and still show as unsaved" in error
    assert "Changed elsewhere since the page loaded: srchJobsQuota" in error
    assert "ea-changed" in _classes(_cell(_setting(page, role, "srchJobsQuota")))
    assert str(_role(sandbox_client, role)["srchJobsQuota"]) == "5"


def test_refused_role_is_listed_and_stays_unsaved(roles_page, role, sandbox_client):
    """A value splunkd refuses is reported with splunkd's reason; the edit is kept."""
    page = roles_page
    _open_tab(page, "Capabilities")
    page.locator(ROOT + " input.ea-add").fill("splktest_no_such_capability")
    page.locator(ROOT + " input.ea-add").press("Enter")
    _box(page, role, "splktest_no_such_capability", field="capabilities").check()
    _save(page)

    error = page.locator(ROOT + " .ea-message.ea-error").inner_text()
    assert "Updated 0 role(s); 1 could not be updated" in error
    assert role in error
    box = _box(page, role, "splktest_no_such_capability", field="capabilities")
    assert box.is_checked() and "ea-changed" in _classes(_cell(box))
    assert "splktest_no_such_capability" not in _as_set(_role(sandbox_client, role)["capabilities"])


def test_saving_your_own_role_warns_first(roles_page, sandbox):
    """The confirmation names roles the signed-in user holds. Declined, nothing changes."""
    page = roles_page
    # Should the dialog ever be accepted, admin is still put back.
    sandbox.remember("role", "admin", ["srchIndexesAllowed", "srchIndexesDisallowed"])
    page.locator(ROOT + " select.ea-field").select_option("srchIndexesDisallowed")
    page.wait_for_selector(READY)
    _box(page, "admin", "_audit", field="srchIndexesDisallowed").check()

    message = _save(page, accept=False)
    assert "This changes role(s) you hold yourself (admin)" in message
    assert "can lock you out of this page" in message
    # Declining leaves the change pending, unsent.
    assert page.locator(ROOT + " .ea-save").inner_text().strip() == "Save 1 change(s)"
    page.locator(ROOT + " .ea-discard").click()


# --------------------------------------------------------------- reading

def test_inherited_capability_is_shaded_with_its_reason(open_view, sandbox):
    """A shaded cell is effective through an imported role; hovering says why."""
    child = sandbox.create_role(label="easyadmin_ui", srchIndexesAllowed="main",
                                imported_roles="user")
    page = open_view(APP, VIEW, ready=READY)
    _open_tab(page, "Capabilities")
    box = _box(page, child, "change_own_password", field="capabilities")
    cell = _cell(box)
    assert not box.is_checked()
    assert "ea-effective" in _classes(cell)
    assert cell.get_attribute("title") == "Inherited from an imported role"


def test_imported_value_is_shown_under_a_setting(open_view, sandbox):
    """Settings tabs show what imported roles provide beneath the role's own value."""
    child = sandbox.create_role(label="easyadmin_ui", srchIndexesAllowed="main",
                                imported_roles="user")
    page = open_view(APP, VIEW, ready=READY)
    _open_tab(page, "Search limits")
    cell = _cell(_setting(page, child, "srchJobsQuota"))
    assert re.match(r"^imported: \d+$", cell.locator(".ea-imported").inner_text().strip())


def test_filter_narrows_columns_and_roles(roles_page, role):
    page = roles_page
    page.locator(ROOT + " input.ea-filter").fill("_inter")
    names = [n.strip() for n in page.locator(ROOT + " .ea-column-name").all_inner_texts()]
    assert names and all("_inter" in n for n in names)
    page.locator(ROOT + " input.ea-filter").fill("splktest_matches_nothing")
    assert page.locator(ROOT + " .ea-empty").inner_text() == "No columns match the filter."

    _open_tab(page, "Search limits")
    page.locator(ROOT + " input.ea-filter").fill(role)
    rows = [n.strip() for n in page.locator(ROOT + " th.ea-role").all_inner_texts()]
    assert rows == [role]


# ------------------------------------------------------------- read-only

def test_read_only_user_sees_a_read_only_page(target, sandbox, tmp_path, shot):
    """A user without edit_roles sees every value but no Save, and disabled cells."""
    viewer = sandbox.create_role(label="easyadmin_ro", imported_roles="user",
                                 srchIndexesAllowed="main")
    name, password = sandbox.create_user(roles=[viewer], label="easyadmin_ro")
    # The app is visible to admin and sc_admin only; open it to this role.
    current = sandbox.client.request("GET", "/services/apps/local/%s" % APP)["entry"][0]["acl"]
    readers = list((current.get("perms") or {}).get("read") or [])
    sandbox.set_app_permissions(APP, read=readers + [viewer])

    environ = dict(os.environ)
    environ[target.web_user_env] = name
    environ[target.web_password_env] = password
    try:
        with splk_ui.SplunkWeb(target, environ=environ, state_dir=str(tmp_path)) as web:
            page = web.new_page()
            web.open_view(page, APP, VIEW, ready_selector=READY)
            shot(page, "read-only")
            info = page.locator(ROOT + " .ea-message.ea-info").inner_text()
            assert "Read-only: your account does not hold the edit_roles" in info
            assert page.locator(ROOT + " .ea-save").count() == 0
            assert page.locator(ROOT + " .ea-cell input").first.is_disabled()
    except (splk_ui.UiError, SplunkError) as exc:
        pytest.fail("Read-only session failed: %s" % exc)
