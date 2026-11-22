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


_STARTED_MS = int(time.time() * 1000)
_swept = []


def _sweep_orphans(client):
    """Delete ``easyadmin_ui_<ms>`` macros left by an interrupted earlier run, once per process.

    The select-all tests count what the name filter shows, so one orphan makes
    them fail ("3 objects selected", expected 2). Only names stamped before this
    process started are removed, so a macro made by a running test is safe.
    """
    if _swept:
        return
    _swept.append(True)
    for app in ("search", "launcher"):
        try:
            entries = client.request("GET", "/servicesNS/nobody/%s/admin/macros" % app,
                                     {"count": 0, "search": "name=easyadmin_ui_*"})["entry"]
        except SplunkError:
            continue
        for entry in entries:
            # Also the conf tab's clashing macro (easyadmin_ui_conf_<ms>): its fixture
            # swallows a failed delete, and one left over made these counts one too high.
            found = re.fullmatch(r"easyadmin_ui_(?:conf_)?(\d{13})", entry["name"])
            if found and int(found.group(1)) < _STARTED_MS and entry["acl"]["app"] == app:
                try:
                    client.request("DELETE", "/servicesNS/nobody/%s/admin/macros/%s" % (app, q(entry["name"])))
                except SplunkError:
                    pass


@pytest.fixture
def macro(sandbox_client):
    """Create a local macro in search; delete it afterwards from search or launcher."""
    _sweep_orphans(sandbox_client)
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


HIDE = ROOT + ' input[data-fid="hide-empty"]'
HIDDEN_AREA = ROOT + ' .ea-hidden-area[data-kind="empty"].ea-show'
BUILTIN_AREA = ROOT + ' .ea-hidden-area[data-kind="builtin"].ea-show'


def _show_empty_apps(page):
    """Untick "Hide apps with no matching objects", so every box is a drop target as before."""
    page.locator(HIDE).uncheck()


def _an_empty_app(page):
    """Name an app that lists no object on this target: its box shows only once the switch is unticked.

    Not a fixed app: even launcher holds a view, a nav and tags here, and what
    each dev instance ships differs. Leaves the switch ticked.
    """
    tick = page.locator(HIDE)
    names = lambda: set(page.locator(ROOT + " .ea-app").evaluate_all(
        "nodes => nodes.map(n => n.getAttribute('data-app'))"))
    tick.check()
    on_show = names()
    tick.uncheck()
    every = names()
    tick.check()
    # A box that only the switch hides, and that takes a drop (a new-app box is staged, so always on show).
    empty = sorted(every - on_show)
    if not empty:
        pytest.skip("this target has no app without objects: the switch has nothing to hide")
    return empty[0]


def _begin_drag(page, row):
    """Press on ``row`` and move a little: the drag starts and the page reacts to it."""
    row.hover()
    box = row.bounding_box()
    page.mouse.down()
    page.mouse.move(box["x"] + box["width"] / 2 + 10, box["y"] + box["height"] / 2 + 10, steps=3)


def _open_hidden_area(page, area=HIDDEN_AREA):
    """Wait for a drop area ("Hidden apps" unless told otherwise) to appear mid-drag, then hover it so its list opens."""
    area = page.locator(area)
    area.wait_for()
    box = area.bounding_box()
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2, steps=5)


def _hover_hidden_app(page, app):
    """Move onto a listed hidden app (the list opens when the area is hovered)."""
    target = page.locator(ROOT + ' .ea-hidden-target[data-app="%s"]' % app)
    target.wait_for()
    box = target.bounding_box()
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2, steps=5)


def _drag_to_hidden_app(page, row, app, area=HIDDEN_AREA):
    """Drag ``row`` onto ``app`` in a drop area ("Hidden apps" unless told otherwise), as a person would with the pointer."""
    _begin_drag(page, row)
    _open_hidden_area(page, area)
    _hover_hidden_app(page, app)
    page.mouse.up()


def _object(page, app, name):
    """The row of the object called exactly ``name`` (not one whose badges contain the text)."""
    return page.locator('%s .ea-app[data-app="%s"] .ea-object:has(.ea-object-name:text-is("%s"))'
                        % (ROOT, app, name))


def _moving_out(page, app, name):
    """The struck-through row an object keeps in the app a staged move takes it from."""
    return page.locator('%s .ea-app[data-app="%s"] .ea-moving-out:has(.ea-object-name:text-is("%s"))'
                        % (ROOT, app, name))


def _struck(row):
    """Whether the row's name is drawn with a line through it (computed style, not the class)."""
    return "line-through" in row.locator(".ea-object-name").evaluate(
        "n => getComputedStyle(n).textDecorationLine")


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
    _app_filter(page, "easy")
    apps = page.locator(ROOT + " .ea-app").evaluate_all("nodes => nodes.map(n => n.getAttribute('data-app'))")
    assert apps == ["easyadmin"]
    _app_filter(page, "reporting")   # matches the label Search & Reporting
    apps = page.locator(ROOT + " .ea-app").evaluate_all("nodes => nodes.map(n => n.getAttribute('data-app'))")
    assert apps == ["search"]
    _app_filter(page, "no_such_app_anywhere")
    assert 'No apps match the filter "no_such_app_anywhere"' in page.locator(ROOT).inner_text()


PAUSE_MS = 250   # the page waits this long after the last keystroke before it filters


def _watch_redraws(page):
    """Count, from now on, how many grids and toolbars the page draws.

    A render replaces its parent, so the added node holds the grid; matching
    only the added node itself would miss that.
    """
    page.evaluate("""(root) => {
        window.__eaDraws = {grids: 0, bars: 0};
        const count = (node, selector) => node.nodeType === 1
            ? (node.matches(selector) ? 1 : 0) + node.querySelectorAll(selector).length : 0;
        new MutationObserver(records => {
            for (const record of records) {
                for (const node of record.addedNodes) {
                    window.__eaDraws.grids += count(node, '.ea-grid-wrap');
                    window.__eaDraws.bars += count(node, '.ea-toolbar');
                }
            }
        }).observe(document.querySelector(root), {childList: true, subtree: true});
    }""", ROOT)


def _redraws(page):
    return page.evaluate("() => Object.assign({}, window.__eaDraws)")


def _wait_drawn(page, attr, text):
    """Wait for the grid drawn with this filter text (data-filter or data-app-filter).

    The page filters after a pause in typing, so what is on screen right after a
    fill is the old list: wait for the state that proves the new render.
    """
    page.wait_for_function(
        "([attr, text]) => { const w = document.querySelector('#easyadmin-apps .ea-grid-wrap');"
        " return !!w && w.getAttribute(attr) === text; }", arg=[attr, text])


def _filter(page, text):
    """Fill "Filter objects by name" and wait for the list it produces."""
    page.locator(ROOT + " .ea-filter").fill(text)
    _wait_drawn(page, "data-filter", text)


def _app_filter(page, text):
    """Fill "Filter apps by name" and wait for the list it produces."""
    page.locator(ROOT + " .ea-app-filter").fill(text)
    _wait_drawn(page, "data-app-filter", text)


def _focus_state(page):
    return page.evaluate("() => { const a = document.activeElement;"
                         " return [a.className, a.value, a.selectionStart]; }")


def test_object_filter_waits_for_a_pause_then_renders_once(open_view, macro):
    """Typing a name quickly filters once, after the pause, and the field keeps focus and caret."""
    name = macro()
    page = _open(open_view)
    _watch_redraws(page)
    page.locator(ROOT + " .ea-filter").press_sequentially(name, delay=40)
    _wait_drawn(page, "data-filter", name)
    assert page.locator(ROOT + " .ea-object").count() == 1
    assert _object(page, "search", name).count() == 1
    assert _redraws(page) == {"grids": 1, "bars": 0}   # not one body redraw per character
    classes, value, caret = _focus_state(page)
    assert "ea-filter" in classes.split() and value == name and caret == len(name)


def test_app_filter_waits_for_a_pause_then_renders_once(open_view):
    """The same for "Filter apps by name": one redraw, focus and caret kept."""
    page = _open(open_view)
    _watch_redraws(page)
    page.locator(ROOT + " .ea-app-filter").press_sequentially("easyadmin", delay=40)
    _wait_drawn(page, "data-app-filter", "easyadmin")
    apps = page.locator(ROOT + " .ea-app").evaluate_all("nodes => nodes.map(n => n.getAttribute('data-app'))")
    assert apps == ["easyadmin"]
    assert _redraws(page) == {"grids": 1, "bars": 0}
    classes, value, caret = _focus_state(page)
    assert "ea-app-filter" in classes.split() and value == "easyadmin" and caret == len("easyadmin")


def test_a_click_in_the_pause_acts_on_the_list_shown(open_view, macro):
    """Until the pause ends the grid shows the old list, so a select-all tick acts on that list."""
    first, second = macro(), macro()
    shared = first
    while not second.startswith(shared):
        shared = shared[:-1]
    assert len(first) > len(shared), "the two macro names must differ"
    page = _open(open_view)
    page.locator(ROOT + " .ea-filter").fill(shared)
    # Wait on what the list shows (two rows), not on the page's own marker, so
    # the reproduction on code without the pause reaches the tick below.
    page.wait_for_function("(root) => document.querySelectorAll(root + ' .ea-object').length === 2", arg=ROOT)
    # One more character, matching only the first macro, then the tick, in one
    # call so the pause cannot run out in between on a slow machine.
    page.evaluate("""([root, text]) => {
        const input = document.querySelector(root + ' .ea-filter');
        input.value = text;
        input.dispatchEvent(new Event('input', {bubbles: true}));
        document.querySelector(root + ' .ea-app[data-app="search"] .ea-select-app').click();
    }""", [ROOT, first[:len(shared) + 1]])
    assert "2 objects selected" in page.locator(ROOT + " .ea-selection").inner_text()
    _wait_drawn(page, "data-filter", first[:len(shared) + 1])
    assert _object(page, "search", first).count() == 1 and page.locator(ROOT + " .ea-object").count() == 1
    assert "2 objects selected" in page.locator(ROOT + " .ea-selection").inner_text()


def test_reload_during_the_pause_keeps_the_typed_filter(open_view, macro):
    """A full render in the pause (Reload) applies the typed text; no second redraw follows."""
    name = macro()
    page = _open(open_view)
    _watch_redraws(page)
    page.evaluate("""([root, text]) => {
        const input = document.querySelector(root + ' .ea-filter');
        input.value = text;
        input.dispatchEvent(new Event('input', {bubbles: true}));
        document.querySelector(root + ' button[data-fid="reload"]').click();
    }""", [ROOT, name])
    page.locator(ROOT + " .ea-busy").wait_for(state="detached")
    _wait_drawn(page, "data-filter", name)
    assert page.locator(ROOT + " .ea-filter").input_value() == name
    assert _object(page, "search", name).count() == 1 and page.locator(ROOT + " .ea-object").count() == 1
    page.evaluate("() => { window.__eaDraws = {grids: 0, bars: 0}; }")
    page.wait_for_timeout(PAUSE_MS + 50)   # a timer left behind would redraw by now
    assert _redraws(page) == {"grids": 0, "bars": 0}


def test_select_all_in_an_app_selects_what_it_shows(open_view, macro):
    """One tick in an app's header selects every object shown in it; half-ticked when only some are."""
    first, second = macro(), macro()
    page = _open(open_view)
    _filter(page, "easyadmin_ui_")
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
    _filter(page, name)
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
    _filter(page, name)
    assert page.locator(ROOT + " .ea-object").count() == 1
    assert _object(page, "search", name).count() == 1
    _filter(page, "no_such_object_anywhere")
    text = page.locator(ROOT).inner_text()
    assert 'No objects match the filter "no_such_object_anywhere"' in text
    # No app has a matching object, so the switch hides them all: the page says
    # that, not that the account sees no apps.
    assert page.locator(ROOT + " .ea-app").count() == 0
    assert "No apps are visible to your account" not in text
    assert 'No app has objects matching "no_such_object_anywhere"' in text
    # Unticked, every app stays on show, as a place to drop an object.
    _show_empty_apps(page)
    assert page.locator(ROOT + ' .ea-app[data-app="launcher"]').count() == 1


def test_apps_with_no_matching_objects_hide_with_or_without_a_filter(open_view, macro):
    """"Hide apps with no matching objects" hides boxes that list nothing, whether or not text is typed."""
    name = macro()
    page = _open(open_view)
    tick = page.locator(HIDE)
    assert tick.is_checked()
    assert "Hide apps with no matching objects" in page.locator(ROOT + " .ea-toolbar").inner_text()
    assert 'drag objects over the "Hidden apps" area' in page.locator(ROOT + ' label.ea-check:has(input[data-fid="hide-empty"])').get_attribute("title")
    # Nothing typed: an app that holds no object is hidden all the same, and one that holds some shows.
    empty = _an_empty_app(page)
    launcher = page.locator(ROOT + ' .ea-app[data-app="%s"]' % empty)
    assert launcher.count() == 0
    assert page.locator(ROOT + ' .ea-app[data-app="search"]').count() == 1
    assert "with no matching objects" in page.locator(ROOT + " .ea-summary").inner_text()
    _filter(page, name)
    assert launcher.count() == 0
    assert page.locator(ROOT + ' .ea-app[data-app="search"]').count() == 1
    summary = page.locator(ROOT + " .ea-summary").inner_text()
    assert "with no matching objects" in summary and 'untick "Hide apps with no matching objects"' in summary
    tick.uncheck()
    assert launcher.count() == 1
    tick.check()
    assert launcher.count() == 0
    _filter(page, "")   # clearing the text: still hidden, as the switch is ticked
    assert launcher.count() == 0


def test_hide_switch_is_not_kept_across_page_loads(open_view):
    """Like the built-in toggle, the switch starts ticked on every visit."""
    page = _open(open_view)
    page.locator(HIDE).uncheck()
    assert not page.locator(HIDE).is_checked()
    page.reload()
    page.wait_for_selector(READY)
    assert page.locator(HIDE).is_checked()


def test_dragging_onto_a_hidden_app_stages_a_move(open_view, macro, sandbox_client, shot):
    """Hidden apps are listed in an area that appears during a drag; dropping on one does what its box does."""
    name = macro()
    page = _open(open_view)
    _room_to_drag(page)
    _filter(page, name)
    assert page.locator(ROOT + ' .ea-app[data-app="launcher"]').count() == 0
    assert page.locator(HIDDEN_AREA).count() == 0   # only while dragging
    row = _object(page, "search", name)
    _begin_drag(page, row)
    _open_hidden_area(page)
    _hover_hidden_app(page, "launcher")
    listed = page.locator(ROOT + " .ea-hidden-target").evaluate_all(
        "nodes => nodes.map(n => n.getAttribute('data-app'))")
    assert "launcher" in listed
    assert "search" not in listed   # on show, so a box of its own
    assert page.locator(HIDDEN_AREA + " .ea-hidden-hint").inner_text() == "Hold here, then drop on a hidden app."
    assert page.locator(HIDDEN_AREA + " .ea-hidden-title").inner_text().startswith("Hidden apps (")
    shot(page, "app_management_hidden_apps_area")   # taken mid-drag, for the UX review
    # The same state in the other theme: the area only exists mid-drag, so flip the class the page sets itself.
    page.evaluate("root => root.classList.toggle('ea-dark')", page.locator(ROOT).element_handle())
    shot(page, "app_management_hidden_apps_area_other_theme")
    page.mouse.up()
    assert 'Staged a move of 1 object to "Home" (launcher)' in page.locator(ROOT + " .ea-messages").inner_text()
    moved = _object(page, "launcher", name)   # the app now has a staged change, so its box shows
    assert moved.count() == 1 and "moving from search" in moved.inner_text()
    assert page.locator(HIDDEN_AREA).count() == 0   # gone with the drag
    assert page.locator(ROOT + " .ea-apply").inner_text() == "Apply changes to 1 object"
    assert _acl(sandbox_client, "search", name)["app"] == "search"   # nothing written until Apply


def test_dragging_onto_a_hidden_app_works_with_no_filter(open_view, macro, sandbox_client):
    """The owner's case: no filter applied, an empty app is hidden, and the area still reaches it."""
    name = macro()
    page = _open(open_view)
    _room_to_drag(page)
    empty = _an_empty_app(page)
    assert page.locator(ROOT + ' .ea-app[data-app="%s"]' % empty).count() == 0
    _drag_to_hidden_app(page, _object(page, "search", name), empty)
    assert 'Staged a move of 1 object to' in page.locator(ROOT + " .ea-messages").inner_text()
    # The app's label, with its id in brackets when the two differ.
    assert empty in page.locator(ROOT + " .ea-messages").inner_text()
    assert _object(page, empty, name).count() == 1
    assert _acl(sandbox_client, "search", name)["app"] == "search"   # nothing written until Apply


def test_dropping_a_default_object_on_a_hidden_app_stages_a_copy(open_view, sandbox_client, cleanup_launcher_macros):
    """Through the area, as on a box, an object in a default folder is copied rather than moved."""
    name = _shipped_search_macro(sandbox_client)
    cleanup_launcher_macros.append(name)
    page = _open(open_view)
    _room_to_drag(page)
    _filter(page, name)
    assert page.locator(ROOT + ' .ea-app[data-app="launcher"]').count() == 0
    _drag_to_hidden_app(page, _object(page, "search", name), "launcher")
    text = page.locator(ROOT + " .ea-messages").inner_text()
    assert 'Staged a copy of 1 object into "Home" (launcher).' in text
    ghost = page.locator(ROOT + ' .ea-app[data-app="launcher"] .ea-ghost:has(.ea-object-name:text-is("%s"))' % name)
    assert ghost.count() == 1 and "copy from search" in ghost.inner_text()


def test_a_cancelled_drag_removes_the_hidden_apps_area(open_view, macro):
    """Letting go over empty space ends the drag: the area goes and nothing is staged."""
    name = macro()
    page = _open(open_view)
    _room_to_drag(page)
    _filter(page, name)
    _begin_drag(page, _object(page, "search", name))
    _open_hidden_area(page)
    _hover_hidden_app(page, "launcher")
    page.mouse.move(1400, 300, steps=5)   # past the last box
    page.mouse.up()
    page.locator(HIDDEN_AREA).wait_for(state="detached")
    assert page.locator(ROOT + " .ea-apply").is_disabled()
    assert page.locator(ROOT + ' .ea-app[data-app="launcher"]').count() == 0


def test_no_hidden_apps_area_when_nothing_is_hidden(open_view, macro):
    """The area appears only when the switch has hidden an app: not once it is unticked."""
    name = macro()
    page = _open(open_view)
    _room_to_drag(page)
    _filter(page, name)
    _show_empty_apps(page)
    _begin_drag(page, _object(page, "search", name))
    page.wait_for_timeout(500)
    assert page.locator(HIDDEN_AREA).count() == 0
    page.mouse.up()


def test_no_app_has_an_object_to_list_says_so(open_view):
    """With no object type chosen, the switch hides every box and the page says why, not that no app is visible."""
    page = _open(open_view)
    page.locator(ROOT + ' button[data-fid="types-button"]').click()
    page.locator(ROOT + ' button[data-fid="types-2"]').click()   # None
    page.keyboard.press("Escape")
    assert page.locator(ROOT + " .ea-app").count() == 0
    assert "No app has any object to list." in page.locator(ROOT + " .ea-empty").inner_text()


def test_builtin_apps_are_reached_through_their_own_area_while_dragging(open_view, macro, sandbox_client, shot):
    """Hidden built-in apps get a "Built-in apps" area of their own, apart from "Hidden apps"."""
    name = macro()
    page = _open(open_view, builtin=False)
    _room_to_drag(page)
    assert page.locator(ROOT + ' .ea-app[data-app="launcher"]').count() == 0
    assert "Built-in apps" in page.locator(ROOT + ' label.ea-check:has(input[data-fid="builtin"])').get_attribute("title")
    row = _object(page, "search", name)
    _begin_drag(page, row)
    _open_hidden_area(page, BUILTIN_AREA)
    _hover_hidden_app(page, "launcher")
    area = page.locator(BUILTIN_AREA)
    assert area.locator(".ea-hidden-title").inner_text().startswith("Built-in apps (")
    assert area.locator(".ea-hidden-hint").inner_text() == "Hold here, then drop on a built-in app."
    listed = area.locator(".ea-hidden-target").evaluate_all("nodes => nodes.map(n => n.getAttribute('data-app'))")
    assert "launcher" in listed and "search" not in listed
    # Each area lists only its own apps: no built-in app in "Hidden apps" while the tick box hides it.
    other = page.locator(HIDDEN_AREA + " .ea-hidden-target")
    assert "launcher" not in (other.evaluate_all("nodes => nodes.map(n => n.getAttribute('data-app'))") if other.count() else [])
    shot(page, "app_management_builtin_apps_area")   # mid-drag, for the UX review
    page.evaluate("root => root.classList.toggle('ea-dark')", page.locator(ROOT).element_handle())
    shot(page, "app_management_builtin_apps_area_other_theme")
    page.mouse.up()
    assert 'Staged a move of 1 object to "Home" (launcher)' in page.locator(ROOT + " .ea-messages").inner_text()
    assert _object(page, "launcher", name).count() == 1   # staged, so the box shows
    assert page.locator(BUILTIN_AREA).count() == 0   # gone with the drag
    assert _acl(sandbox_client, "search", name)["app"] == "search"   # nothing written until Apply


def test_no_builtin_area_when_built_in_apps_are_shown(open_view, macro):
    """Ticking "Show Splunk's built-in apps" puts the boxes on show, so there is no area for them."""
    name = macro()
    page = _open(open_view)
    _room_to_drag(page)
    _begin_drag(page, _object(page, "search", name))
    page.wait_for_timeout(500)
    assert page.locator(BUILTIN_AREA).count() == 0
    page.mouse.up()


def test_app_boxes_are_wide_enough_for_long_names(open_view):
    """Boxes are at least 460px wide where the window has room, so names wrap less."""
    page = _open(open_view)
    page.set_viewport_size({"width": 1800, "height": 900})
    widths = page.locator(ROOT + " .ea-app").evaluate_all("nodes => nodes.map(n => n.getBoundingClientRect().width)")
    assert widths and min(widths) >= 459


def test_staged_and_new_apps_show_whatever_the_switch_says(open_view, macro, cleanup_launcher_macros):
    """A box with staged changes and a pending new app stay on show while the switch hides the rest."""
    name = macro()
    cleanup_launcher_macros.append(name)
    page = _open(open_view)
    _stage_new_app(page)
    _filter(page, name)
    _object(page, "search", name).locator(".ea-select").check()
    page.locator(ROOT + " .ea-move-target").select_option("launcher")
    page.locator(ROOT + ' button[data-fid="copy-selected"]').click()
    _filter(page, "no_such_object_anywhere")
    assert page.locator(ROOT + ' .ea-app[data-app="%s"]' % NEW_APP).count() == 1
    assert page.locator(ROOT + ' .ea-app[data-app="launcher"]').count() == 1
    assert page.locator(ROOT + ' .ea-app[data-app="easyadmin"]').count() == 0   # nothing staged: hidden


def test_drag_to_another_app_stages_a_move_and_apply_makes_it(open_view, macro, sandbox_client, shot):
    """Dragging an object onto another app's box stages a move, marked on the object; Apply moves it."""
    name = macro()
    page = _open(open_view)
    _show_empty_apps(page)   # the switch would hide launcher's box while filtering
    _room_to_drag(page)
    _filter(page, name)
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
    # Until Apply the object is still listed where it is: struck through.
    assert _moving_out(page, "search", name).count() == 1
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
    # Moved: nothing is left in the old app.
    assert _object(page, "search", name).count() == 0


def test_select_and_bulk_move_with_the_keyboard_controls(open_view, macro, sandbox_client):
    """Ticking objects and choosing an app in "Move to app" stages a move without dragging."""
    first, second = macro(), macro()
    page = _open(open_view)
    _filter(page, "easyadmin_ui_")
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
    _filter(page, name)
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
    _filter(page, name)
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
    # A view is not a conf stanza: it never names a local file.
    assert "local changes" not in row.locator(".ea-locked").get_attribute("title")


def test_a_locked_object_with_local_changes_names_the_file_that_holds_them(open_view, sandbox_client):
    """No delete is offered (Splunk refuses it and nothing removes only the local layer): the page says what to edit."""
    name = "instrumentation.anonymized.eventsByTime"
    obj = next((o for o in sandbox_client.request("GET", "/services/easyadmin/apps")["objects"]
                if (o["type"], o["app"], o["name"]) == ("savedsearch", "splunk_instrumentation", name)), None)
    if obj is None or not obj.get("local_file"):
        pytest.skip("the report is not shipped here, or has no local layer (the live test makes one)")
    page = _open(open_view)
    _filter(page, name)
    row = _object(page, "splunk_instrumentation", name)
    lock = row.locator(".ea-locked")
    assert "It has local changes" in lock.get_attribute("title")
    assert "etc/apps/splunk_instrumentation/local/savedsearches.conf" in lock.get_attribute("title")
    row.locator(".ea-object-name").click()
    delete = page.locator(ROOT + ' .ea-panel button[data-fid="panel-delete"]')
    assert delete.is_disabled()
    assert "etc/apps/splunk_instrumentation/local/savedsearches.conf" in delete.get_attribute("title")
    assert "It has local changes" in delete.get_attribute("title")


def test_the_legend_says_how_local_changes_to_a_locked_object_go(open_view):
    """Visible text, since a badge's title is out of reach of the keyboard."""
    page = _open(open_view, builtin=False)
    legend = page.locator(ROOT + " .ea-legend").inner_text()
    assert "Local changes to such an object can be removed only by editing its app's local file." in legend


def test_leaving_with_staged_changes_asks_first(open_view, macro):
    """The browser asks before a page with staged changes is left."""
    name = macro()
    page = _open(open_view)
    _filter(page, name)
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
    _filter(page, "easyadmin_ui_")
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
    _show_empty_apps(page)   # the switch would hide launcher's box while filtering
    _room_to_drag(page)
    _filter(page, name)
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
    _filter(page, name)
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
    _filter(page, name)
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
    _filter(page, name)
    _object(page, "search", name).locator(".ea-select").check()
    page.locator(ROOT + " .ea-move-target").select_option("launcher")
    page.locator(ROOT + ' button[data-fid="copy-selected"]').click()
    assert "already has an object of the same type and name" in page.locator(ROOT + " .ea-messages").inner_text()
    assert page.locator(ROOT + " .ea-apply").is_disabled()


def test_each_staged_change_can_be_discarded_on_its_own(open_view, macro, shot):
    """The x on a staged-change badge discards that change only; the object's other changes stay."""
    name = macro()
    page = _open(open_view)
    _filter(page, name)
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


def _stage_move_to_launcher(page, name):
    _filter(page, name)
    _object(page, "search", name).locator(".ea-select").check()
    page.locator(ROOT + " .ea-move-target").select_option("launcher")
    page.locator(ROOT + ' button[data-fid="move-selected"]').click()


def test_a_staged_move_stays_in_its_old_app_struck_through(open_view, macro, shot):
    """An object with a staged move is still listed in the app it is leaving, struck through
    and labelled, as a deletion is; the box it is going to shows the real row, not struck."""
    name = macro()
    page = _open(open_view)
    _stage_move_to_launcher(page, name)

    origin = _moving_out(page, "search", name)
    assert origin.count() == 1
    assert _object(page, "search", name).count() == 1   # the struck row is the only one there
    assert "moving to launcher" in origin.inner_text()
    assert origin.locator(".ea-select").count() == 0
    assert origin.get_attribute("draggable") is None
    assert "ea-changed" in origin.get_attribute("class")
    # The label's meaning is carried by its style too (lesson ux-label-meaning-needs-matching-style).
    assert _struck(origin)

    real = _object(page, "launcher", name)
    assert real.count() == 1 and "moving from search" in real.inner_text()
    assert not _struck(real)
    assert "ea-moving-out" not in real.get_attribute("class")
    # Counted once: in the box the object is going to.
    assert "and 1 object (" in page.locator(ROOT + " .ea-summary").inner_text()

    # The name opens the object's panel, as a staged copy's name does.
    origin.locator(".ea-object-name").click()
    page.locator(ROOT + " .ea-panel .ea-settings").wait_for()
    page.keyboard.press("Escape")
    shot(page, "app_management_staged_move_origin")


def test_the_struck_row_discards_the_move(open_view, macro):
    """The x on the struck row drops the move only: the object is back in its app, other staged
    changes are kept, and the keyboard goes to the object's name."""
    name = macro()
    page = _open(open_view)
    _stage_move_to_launcher(page, name)
    # A second staged change on the same object, to prove it is kept.
    _object(page, "launcher", name).locator(".ea-object-name").click()
    page.locator(ROOT + " .ea-panel #ea-sharing").select_option("global")
    page.keyboard.press("Escape")

    cross = _moving_out(page, "search", name).locator('.ea-discard-one[data-kind="move"]')
    assert cross.get_attribute("aria-label").startswith("Discard staged change: moving to launcher")
    cross.click()
    assert _moving_out(page, "search", name).count() == 0
    back = _object(page, "search", name)
    assert back.count() == 1 and _object(page, "launcher", name).count() == 0
    assert "moving from" not in back.inner_text()
    assert "permissions changed" in back.inner_text()
    assert not _struck(back)
    assert page.evaluate("document.activeElement.getAttribute('data-fid')") == "open:" + \
        back.get_attribute("data-key")
    back.locator('.ea-discard-one[data-kind="acl"]').click()
    assert page.locator(ROOT + " .ea-apply").is_disabled()


def test_select_all_skips_the_struck_row(open_view, macro):
    """Ticking an app's select-all does not select an object that is leaving it."""
    moving, staying = macro(), macro()
    page = _open(open_view)
    _filter(page, "easyadmin_ui_")
    _object(page, "search", moving).locator(".ea-select").check()
    page.locator(ROOT + " .ea-move-target").select_option("launcher")
    page.locator(ROOT + ' button[data-fid="move-selected"]').click()
    page.locator(ROOT + ' button[data-fid="clear-selection"]').click()
    assert _moving_out(page, "search", moving).count() == 1
    page.locator(ROOT + ' .ea-app[data-app="search"] .ea-select-app').check()
    assert _object(page, "search", staying).locator(".ea-select").is_checked()
    assert "1 object selected" in page.locator(ROOT + " .ea-selection").inner_text()
    assert _moving_out(page, "search", moving).locator(".ea-select").count() == 0


def test_a_staged_copy_can_be_discarded_from_its_dashed_row(open_view, macro):
    """The x on a staged copy's row in the target app drops the copy and nothing else."""
    name = macro()
    page = _open(open_view)
    _filter(page, name)
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
    _filter(page, name)
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
    _filter(page, shipped)
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
    _app_filter(page, "zzz-no-such-app")
    assert page.locator(ROOT + ' .ea-app[data-app="%s"]' % NEW_APP).count() == 1
    _app_filter(page, "")
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
    _filter(page, name)
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
    _filter(page, name)
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
    _filter(page, name)
    assert box.locator(".ea-ghost").count() == 1
    assert "0 matches, 1 staged" in meta.inner_text()
    assert box.locator(".ea-hidden-staged").inner_text() == "%s hidden by the filters." % (
        "1 staged copy is" if total - 1 == 1 else "%d staged copies are" % (total - 1))
    # The name filter hides every other copy, so this shot always shows the note.
    shot(page, "app_management_clone_hidden_note")

    seen = _accept_dialogs(page)
    box.locator(".ea-discard-app").click()
    assert len(seen) == 1
    assert page.locator(ROOT + " .ea-apply").is_disabled()


def test_a_box_with_only_hidden_staged_copies_stays_on_show(open_view, macro, cleanup_launcher_macros):
    """The app filter does not hide a box that has staged copies the Types menu keeps out of its list."""
    name = macro()
    cleanup_launcher_macros.append(name)
    page = _open(open_view)
    _filter(page, name)
    _object(page, "search", name).locator(".ea-select").check()
    page.locator(ROOT + " .ea-move-target").select_option("launcher")
    page.locator(ROOT + ' button[data-fid="copy-selected"]').click()
    assert "copying to launcher" in _object(page, "search", name).inner_text()
    _filter(page, "")

    page.locator(ROOT + ' button[data-fid="types-button"]').click()
    page.locator(ROOT + ' input[data-fid="type:macro"]').uncheck()
    page.keyboard.press("Escape")
    _app_filter(page, "search")
    box = page.locator(ROOT + ' .ea-app[data-app="launcher"]')
    assert box.count() == 1
    assert box.locator(".ea-hidden-staged").inner_text() == "1 staged copy is hidden by the filters."
    assert ", 1 staged" not in box.locator(".ea-app-meta").inner_text()
    assert box.locator(".ea-ghost").count() == 0

    seen = _accept_dialogs(page)
    page.locator(ROOT + ' button[data-fid="discard"]').click()
    assert len(seen) == 1
    assert page.locator(ROOT + " .ea-apply").is_disabled()


def _stage(page, name, button, target=None):
    """Select the object called ``name`` in search, optionally pick a target app, click ``button``."""
    _filter(page, name)
    _object(page, "search", name).locator(".ea-select").check()
    if target:
        page.locator(ROOT + " .ea-move-target").select_option(target)
    page.locator(ROOT + ' button[data-fid="%s"]' % button).click()
    page.locator(ROOT + ' button[data-fid="clear-selection"]').click()


def _macros_listed(page, shown):
    """Tick or untick "macro" in the Types menu, so the staged macros are shown or hidden."""
    page.locator(ROOT + ' button[data-fid="types-button"]').click()
    box = page.locator(ROOT + ' input[data-fid="type:macro"]')
    box.check() if shown else box.uncheck()
    page.keyboard.press("Escape")


def test_hidden_staged_moves_and_deletions_are_counted_too(open_view, macro, cleanup_launcher_macros):
    """A move is counted in the box it goes to, a deletion in the box the object is in, when the
    Types menu keeps the object out of the list; both are said alongside a hidden copy."""
    moved, deleted, copied = macro(), macro(), macro()
    cleanup_launcher_macros.extend([moved, copied])
    page = _open(open_view)

    _stage(page, moved, "move-selected", "launcher")
    _stage(page, deleted, "delete-selected")
    assert "will be deleted" in _object(page, "search", deleted).inner_text()
    _filter(page, "")
    assert "moving from search" in page.locator(ROOT + " .ea-app[data-app='launcher']").inner_text()

    _macros_listed(page, False)
    launcher = page.locator(ROOT + ' .ea-app[data-app="launcher"]')
    search = page.locator(ROOT + ' .ea-app[data-app="search"]')
    assert launcher.locator(".ea-hidden-staged").inner_text() == "1 staged move is hidden by the filters."
    # The move is counted where it goes and where it leaves, as the deletion is where it is.
    assert search.locator(".ea-hidden-staged").inner_text() == \
        "1 staged move away and 1 staged deletion are hidden by the filters."
    assert moved not in launcher.inner_text()
    assert moved not in search.inner_text()

    # A copy into the same box is said in the same line.
    _macros_listed(page, True)
    _stage(page, copied, "copy-selected", "launcher")
    _filter(page, "")
    _macros_listed(page, False)
    assert launcher.locator(".ea-hidden-staged").inner_text() == \
        "1 staged copy and 1 staged move are hidden by the filters."
    assert search.locator(".ea-hidden-staged").inner_text() == \
        "1 staged move away and 1 staged deletion are hidden by the filters."

    seen = _accept_dialogs(page)
    page.locator(ROOT + ' button[data-fid="discard"]').click()
    assert len(seen) == 1
    assert page.locator(ROOT + " .ea-apply").is_disabled()
    assert page.locator(ROOT + " .ea-hidden-staged").count() == 0


def test_hidden_staged_moves_away_are_counted_alone_and_in_the_plural(open_view, macro, cleanup_launcher_macros):
    """The note names a hidden move away on its own, singular and plural, with the verb agreeing;
    the box the objects go to counts the same moves as "moves" (exact text: the plural contains
    the singular's words)."""
    first, second = macro(), macro()
    cleanup_launcher_macros.extend([first, second])
    page = _open(open_view)
    launcher = page.locator(ROOT + ' .ea-app[data-app="launcher"]')
    search = page.locator(ROOT + ' .ea-app[data-app="search"]')

    _stage(page, first, "move-selected", "launcher")
    _filter(page, "")
    _macros_listed(page, False)
    assert search.locator(".ea-hidden-staged").inner_text() == "1 staged move away is hidden by the filters."
    assert launcher.locator(".ea-hidden-staged").inner_text() == "1 staged move is hidden by the filters."

    _macros_listed(page, True)
    _stage(page, second, "move-selected", "launcher")
    _filter(page, "")
    _macros_listed(page, False)
    assert search.locator(".ea-hidden-staged").inner_text() == "2 staged moves away are hidden by the filters."
    assert launcher.locator(".ea-hidden-staged").inner_text() == "2 staged moves are hidden by the filters."

    seen = _accept_dialogs(page)
    page.locator(ROOT + ' button[data-fid="discard"]').click()
    assert len(seen) == 1
    assert page.locator(ROOT + " .ea-apply").is_disabled()
    assert page.locator(ROOT + " .ea-hidden-staged").count() == 0


def _focused(page):
    """The focused element's data-fid and the app box it is in."""
    return page.evaluate("""() => { const a = document.activeElement;
        const box = a && a.closest ? a.closest('.ea-app') : null;
        return [a && a.getAttribute ? a.getAttribute('data-fid') : null,
                box ? box.getAttribute('data-app') : null]; }""")


def test_the_struck_row_keeps_the_keyboard_when_the_filter_redraws(open_view, macro):
    """The struck row's name has its own focus id (moving:<key>), distinct from the real row's in
    the box the object goes to; focus on it comes back to it after the filter redraws the grid
    and after the panel it opened is closed with Escape."""
    name = macro()
    page = _open(open_view)
    _stage_move_to_launcher(page, name)
    origin = _moving_out(page, "search", name)
    fid = "moving:" + origin.get_attribute("data-key")
    narrower = name[:-1]

    # Typing the filter and moving focus in one call, so the pause cannot run out between them;
    # the keys hold characters a raw attribute selector may not accept, hence the equality test.
    page.evaluate("""([root, text, fid]) => {
        const input = document.querySelector(root + ' .ea-filter');
        input.value = text;
        input.dispatchEvent(new Event('input', {bubbles: true}));
        const button = Array.from(document.querySelectorAll(root + ' [data-fid]'))
            .find(b => b.getAttribute('data-fid') === fid);
        button.focus();
    }""", [ROOT, narrower, fid])
    _wait_drawn(page, "data-filter", narrower)
    assert _focused(page) == [fid, "search"]

    # A second redraw by another path: the panel opened from the struck name returns to it.
    origin = _moving_out(page, "search", name)
    origin.locator(".ea-object-name").click()
    page.locator(ROOT + " .ea-panel .ea-settings").wait_for()
    page.keyboard.press("Escape")
    page.wait_for_function(
        "fid => { const a = document.activeElement; return !!a && a.getAttribute('data-fid') === fid; }",
        arg=fid)
    assert _focused(page) == [fid, "search"]

    seen = _accept_dialogs(page)
    page.locator(ROOT + ' button[data-fid="discard"]').click()
    assert len(seen) == 1
    assert page.locator(ROOT + " .ea-apply").is_disabled()


# ------------------------------------------- the panel and the page buttons

TOOLBAR_BUTTONS = ("new-app", "reload", "discard", "apply")
PANEL = ROOT + " .ea-panel"


def _uncovered(page, fid):
    """'ok' when the toolbar button is inside the window and a click at its centre would hit it."""
    return page.evaluate("""([root, fid]) => {
        const b = document.querySelector(root + ' button[data-fid="' + fid + '"]');
        if (!b) { return 'missing'; }
        // Opening an object scrolls the page to its row; what matters is whether
        // the panel covers the button, not where the page happens to be scrolled.
        b.scrollIntoView({ block: 'nearest' });
        const r = b.getBoundingClientRect();
        if (r.left < 0 || r.top < 0 || r.right > window.innerWidth || r.bottom > window.innerHeight) {
            return 'outside the window';
        }
        const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
        return hit && (hit === b || b.contains(hit)) ? 'ok' : 'covered by ' + (hit ? hit.className : 'nothing');
    }""", [ROOT, fid])


def _open_object_panel(page, name):
    _filter(page, name)
    _object(page, "search", name).locator(".ea-object-name").click()
    page.locator(PANEL + " .ea-settings").first.wait_for()
    return page.locator(PANEL)


def _idle(page):
    page.locator(ROOT + " .ea-busy").wait_for(state="detached")
    page.wait_for_selector(READY)


class _Dialogs:
    """Records every dialog and answers it with ``accept`` (change it between clicks)."""

    def __init__(self, page, accept=True):
        self.accept = accept
        self.seen = []
        page.on("dialog", self._answer)

    def _answer(self, dialog):
        self.seen.append(dialog.message)
        if self.accept:
            dialog.accept()
        else:
            dialog.dismiss()


def test_toolbar_buttons_stay_uncovered_while_a_panel_is_open(open_view, macro, shot):
    """Object details, Edit permissions, New app and Clone leave New app, Reload, Discard and Apply in view."""
    name = macro()
    page = _open(open_view)
    _filter(page, name)
    _object(page, "search", name).locator(".ea-select").check()
    page.locator(ROOT + ' button[data-fid="delete-selected"]').click()   # a staged change enables Discard and Apply
    assert page.locator(ROOT + " .ea-apply").is_enabled()
    opened = {
        "details": lambda: _object(page, "search", name).locator(".ea-object-name").click(),
        "permissions": lambda: page.locator(ROOT + ' button[data-fid="bulk-acl"]').click(),
        "new app": lambda: page.locator(ROOT + ' button[data-fid="new-app"]').click(),
        "clone": lambda: page.locator(ROOT + ' button[data-fid="clone:search"]').click(),
    }
    for label, open_it in opened.items():
        open_it()
        page.locator(PANEL).wait_for()
        for fid in TOOLBAR_BUTTONS:
            assert _uncovered(page, fid) == "ok", (label, fid, _uncovered(page, fid))
        if label == "details":
            shot(page, "app_management_panel_toolbar")
        page.locator(PANEL + ' button[data-fid="panel-close"]').click()
        assert page.locator(PANEL).count() == 0


def test_reload_with_an_untouched_panel_closes_it_without_asking(open_view, macro):
    name = macro()
    page = _open(open_view)
    _open_object_panel(page, name)
    dialogs = _Dialogs(page)
    page.locator(ROOT + ' button[data-fid="reload"]').click(timeout=5000)
    assert page.locator(PANEL).count() == 0
    _idle(page)
    assert dialogs.seen == []


def test_apply_with_a_panel_open_applies_and_closes_it(open_view, macro, sandbox_client):
    name = macro()
    page = _open(open_view)
    panel = _open_object_panel(page, name)
    panel.locator('button[data-fid="setting-edit:definition"]').click()
    panel.locator("#ea-edit-value").fill("index=_audit | head 1")
    panel.locator('button[data-fid="setting-stage:definition"]').click()
    assert page.locator(PANEL).count() == 1   # still open: nobody closed it
    dialogs = _Dialogs(page)
    page.locator(ROOT + " .ea-apply").click(timeout=5000)
    page.wait_for_selector(ROOT + " .ea-message.ea-success, " + ROOT + " .ea-message.ea-error")
    _idle(page)
    assert len(dialogs.seen) == 1 and "Apply changes to" in dialogs.seen[0], dialogs.seen
    assert page.locator(PANEL).count() == 0
    content = sandbox_client.request("GET", "/servicesNS/nobody/search/admin/macros/%s" % q(name))["entry"][0]["content"]
    assert content["definition"] == "index=_audit | head 1"


def test_an_unstaged_setting_edit_is_asked_about_and_kept_if_declined(open_view, macro):
    name = macro()
    page = _open(open_view)
    panel = _open_object_panel(page, name)
    panel.locator('button[data-fid="setting-edit:definition"]').click()
    panel.locator("#ea-edit-value").fill("index=_audit")
    dialogs = _Dialogs(page, accept=False)
    page.locator(ROOT + ' button[data-fid="reload"]').click(timeout=5000)
    assert len(dialogs.seen) == 1 and "Discard what you typed" in dialogs.seen[0]
    assert page.locator(PANEL).count() == 1
    assert page.locator("#ea-edit-value").input_value() == "index=_audit"
    assert page.locator(ROOT + " .ea-busy").count() == 0
    dialogs.accept = True
    page.locator(ROOT + ' button[data-fid="reload"]').click(timeout=5000)
    assert page.locator(PANEL).count() == 0
    _idle(page)
    panel = _open_object_panel(page, name)
    assert panel.locator("#ea-edit-value").count() == 0   # the editor did not come back


def test_a_half_typed_new_setting_counts_as_typing(open_view, macro):
    name = macro()
    page = _open(open_view)
    _filter(page, name)
    _object(page, "search", name).locator(".ea-select").check()
    page.locator(ROOT + ' button[data-fid="delete-selected"]').click()   # one change staged elsewhere
    panel = _open_object_panel(page, name)
    panel.locator("#ea-add-name").fill("errormsg")
    dialogs = _Dialogs(page)
    page.locator(ROOT + ' button[data-fid="discard"]').click(timeout=5000)
    assert len(dialogs.seen) == 2, dialogs.seen
    assert "Discard what you typed" in dialogs.seen[0] and "Discard the staged changes" in dialogs.seen[1]
    assert page.locator(PANEL).count() == 0
    assert page.locator(ROOT + " .ea-apply").is_disabled()
    panel = _open_object_panel(page, name)
    assert panel.locator("#ea-add-name").input_value() == ""


def test_new_app_with_a_half_filled_form_asks_then_opens_a_fresh_form(open_view):
    page = _open(open_view)
    page.locator(ROOT + ' button[data-fid="new-app"]').click()
    _fill(page, "name", NEW_APP)
    dialogs = _Dialogs(page, accept=False)
    page.locator(ROOT + ' button[data-fid="new-app"]').click(timeout=5000)
    assert len(dialogs.seen) == 1 and "Discard what you typed" in dialogs.seen[0]
    assert page.locator(PANEL + ' input[data-fid="newapp-name"]').input_value() == NEW_APP
    dialogs.accept = True
    page.locator(ROOT + ' button[data-fid="new-app"]').click(timeout=5000)
    assert page.locator(PANEL + ' input[data-fid="newapp-name"]').input_value() == ""
    assert page.locator(PANEL + " #ea-panel-title").inner_text() == "New app"


def test_untouched_clone_form_and_bulk_choices(open_view, macro):
    name = macro()
    page = _open(open_view)
    dialogs = _Dialogs(page)
    page.locator(ROOT + ' button[data-fid="clone:search"]').click()
    assert page.locator(PANEL + ' input[data-fid="newapp-name"]').input_value() == "search_copy"
    page.locator(ROOT + ' button[data-fid="reload"]').click(timeout=5000)   # pre-filled values are not typing
    assert dialogs.seen == [] and page.locator(PANEL).count() == 0
    _idle(page)
    _filter(page, name)
    _object(page, "search", name).locator(".ea-select").check()
    page.locator(ROOT + ' button[data-fid="bulk-acl"]').click()
    page.locator(PANEL + " #ea-sharing").select_option("global")
    page.locator(ROOT + ' button[data-fid="reload"]').click(timeout=5000)
    assert len(dialogs.seen) == 1 and "Discard what you typed" in dialogs.seen[0]
    assert page.locator(PANEL).count() == 0
