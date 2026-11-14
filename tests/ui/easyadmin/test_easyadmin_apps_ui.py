"""UI tests for easyadmin's App management page, in a real browser.

Every test that changes something works on macros it creates itself in the
search app (named ``easyadmin_ui_*``) and deletes afterwards from wherever
the test left them. Each checks what a person sees and, after Apply, splunkd
itself through the admin REST client.
"""

import time
import urllib.parse

import pytest

from splk.rest import SplunkError

APP = "easyadmin"
VIEW = "app_management"
ROOT = "#easyadmin-apps"
READY = ROOT + " .ea-grid"


def q(name):
    return urllib.parse.quote(name, safe="")


@pytest.fixture
def macro(sandbox_client):
    """Create a local macro in search; delete it afterwards from search or launcher."""
    made = []

    def create():
        name = "easyadmin_ui_%d" % int(time.time() * 1000)
        sandbox_client.request("POST", "/servicesNS/nobody/search/admin/macros",
                               {"name": name, "definition": "index=_internal"})
        made.append(name)
        return name

    yield create
    for name in made:
        for app in ("search", "launcher"):
            try:
                sandbox_client.request("DELETE", "/servicesNS/nobody/%s/admin/macros/%s" % (app, q(name)))
            except SplunkError:
                pass


def _open(open_view, builtin=True):
    page = open_view(APP, VIEW, ready=READY)
    if builtin:
        # search and launcher are built-in apps, hidden until asked for.
        page.locator(ROOT + ' input[data-fid="builtin"]').check()
        page.wait_for_selector(ROOT + ' .ea-app[data-app="search"]')
    return page


def _object(page, app, name):
    return page.locator('%s .ea-app[data-app="%s"] .ea-object' % (ROOT, app), has_text=name)


def _apply(page):
    """Click Apply, accept the confirmation, wait for the reloaded model. Returns the prompt."""
    seen = {}

    def answer(dialog):
        seen["message"] = dialog.message
        dialog.accept()
    page.once("dialog", answer)
    page.locator(ROOT + " .ea-apply").click()
    page.wait_for_selector(ROOT + " .ea-message.ea-success, " + ROOT + " .ea-message.ea-error")
    # As on the role page: wait for the busy line to go, or the old model is still shown.
    page.locator(ROOT + " .ea-busy").wait_for(state="detached")
    page.wait_for_selector(READY)
    return seen.get("message")


def _acl(client, app, name):
    return client.request("GET", "/servicesNS/nobody/%s/admin/macros/%s" % (app, q(name)))["entry"][0]["acl"]


def test_apps_are_boxes_in_alphabetical_order_with_a_legend(open_view, shot, page_log):
    """Every app is its own box, in alphabetical order; the legend names every type's icon."""
    page = _open(open_view)
    shot(page, "app_management")
    apps = page.locator(ROOT + " .ea-app").evaluate_all("nodes => nodes.map(n => n.getAttribute('data-app'))")
    # Alphabetical by the title each box shows (the app's label).
    titles = [t.strip().lower() for t in page.locator(ROOT + " .ea-app-title").all_inner_texts()]
    assert titles == sorted(titles)
    assert {"easyadmin", "search", "launcher"} <= set(apps)
    legend = page.locator(ROOT + " .ea-legend-types li").all_inner_texts()
    assert "Search macro" in [t.strip() for t in legend] and len(legend) == 20
    # Each type has its own icon, and every object row shows one named for assistive tech.
    shapes = page.locator(ROOT + " .ea-legend-types svg").evaluate_all(
        "nodes => nodes.map(n => n.innerHTML)")
    assert len(set(shapes)) == len(shapes)
    labels = page.locator(ROOT + ' .ea-object svg[role="img"]').evaluate_all(
        "nodes => nodes.map(n => n.getAttribute('aria-label'))")
    assert labels and all(labels)
    assert page_log(page).page_errors == []


def test_builtin_apps_are_hidden_until_asked_for(open_view):
    """Splunk's own apps (search, launcher...) only appear with "Show Splunk's built-in apps"."""
    page = _open(open_view, builtin=False)
    assert page.locator(ROOT + ' .ea-app[data-app="search"]').count() == 0
    assert page.locator(ROOT + ' .ea-app[data-app="easyadmin"]').count() == 1
    assert "built-in apps are hidden" in page.locator(ROOT + " .ea-summary").inner_text()
    page.locator(ROOT + ' input[data-fid="builtin"]').check()
    assert page.locator(ROOT + ' .ea-app[data-app="search"]').count() == 1


def test_filter_narrows_objects_and_says_when_nothing_matches(open_view, macro):
    """The filter keeps only objects whose name contains the text, and names a filter with no matches."""
    name = macro()
    page = _open(open_view)
    page.locator(ROOT + " .ea-filter").fill(name)
    assert page.locator(ROOT + " .ea-object").count() == 1
    assert _object(page, "search", name).count() == 1
    page.locator(ROOT + " .ea-filter").fill("no_such_object_anywhere")
    assert 'No objects match the filter "no_such_object_anywhere"' in page.locator(ROOT).inner_text()
    # Apps stay on show while filtering, so an object can be found and then
    # dragged to any of them.
    assert page.locator(ROOT + ' .ea-app[data-app="launcher"]').count() == 1


def test_drag_to_another_app_stages_a_move_and_apply_makes_it(open_view, macro, sandbox_client, shot):
    """Dragging an object onto another app's box stages a move, marked on the object; Apply moves it."""
    name = macro()
    page = _open(open_view)
    page.locator(ROOT + " .ea-filter").fill(name)
    # Dropped back on its own app: nothing is staged, and the page says so.
    _object(page, "search", name).drag_to(page.locator(ROOT + ' .ea-app[data-app="search"] .ea-app-head'))
    assert "Nothing to move" in page.locator(ROOT + " .ea-messages").inner_text()
    assert page.locator(ROOT + " .ea-apply").is_disabled()
    _object(page, "search", name).drag_to(page.locator(ROOT + ' .ea-app[data-app="launcher"]'))
    assert "Staged a move of 1 object to Home (launcher)" in page.locator(ROOT + " .ea-messages").inner_text()
    moved = _object(page, "launcher", name)
    assert moved.count() == 1
    assert "moving from search" in moved.inner_text()
    assert "ea-changed" in moved.get_attribute("class")
    assert page.locator(ROOT + " .ea-apply").inner_text() == "Apply 1 change"
    shot(page, "app_management_staged_move")
    # Nothing is written until Apply.
    assert _acl(sandbox_client, "search", name)["app"] == "search"

    prompt = _apply(page)
    assert "move 1 object" in prompt
    assert _acl(sandbox_client, "launcher", name)["app"] == "launcher"
    assert "Applied changes to 1 object." in page.locator(ROOT + " .ea-message.ea-success").inner_text()
    assert "moving from" not in _object(page, "launcher", name).inner_text()


def test_select_and_bulk_move_with_the_keyboard_controls(open_view, macro, sandbox_client):
    """Ticking objects and choosing an app in "Move to app" stages a move without dragging."""
    first, second = macro(), macro()
    page = _open(open_view)
    page.locator(ROOT + " .ea-filter").fill("easyadmin_ui_")
    for name in (first, second):
        _object(page, "search", name).locator(".ea-select").check()
    assert "2 objects selected" in page.locator(ROOT + " .ea-selection").inner_text()
    page.locator(ROOT + " .ea-move-target").select_option("launcher")
    page.locator(ROOT + ' button[data-fid="move-selected"]').click()
    assert _object(page, "launcher", first).count() == 1 and _object(page, "launcher", second).count() == 1
    _apply(page)
    assert _acl(sandbox_client, "launcher", first)["app"] == "launcher"
    assert _acl(sandbox_client, "launcher", second)["app"] == "launcher"


def test_panel_shows_settings_and_stages_permission_changes(open_view, macro, sandbox_client, shot):
    """Clicking an object opens a panel with every setting; changing sharing there is staged and applied."""
    name = macro()
    page = _open(open_view)
    page.locator(ROOT + " .ea-filter").fill(name)
    _object(page, "search", name).locator(".ea-object-name").click()
    panel = page.locator(ROOT + " .ea-panel")
    panel.locator(".ea-settings").wait_for()
    assert "index=_internal" in panel.locator(".ea-settings").inner_text()
    panel.locator("#ea-sharing").select_option("global")
    assert "permissions changed" in _object(page, "search", name).inner_text()
    assert "Staged:" in panel.inner_text()
    shot(page, "app_management_panel")
    page.keyboard.press("Escape")
    assert page.locator(ROOT + " .ea-panel").count() == 0

    prompt = _apply(page)
    assert "change the permissions of 1 object" in prompt
    assert _acl(sandbox_client, "search", name)["sharing"] == "global"


def test_delete_is_staged_and_discard_drops_it(open_view, macro, sandbox_client):
    """Delete marks the object "will be deleted"; Discard changes drops every staged change."""
    name = macro()
    page = _open(open_view)
    page.locator(ROOT + " .ea-filter").fill(name)
    _object(page, "search", name).locator(".ea-select").check()
    page.locator(ROOT + ' button[data-fid="delete-selected"]').click()
    assert "will be deleted" in _object(page, "search", name).inner_text()
    assert "Staged 1 object for deletion" in page.locator(ROOT + " .ea-messages").inner_text()
    seen = {}

    def answer(dialog):
        seen["message"] = dialog.message
        dialog.accept()
    page.once("dialog", answer)
    page.locator(ROOT + " .ea-discard").click()
    assert seen["message"] == "Discard 1 staged change? Nothing has been applied yet."
    assert "will be deleted" not in _object(page, "search", name).inner_text()
    assert page.locator(ROOT + " .ea-apply").is_disabled()
    assert _acl(sandbox_client, "search", name)["app"] == "search"


def test_object_in_default_cannot_be_moved_or_deleted(open_view):
    """An object shipped in default/ is marked locked; its panel says why it cannot be moved or deleted."""
    page = _open(open_view, builtin=False)
    row = _object(page, "easyadmin", "role_management")
    assert row.locator(".ea-locked").count() == 1
    assert row.get_attribute("draggable") is None
    row.locator(".ea-object-name").click()
    panel = page.locator(ROOT + " .ea-panel")
    assert panel.locator("#ea-app").is_disabled()
    assert "cannot be moved or deleted" in panel.inner_text()
    assert panel.locator('button[data-fid="panel-delete"]').is_disabled()


def test_leaving_with_staged_changes_asks_first(open_view, macro):
    """The browser asks before a page with staged changes is left."""
    name = macro()
    page = _open(open_view)
    page.locator(ROOT + " .ea-filter").fill(name)
    _object(page, "search", name).locator(".ea-select").check()
    page.locator(ROOT + ' button[data-fid="delete-selected"]').click()
    seen = []

    def answer(dialog):
        seen.append(dialog.type)
        dialog.accept()
    page.on("dialog", answer)
    page.close(run_before_unload=True)
    page.wait_for_event("close")
    assert seen == ["beforeunload"]


def test_bulk_owner_change_is_staged_and_applied(open_view, macro, sandbox_client):
    """Edit permissions on ticked objects: typing only a new owner is enough to stage it for all of them."""
    first, second = macro(), macro()
    page = _open(open_view)
    page.locator(ROOT + " .ea-filter").fill("easyadmin_ui_")
    for name in (first, second):
        _object(page, "search", name).locator(".ea-select").check()
    page.locator(ROOT + ' button[data-fid="bulk-acl"]').click()
    stage = page.locator(ROOT + ' button[data-fid="bulk-stage"]')
    assert stage.is_disabled()   # nothing chosen yet
    page.locator(ROOT + ' input[data-fid="bulk-owner"]').fill("nobody")
    assert stage.is_enabled()
    stage.click()
    assert "Staged permission changes for 2 objects" in page.locator(ROOT + " .ea-messages").inner_text()
    assert "permissions changed" in _object(page, "search", first).inner_text()
    prompt = _apply(page)
    assert "change the permissions of 2 objects" in prompt
    assert _acl(sandbox_client, "search", first)["owner"] == "nobody"
    assert _acl(sandbox_client, "search", second)["owner"] == "nobody"
