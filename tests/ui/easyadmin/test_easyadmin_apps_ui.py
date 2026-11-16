"""UI tests for easyadmin's App management page, in a real browser.

Every test that changes something works on macros it creates itself in the
search app (named ``easyadmin_ui_*``) and deletes afterwards from wherever
the test left them. Each checks what a person sees and, after Apply, splunkd
itself through the admin REST client.
"""

import re
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

    def create(definition="index=_internal"):
        name = "easyadmin_ui_%d" % int(time.time() * 1000)
        sandbox_client.request("POST", "/servicesNS/nobody/search/admin/macros",
                               {"name": name, "definition": definition})
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


def _room_to_drag(page):
    """Make the window tall enough to hold every app box.

    Playwright's drag starts with a press and one move: when the target box is
    outside the window the browser never starts the drag (observed once the dev
    target had 30 apps: no dragstart, nothing staged), so a drag needs both ends
    on screen.
    """
    page.set_viewport_size({"width": 1440, "height": 2600})


def _object(page, app, name):
    """The row of the object called exactly ``name`` (not one whose badges contain the text)."""
    return page.locator('%s .ea-app[data-app="%s"] .ea-object:has(.ea-object-name:text-is("%s"))'
                        % (ROOT, app, name))


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
    """Splunk's own apps (launcher, the Monitoring Console...) only appear with "Show Splunk's
    built-in apps"; Search & Reporting is always shown, as users keep their objects there."""
    page = _open(open_view, builtin=False)
    assert page.locator(ROOT + ' .ea-app[data-app="launcher"]').count() == 0
    assert page.locator(ROOT + ' .ea-app[data-app="search"]').count() == 1
    assert page.locator(ROOT + ' .ea-app[data-app="easyadmin"]').count() == 1
    assert "built-in apps are hidden" in page.locator(ROOT + " .ea-summary").inner_text()
    page.locator(ROOT + ' input[data-fid="builtin"]').check()
    assert page.locator(ROOT + ' .ea-app[data-app="launcher"]').count() == 1


def test_type_menu_shows_common_types_first(open_view, shot):
    """The type menu starts with the common types ticked; administrator types such as
    navigation menus are hidden until ticked, and the menu closes with Escape."""
    page = _open(open_view, builtin=False)
    nav = _object(page, "easyadmin", "default")
    assert nav.count() == 0   # the app's navigation menu: an administrator's type
    assert _object(page, "easyadmin", "role_management").count() == 1   # a dashboard: common
    button = page.locator(ROOT + ' button[data-fid="types-button"]')
    assert button.inner_text().startswith("Types: 13 of 20")
    button.click()
    assert button.get_attribute("aria-expanded") == "true"
    menu = page.locator(ROOT + " #ea-types-menu")
    assert menu.locator('input[data-fid="type:view"]').is_checked()
    assert not menu.locator('input[data-fid="type:panel"]').is_checked()
    assert not menu.locator('input[data-fid="type:timerange"]').is_checked()
    shot(page, "app_management_types")
    menu.locator('input[data-fid="type:nav"]').check()
    assert nav.count() == 1
    assert page.locator(ROOT + " #ea-types-menu").count() == 1   # stays open while ticking
    page.keyboard.press("Escape")
    assert page.locator(ROOT + " #ea-types-menu").count() == 0
    assert button.inner_text().startswith("Types: 14 of 20")
    # Tabbing out of the open menu closes it too.
    button.click()
    page.locator(ROOT + ' input[data-fid="type:alertaction"]').focus()
    page.keyboard.press("Tab")
    assert page.locator(ROOT + " #ea-types-menu").count() == 0
    button.click()
    page.locator(ROOT + ' button[data-fid="types-2"]').click()   # None
    assert page.locator(ROOT + " .ea-object").count() == 0
    assert "No object types are selected" in page.locator(ROOT).inner_text()
    page.locator(ROOT + ' button[data-fid="types-1"]').click()   # All
    assert page.locator(ROOT + ' button[data-fid="types-button"]').inner_text().startswith("Types: all")


def test_app_filter_narrows_the_boxes(open_view):
    """"Filter apps by name" keeps only apps whose label or directory name contains the text."""
    page = _open(open_view)
    page.locator(ROOT + " .ea-app-filter").fill("easy")
    apps = page.locator(ROOT + " .ea-app").evaluate_all("nodes => nodes.map(n => n.getAttribute('data-app'))")
    assert apps == ["easyadmin"]
    page.locator(ROOT + " .ea-app-filter").fill("reporting")   # matches the label Search & Reporting
    apps = page.locator(ROOT + " .ea-app").evaluate_all("nodes => nodes.map(n => n.getAttribute('data-app'))")
    assert apps == ["search"]
    page.locator(ROOT + " .ea-app-filter").fill("no_such_app_anywhere")
    assert 'No apps match the filter "no_such_app_anywhere"' in page.locator(ROOT).inner_text()


def test_select_all_in_an_app_selects_what_it_shows(open_view, macro):
    """One tick in an app's header selects every object shown in it; half-ticked when only some are."""
    first, second = macro(), macro()
    page = _open(open_view)
    page.locator(ROOT + " .ea-filter").fill("easyadmin_ui_")
    box = page.locator(ROOT + ' .ea-app[data-app="search"]')
    box.locator(".ea-select-app").check()
    assert "2 objects selected" in page.locator(ROOT + " .ea-selection").inner_text()
    assert _object(page, "search", first).locator(".ea-select").is_checked()
    _object(page, "search", second).locator(".ea-select").uncheck()
    assert box.locator(".ea-select-app").evaluate("n => n.indeterminate") is True
    # As with any half-ticked box, a click selects them all; a second clears them.
    box.locator(".ea-select-app").click()
    assert "2 objects selected" in page.locator(ROOT + " .ea-selection").inner_text()
    box.locator(".ea-select-app").click()
    assert page.locator(ROOT + " .ea-selection strong").count() == 0


def test_sharing_is_colour_coded_and_labelled(open_view, macro, sandbox_client):
    """Each object's sharing badge has its own colour class and says its level in words."""
    name = macro()
    sandbox_client.request("POST", "/servicesNS/nobody/search/admin/macros/%s/acl" % q(name),
                           {"sharing": "global", "owner": "admin", "perms.read": "*", "perms.write": "admin"})
    page = _open(open_view)
    page.locator(ROOT + " .ea-filter").fill(name)
    badge = _object(page, "search", name).locator(".ea-share")
    assert badge.inner_text() == "All apps"
    assert "ea-share-global" in badge.get_attribute("class")
    colours = page.locator(ROOT + " .ea-sharing-key .ea-share").evaluate_all(
        "nodes => nodes.map(n => getComputedStyle(n).backgroundColor)")
    assert len(set(colours)) == 4   # private, this app, all apps, system


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
    _room_to_drag(page)
    page.locator(ROOT + " .ea-filter").fill(name)
    # Dropped back on its own app: nothing is staged, and the page says so.
    _object(page, "search", name).drag_to(page.locator(ROOT + ' .ea-app[data-app="search"] .ea-app-head'))
    assert "Nothing to do" in page.locator(ROOT + " .ea-messages").inner_text()
    assert page.locator(ROOT + " .ea-apply").is_disabled()
    _object(page, "search", name).drag_to(page.locator(ROOT + ' .ea-app[data-app="launcher"]'))
    assert 'Staged a move of 1 object to "Home" (launcher)' in page.locator(ROOT + " .ea-messages").inner_text()
    moved = _object(page, "launcher", name)
    assert moved.count() == 1
    assert "moving from search" in moved.inner_text()
    assert "ea-changed" in moved.get_attribute("class")
    assert page.locator(ROOT + " .ea-apply").inner_text() == "Apply changes to 1 object"
    shot(page, "app_management_staged_move")
    # Nothing is written until Apply.
    assert _acl(sandbox_client, "search", name)["app"] == "search"

    prompt = _apply(page)
    assert "move 1 object" in prompt
    assert _acl(sandbox_client, "launcher", name)["app"] == "launcher"
    success = page.locator(ROOT + " .ea-message.ea-success").inner_text()
    assert "Applied changes to 1 object:" in success
    assert 'Moved search macro "%s" to "launcher".' % name in success
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
    assert seen["message"] == "Discard the staged changes to 1 object? Nothing has been applied yet."
    assert "will be deleted" not in _object(page, "search", name).inner_text()
    assert page.locator(ROOT + " .ea-apply").is_disabled()
    assert _acl(sandbox_client, "search", name)["app"] == "search"


def test_object_in_default_cannot_be_moved_or_deleted(open_view):
    """An object shipped in default/ is marked locked; its panel says why it cannot be moved or deleted."""
    page = _open(open_view, builtin=False)
    row = _object(page, "easyadmin", "role_management")
    assert row.locator(".ea-locked").count() == 1
    # Still draggable: dropping it on another app stages a copy instead.
    assert row.get_attribute("draggable") == "true"
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


# ------------------------------------------------------------------- copying

@pytest.fixture
def cleanup_launcher_macros(sandbox_client):
    """Names of macros a test copies into launcher; deleted from there afterwards."""
    names = []
    yield names
    for name in names:
        try:
            sandbox_client.request("DELETE", "/servicesNS/nobody/launcher/admin/macros/%s" % q(name))
        except SplunkError:
            pass


def _shipped_search_macro(sandbox_client):
    """A macro that ships in the search app's default folder (cannot be moved)."""
    for e in sandbox_client.request("GET", "/servicesNS/nobody/search/admin/macros",
                                    {"count": 0, "search": "eai:acl.app=search"})["entry"]:
        if "move" not in (e.get("links") or {}) and e["acl"]["app"] == "search":
            return e["name"]
    pytest.skip("no shipped macro in the search app")


def test_dragging_a_default_object_stages_a_copy(open_view, sandbox_client, cleanup_launcher_macros, shot):
    """An object in a default folder cannot be moved, so dropping it on another app stages a copy."""
    name = _shipped_search_macro(sandbox_client)
    cleanup_launcher_macros.append(name)
    page = _open(open_view)
    _room_to_drag(page)
    page.locator(ROOT + " .ea-filter").fill(name)
    source = _object(page, "search", name)
    assert source.get_attribute("draggable") == "true"
    source.drag_to(page.locator(ROOT + ' .ea-app[data-app="launcher"]'))
    text = page.locator(ROOT + " .ea-messages").inner_text()
    assert 'Staged a copy of 1 object into "Home" (launcher).' in text
    assert "Objects that cannot be moved (in a default folder" in text and "were copied instead." in text
    assert "copying to launcher" in _object(page, "search", name).inner_text()
    ghost = page.locator(ROOT + ' .ea-app[data-app="launcher"] .ea-ghost:has(.ea-object-name:text-is("%s"))' % name)
    assert ghost.count() == 1 and "copy from search" in ghost.inner_text()
    shot(page, "app_management_staged_copy")
    prompt = _apply(page)
    assert "copy 1 object into another app" in prompt
    copied = sandbox_client.request("GET", "/servicesNS/nobody/launcher/admin/macros/%s" % q(name))["entry"][0]
    assert copied["acl"]["app"] == "launcher"
    assert _object(page, "search", name).count() == 1   # the original is still there


def test_copy_from_the_selection_bar(open_view, macro, sandbox_client, cleanup_launcher_macros):
    """Ticking an object, choosing an app and pressing Copy stages a copy rather than a move."""
    name = macro()
    cleanup_launcher_macros.append(name)
    page = _open(open_view)
    page.locator(ROOT + " .ea-filter").fill(name)
    _object(page, "search", name).locator(".ea-select").check()
    page.locator(ROOT + " .ea-move-target").select_option("launcher")
    page.locator(ROOT + ' button[data-fid="copy-selected"]').click()
    assert "copying to launcher" in _object(page, "search", name).inner_text()
    _apply(page)
    assert _acl(sandbox_client, "launcher", name)["app"] == "launcher"
    assert _acl(sandbox_client, "search", name)["app"] == "search"


def test_copy_from_the_panel(open_view, macro, sandbox_client, cleanup_launcher_macros):
    """The panel's "Copy to app" stages a copy; "Do not copy" takes it back."""
    name = macro()
    cleanup_launcher_macros.append(name)
    page = _open(open_view)
    page.locator(ROOT + " .ea-filter").fill(name)
    _object(page, "search", name).locator(".ea-object-name").click()
    panel = page.locator(ROOT + " .ea-panel")
    panel.locator("#ea-copy").select_option("launcher")
    assert "copying to launcher" in _object(page, "search", name).inner_text()
    panel.locator("#ea-copy").select_option("")
    assert "copying to" not in _object(page, "search", name).inner_text()
    panel.locator("#ea-copy").select_option("launcher")
    page.keyboard.press("Escape")
    _apply(page)
    assert _acl(sandbox_client, "launcher", name)["app"] == "launcher"


def test_copy_to_an_app_that_has_the_name_is_caught_when_staging(open_view, macro, sandbox_client,
                                                                   cleanup_launcher_macros):
    """Copying where the target app already has an object of that type and name is refused at once."""
    name = macro()
    cleanup_launcher_macros.append(name)
    sandbox_client.request("POST", "/servicesNS/nobody/launcher/admin/macros",
                           {"name": name, "definition": "index=_audit"})
    page = _open(open_view)
    page.locator(ROOT + " .ea-filter").fill(name)
    _object(page, "search", name).locator(".ea-select").check()
    page.locator(ROOT + " .ea-move-target").select_option("launcher")
    page.locator(ROOT + ' button[data-fid="copy-selected"]').click()
    assert "already has an object of the same type and name" in page.locator(ROOT + " .ea-messages").inner_text()
    assert page.locator(ROOT + " .ea-apply").is_disabled()


def test_each_staged_change_can_be_discarded_on_its_own(open_view, macro, shot):
    """The x on a staged-change badge discards that change only; the object's other changes stay."""
    name = macro()
    page = _open(open_view)
    page.locator(ROOT + " .ea-filter").fill(name)
    # Stage two changes on one object: a move and a permission change.
    _object(page, "search", name).locator(".ea-select").check()
    page.locator(ROOT + " .ea-move-target").select_option("launcher")
    page.locator(ROOT + ' button[data-fid="move-selected"]').click()
    _object(page, "launcher", name).locator(".ea-object-name").click()
    page.locator(ROOT + " .ea-panel #ea-sharing").select_option("global")
    page.keyboard.press("Escape")
    row = _object(page, "launcher", name)
    assert "moving from search" in row.inner_text() and "permissions changed" in row.inner_text()
    # With several badges the name keeps its width; the badges wrap instead.
    assert row.locator(".ea-object-name").evaluate("n => n.getBoundingClientRect().width") >= 140
    shot(page, "app_management_discard_one")

    move_x = row.locator('.ea-discard-one[data-kind="move"]')
    assert move_x.get_attribute("aria-label").startswith("Discard staged change: moving from search")
    move_x.click()
    back = _object(page, "search", name)
    assert "moving from" not in back.inner_text()
    assert "permissions changed" in back.inner_text()
    assert page.locator(ROOT + " .ea-apply").inner_text() == "Apply changes to 1 object"
    assert "Its other staged change is kept." in page.locator(ROOT + " .ea-messages").inner_text()
    # The keyboard stays on the object.
    assert page.evaluate("document.activeElement.getAttribute('data-fid')").startswith("open:")

    back.locator('.ea-discard-one[data-kind="acl"]').click()
    assert page.locator(ROOT + " .ea-apply").is_disabled()
    # That was its last change, so the message does not claim others are kept.
    assert "other staged" not in page.locator(ROOT + " .ea-messages").inner_text()


def test_a_staged_copy_can_be_discarded_from_its_dashed_row(open_view, macro):
    """The x on a staged copy's row in the target app drops the copy and nothing else."""
    name = macro()
    page = _open(open_view)
    page.locator(ROOT + " .ea-filter").fill(name)
    _object(page, "search", name).locator(".ea-select").check()
    page.locator(ROOT + " .ea-move-target").select_option("launcher")
    page.locator(ROOT + ' button[data-fid="copy-selected"]').click()
    ghost = page.locator(ROOT + ' .ea-app[data-app="launcher"] .ea-ghost')
    assert ghost.count() == 1
    ghost.locator('.ea-discard-one[data-kind="copy"]').click()
    assert page.locator(ROOT + ' .ea-app[data-app="launcher"] .ea-ghost').count() == 0
    assert "copying to" not in _object(page, "search", name).inner_text()
    assert page.locator(ROOT + " .ea-apply").is_disabled()


def test_panel_shows_the_objects_own_settings_first(open_view, macro, shot):
    """The panel lists only the settings set in the object; inherited ones come on request."""
    name = macro()
    page = _open(open_view)
    page.locator(ROOT + " .ea-filter").fill(name)
    _object(page, "search", name).locator(".ea-object-name").click()
    panel = page.locator(ROOT + " .ea-panel")
    panel.locator(".ea-settings").first.wait_for()
    assert "Settings set in this object" in panel.inner_text()
    names = [t.strip() for t in panel.locator(".ea-settings dt").all_inner_texts()]
    # The macro was created with only a definition (the badge text follows the name).
    assert len(names) == 1 and names[0].startswith("definition")
    assert panel.locator(".ea-setting-layer").inner_text() == "local"
    shot(page, "app_management_own_settings")
    show = panel.locator(".ea-show-all")
    assert show.get_attribute("aria-expanded") == "false"
    show.click()
    assert page.locator(ROOT + " .ea-panel .ea-settings").count() == 2
    # The full list (as splunkd reports it, inherited settings included) is longer.
    lists = page.locator(ROOT + " .ea-panel .ea-settings")
    assert lists.nth(1).locator("dt").count() > lists.nth(0).locator("dt").count()
    page.locator(ROOT + " .ea-panel .ea-show-all").click()
    assert page.locator(ROOT + " .ea-panel .ea-settings").count() == 1


@pytest.fixture
def cleanup_launcher_reports(sandbox_client):
    names = []
    yield names
    for name in names:
        try:
            sandbox_client.request("DELETE", "/servicesNS/nobody/launcher/saved/searches/%s" % q(name))
        except SplunkError:
            pass


def test_move_button_copies_what_cannot_be_moved(open_view, sandbox_client, cleanup_launcher_reports):
    """Move on an object that ships in a default folder stages a copy instead, and says so."""
    shipped = next(e["name"] for e in sandbox_client.request(
        "GET", "/servicesNS/nobody/search/saved/searches", {"count": 0, "search": "eai:acl.app=search"})["entry"]
        if e["acl"]["app"] == "search" and not e["acl"].get("removable"))
    cleanup_launcher_reports.append(shipped)
    page = _open(open_view)
    page.locator(ROOT + " .ea-filter").fill(shipped)
    row = _object(page, "search", shipped)
    assert row.locator(".ea-locked").count() == 1
    row.locator(".ea-select").check()
    page.locator(ROOT + " .ea-move-target").select_option("launcher")
    page.locator(ROOT + ' button[data-fid="move-selected"]').click()
    text = page.locator(ROOT + " .ea-messages").inner_text()
    assert 'Staged a copy of 1 object into "Home" (launcher).' in text and "were copied instead" in text
    assert "copying to launcher" in _object(page, "search", shipped).inner_text()


# ------------------------------------------------------- creating and cloning
#
# Stage and discard only: applying a create would add a second app per run
# (and a restart to remove it). The live test covers Apply.

NEW_APP = "easyadmin_ui_newapp"
CLONE_APP = "easyadmin_ui_clone"


def _form(page):
    return page.locator(ROOT + " .ea-panel")


def _fill(page, field, value):
    page.locator(ROOT + ' .ea-panel input[data-fid="newapp-%s"]' % field).fill(value)


def _accept_dialogs(page):
    seen = []

    def answer(dialog):
        seen.append(dialog.message)
        dialog.accept()
    page.on("dialog", answer)
    return seen


def _stage_new_app(page):
    page.locator(ROOT + ' button[data-fid="new-app"]').click()
    _fill(page, "name", NEW_APP)
    _fill(page, "label", "UI Test New App")
    page.locator(ROOT + ' button[data-fid="newapp-stage"]').click()
    return page.locator(ROOT + ' .ea-app[data-app="%s"]' % NEW_APP)


def test_new_app_form_validates_before_it_stages(open_view, shot):
    """Stage stays disabled until the ID and label are acceptable; each refusal says why."""
    page = _open(open_view)
    page.locator(ROOT + ' button[data-fid="new-app"]').click()
    form = _form(page)
    stage = form.locator('button[data-fid="newapp-stage"]')
    assert form.locator("#ea-panel-title").inner_text() == "New app"
    # The defaults: version 1.0.0, the signed-in user as author, visible.
    assert form.locator('input[data-fid="newapp-version"]').input_value() == "1.0.0"
    assert form.locator('input[data-fid="newapp-author"]').input_value() != ""
    assert form.locator('input[data-fid="newapp-visible"]').is_checked()
    assert stage.is_disabled()

    _fill(page, "name", "search")
    assert "already exists" in form.locator("#ea-newapp-name-error").inner_text()
    _fill(page, "name", "SEARCH")   # compared ignoring case
    assert "already exists" in form.locator("#ea-newapp-name-error").inner_text()
    _fill(page, "name", "bad name")
    assert "Use letters" in form.locator("#ea-newapp-name-error").inner_text()
    assert form.locator('input[data-fid="newapp-name"]').get_attribute("aria-invalid") == "true"
    _fill(page, "name", NEW_APP)
    assert form.locator("#ea-newapp-name-error").inner_text() == ""
    _fill(page, "label", "abc")
    assert "5 to 80" in form.locator("#ea-newapp-label-error").inner_text()
    _fill(page, "label", "Splunk for Testing")
    assert "Splunk for" in form.locator("#ea-newapp-label-error").inner_text()
    assert stage.is_disabled()
    _fill(page, "label", "UI Test New App")
    _fill(page, "version", "1 2")
    assert "letters, digits" in form.locator("#ea-newapp-version-error").inner_text()
    assert stage.is_disabled()
    _fill(page, "version", "")      # empty means the default
    assert not stage.is_disabled()
    shot(page, "app_management_new_app_form")
    # Escape closes the form and nothing is staged.
    page.keyboard.press("Escape")
    assert page.locator(ROOT + " .ea-panel").count() == 0
    assert page.locator(ROOT + ' .ea-app[data-app="%s"]' % NEW_APP).count() == 0
    assert page.locator(ROOT + " .ea-apply").is_disabled()


def test_a_new_app_is_staged_as_a_box_and_can_be_discarded(open_view, shot):
    page = _open(open_view)
    box = _stage_new_app(page)
    assert box.count() == 1 and "ea-app-new" in box.get_attribute("class")
    assert box.locator(".ea-app-title").inner_text() == "UI Test New App"
    assert "new app" in box.locator(".ea-app-meta").inner_text()
    assert page.locator(ROOT + " .ea-apply").inner_text() == "Apply changes to 1 app"
    assert page.locator(ROOT + " .ea-apply").is_enabled()
    assert "Staged a new app" in page.locator(ROOT + " .ea-messages").inner_text()
    # A new app holds nothing yet, so it has no Clone button.
    assert box.locator(".ea-clone").count() == 0
    # The app filter cannot hide a staged box.
    page.locator(ROOT + " .ea-app-filter").fill("zzz-no-such-app")
    assert page.locator(ROOT + ' .ea-app[data-app="%s"]' % NEW_APP).count() == 1
    page.locator(ROOT + " .ea-app-filter").fill("")
    shot(page, "app_management_new_app_staged")
    # Its x drops it; nothing was staged into it, so there is no confirmation.
    cross = box.locator(".ea-discard-app")
    assert cross.get_attribute("aria-label").startswith("Discard new app UI Test New App")
    cross.click()
    assert page.locator(ROOT + ' .ea-app[data-app="%s"]' % NEW_APP).count() == 0
    assert page.locator(ROOT + " .ea-apply").is_disabled()


def test_discard_changes_drops_a_staged_app_and_its_id_is_taken_meanwhile(open_view):
    page = _open(open_view)
    _stage_new_app(page)
    # The staged app holds its ID: another app cannot be staged under it.
    page.locator(ROOT + ' button[data-fid="new-app"]').click()
    _fill(page, "name", NEW_APP.upper())
    assert "already exists" in page.locator(ROOT + " #ea-newapp-name-error").inner_text()
    page.keyboard.press("Escape")
    seen = _accept_dialogs(page)
    assert page.locator(ROOT + " .ea-discard").inner_text() == "Discard changes to 1 app"
    page.locator(ROOT + " .ea-discard").click()
    assert seen == ["Discard the staged changes to 1 app? Nothing has been applied yet."]
    assert page.locator(ROOT + ' .ea-app[data-app="%s"]' % NEW_APP).count() == 0


def test_a_staged_app_takes_copies_and_its_x_asks_first(open_view, macro):
    """The selection bar copies into the staged box; its x then asks, and drops the copies with it."""
    name = macro()
    page = _open(open_view)
    box = _stage_new_app(page)
    page.locator(ROOT + " .ea-filter").fill(name)
    _object(page, "search", name).locator(".ea-select").check()
    page.locator(ROOT + " .ea-move-target").select_option(NEW_APP)
    page.locator(ROOT + ' button[data-fid="copy-selected"]').click()
    ghost = box.locator(".ea-ghost")
    assert ghost.count() == 1 and ghost.locator(".ea-object-name").inner_text() == name
    assert page.locator(ROOT + " .ea-apply").inner_text() == "Apply changes to 1 app and 1 object"
    seen = _accept_dialogs(page)
    box.locator(".ea-discard-app").click()
    assert len(seen) == 1 and "1 object into it" in seen[0]
    assert page.locator(ROOT + ' .ea-app[data-app="%s"]' % NEW_APP).count() == 0
    assert "copying to" not in _object(page, "search", name).inner_text()
    assert page.locator(ROOT + " .ea-apply").is_disabled()


def test_dropping_an_object_on_a_staged_app_stages_a_move(open_view, macro):
    name = macro()
    page = _open(open_view)
    box = _stage_new_app(page)
    _room_to_drag(page)
    page.locator(ROOT + " .ea-filter").fill(name)
    _object(page, "search", name).drag_to(box)
    moved = _object(page, NEW_APP, name)
    assert moved.count() == 1 and "moving from search" in moved.inner_text()
    assert page.locator(ROOT + " .ea-apply").inner_text() == "Apply changes to 1 app and 1 object"


def test_clone_stages_a_copy_of_every_copyable_object_and_says_what_it_leaves_out(open_view, macro, shot):
    name = macro()
    page = _open(open_view)
    source_label = page.locator(ROOT + ' .ea-app[data-app="search"] .ea-app-title').inner_text()
    clone = page.locator(ROOT + ' button[data-fid="clone:search"]')
    assert clone.get_attribute("aria-label").startswith("Clone app " + source_label)
    clone.click()
    form = _form(page)
    assert form.locator("#ea-panel-title").inner_text() == "Clone " + source_label
    assert form.locator('input[data-fid="newapp-name"]').input_value() == "search_copy"
    assert form.locator('input[data-fid="newapp-label"]').input_value() == source_label + " (copy)"
    assert form.locator('input[data-fid="newapp-version"]').input_value() == "1.0.0"
    assert not form.locator('button[data-fid="newapp-stage"]').is_disabled()
    # The ID must be free: an existing one is refused here, not at Apply.
    _fill(page, "name", "launcher")
    assert "already exists" in form.locator("#ea-newapp-name-error").inner_text()
    assert form.locator('button[data-fid="newapp-stage"]').is_disabled()
    _fill(page, "name", CLONE_APP)
    page.locator(ROOT + ' button[data-fid="newapp-stage"]').click()

    box = page.locator(ROOT + ' .ea-app[data-app="%s"]' % CLONE_APP)
    assert "clone of " + source_label in box.locator(".ea-app-meta").inner_text()
    # Its rows are dashed copies of the search app's, the new macro among them.
    ghosts = box.locator(".ea-ghost")
    total = ghosts.count()
    assert total >= 1
    assert box.locator('.ea-ghost .ea-object-name:text-is("%s")' % name).count() == 1
    assert "copy from search" in ghosts.first.inner_text()
    message = page.locator(ROOT + " .ea-messages").inner_text()
    assert "Staged a copy of" in message and 'from "%s"' % source_label in message
    # What splunkd cannot copy is listed by type, and the navigation is explained.
    assert "Left out, because splunkd cannot copy them:" in message
    assert "navigation menu" in message
    shot(page, "app_management_clone_staged")

    # One copy can be dropped on its own; the rest stay.
    box.locator('.ea-ghost:has(.ea-object-name:text-is("%s")) .ea-discard-one' % name).click()
    assert box.locator(".ea-ghost").count() == total - 1
    assert box.locator('.ea-ghost .ea-object-name:text-is("%s")' % name).count() == 0
    assert "copying to" not in _object(page, "search", name).inner_text()
    # The box's x takes the remaining copies with it, after asking.
    seen = _accept_dialogs(page)
    box.locator(".ea-discard-app").click()
    assert len(seen) == 1 and CLONE_APP in seen[0]
    assert page.locator(ROOT + ' .ea-app[data-app="%s"]' % CLONE_APP).count() == 0
    assert page.locator(ROOT + " .ea-apply").is_disabled()


def _staged_clone_of_search(page):
    """Stage a clone of search (common types) and return its box."""
    page.locator(ROOT + ' button[data-fid="clone:search"]').click()
    _fill(page, "name", CLONE_APP)
    page.locator(ROOT + ' button[data-fid="newapp-stage"]').click()
    return page.locator(ROOT + ' .ea-app[data-app="%s"]' % CLONE_APP)


def _copy_count(page):
    """The number of objects the Apply button says it will touch."""
    text = page.locator(ROOT + " .ea-apply").inner_text()
    return int(re.search(r"and (\d+) objects?", text).group(1))


def test_a_clone_box_counts_its_staged_copies_and_those_the_filters_hide(open_view, macro, shot):
    """A clone's header says "0 objects, N staged", not a bare "0 objects"; copies the Types menu
    or the name filter keep out of the list are counted at the foot of the box."""
    name = macro()
    page = _open(open_view)
    box = _staged_clone_of_search(page)
    meta = box.locator(".ea-app-meta")
    total = _copy_count(page)   # every copyable object, whatever the filters show
    listed = box.locator(".ea-ghost").count()
    assert listed >= 1
    assert "0 objects, %d staged" % listed in meta.inner_text()
    assert not re.search(r"\b0 objects(?!,)", meta.inner_text())
    note = box.locator(".ea-hidden-staged")
    if total > listed:
        hidden = total - listed
        assert note.inner_text() == "%s hidden by the filters." % (
            "1 staged copy is" if hidden == 1 else "%d staged copies are" % hidden)
    else:
        assert note.count() == 0
    shot(page, "app_management_clone_counts")

    # All types: nothing is hidden, so every copy is listed and the note goes.
    page.locator(ROOT + ' button[data-fid="types-button"]').click()
    page.locator(ROOT + ' button[data-fid="types-1"]').click()
    page.keyboard.press("Escape")
    assert box.locator(".ea-ghost").count() == total
    assert "0 objects, %d staged" % total in meta.inner_text()
    assert box.locator(".ea-hidden-staged").count() == 0

    # A name filter lists the one matching copy and counts the rest as hidden.
    page.locator(ROOT + " .ea-filter").fill(name)
    assert box.locator(".ea-ghost").count() == 1
    assert "0 matches, 1 staged" in meta.inner_text()
    assert box.locator(".ea-hidden-staged").inner_text() == "%s hidden by the filters." % (
        "1 staged copy is" if total - 1 == 1 else "%d staged copies are" % (total - 1))

    seen = _accept_dialogs(page)
    box.locator(".ea-discard-app").click()
    assert len(seen) == 1
    assert page.locator(ROOT + " .ea-apply").is_disabled()


def test_a_box_with_only_hidden_staged_copies_stays_on_show(open_view, macro, cleanup_launcher_macros):
    """The app filter does not hide a box that has staged copies the Types menu keeps out of its list."""
    name = macro()
    cleanup_launcher_macros.append(name)
    page = _open(open_view)
    page.locator(ROOT + " .ea-filter").fill(name)
    _object(page, "search", name).locator(".ea-select").check()
    page.locator(ROOT + " .ea-move-target").select_option("launcher")
    page.locator(ROOT + ' button[data-fid="copy-selected"]').click()
    assert "copying to launcher" in _object(page, "search", name).inner_text()
    page.locator(ROOT + " .ea-filter").fill("")

    page.locator(ROOT + ' button[data-fid="types-button"]').click()
    page.locator(ROOT + ' input[data-fid="type:macro"]').uncheck()
    page.keyboard.press("Escape")
    page.locator(ROOT + " .ea-app-filter").fill("search")
    box = page.locator(ROOT + ' .ea-app[data-app="launcher"]')
    assert box.count() == 1
    assert box.locator(".ea-hidden-staged").inner_text() == "1 staged copy is hidden by the filters."
    assert ", 1 staged" not in box.locator(".ea-app-meta").inner_text()
    assert box.locator(".ea-ghost").count() == 0

    seen = _accept_dialogs(page)
    page.locator(ROOT + ' button[data-fid="discard"]').click()
    assert len(seen) == 1
    assert page.locator(ROOT + " .ea-apply").is_disabled()


def test_hidden_staged_moves_and_deletions_are_counted_too(open_view, macro, cleanup_launcher_macros):
    """A move is counted in the box it goes to, a deletion in the box the object is in, when the
    Types menu keeps the object out of the list; both are said alongside a hidden copy."""
    moved, deleted, copied = macro(), macro(), macro()
    cleanup_launcher_macros.extend([moved, copied])
    page = _open(open_view)

    def stage(name, button, target=None):
        page.locator(ROOT + " .ea-filter").fill(name)
        _object(page, "search", name).locator(".ea-select").check()
        if target:
            page.locator(ROOT + " .ea-move-target").select_option(target)
        page.locator(ROOT + ' button[data-fid="%s"]' % button).click()
        page.locator(ROOT + ' button[data-fid="clear-selection"]').click()

    stage(moved, "move-selected", "launcher")
    stage(deleted, "delete-selected")
    assert "will be deleted" in _object(page, "search", deleted).inner_text()
    page.locator(ROOT + " .ea-filter").fill("")
    assert "moving from search" in page.locator(ROOT + " .ea-app[data-app='launcher']").inner_text()

    page.locator(ROOT + ' button[data-fid="types-button"]').click()
    page.locator(ROOT + ' input[data-fid="type:macro"]').uncheck()
    page.keyboard.press("Escape")
    launcher = page.locator(ROOT + ' .ea-app[data-app="launcher"]')
    search = page.locator(ROOT + ' .ea-app[data-app="search"]')
    assert launcher.locator(".ea-hidden-staged").inner_text() == "1 staged move is hidden by the filters."
    assert search.locator(".ea-hidden-staged").inner_text() == "1 staged deletion is hidden by the filters."
    assert moved not in launcher.inner_text()

    # A copy into the same box is said in the same line.
    page.locator(ROOT + ' button[data-fid="types-button"]').click()
    page.locator(ROOT + ' input[data-fid="type:macro"]').check()
    page.keyboard.press("Escape")
    stage(copied, "copy-selected", "launcher")
    page.locator(ROOT + " .ea-filter").fill("")
    page.locator(ROOT + ' button[data-fid="types-button"]').click()
    page.locator(ROOT + ' input[data-fid="type:macro"]').uncheck()
    page.keyboard.press("Escape")
    assert launcher.locator(".ea-hidden-staged").inner_text() == \
        "1 staged copy and 1 staged move are hidden by the filters."
    assert search.locator(".ea-hidden-staged").inner_text() == "1 staged deletion is hidden by the filters."

    seen = _accept_dialogs(page)
    page.locator(ROOT + ' button[data-fid="discard"]').click()
    assert len(seen) == 1
    assert page.locator(ROOT + " .ea-apply").is_disabled()
    assert page.locator(ROOT + " .ea-hidden-staged").count() == 0
