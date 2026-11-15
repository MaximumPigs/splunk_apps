"""UI tests for editing the settings of a knowledge object in the App management panel.

One test per control (the filter, Copy, Show default value, Edit, the staged
edit and its discard, Add a setting, Apply). Each works on a macro it creates
in the search app (``easyadmin_ui_*``, removed by the ``macro`` fixture), except
the default-value test, which needs an object that ships with a default.
"""

import urllib.parse

import pytest
from playwright.sync_api import expect

from test_easyadmin_apps_ui import (APP, READY, ROOT, VIEW, _apply, _object, _open,  # noqa: F401
                                    macro, q)

ENDPOINT = "/services/easyadmin/apps"
PANEL = ROOT + " .ea-panel"


def _open_panel(page, name, app="search"):
    page.locator(ROOT + " .ea-filter").fill(name)
    _object(page, app, name).locator(".ea-object-name").click()
    page.locator(PANEL + " .ea-settings").first.wait_for()
    return page.locator(PANEL)


def _setting(panel, name):
    """The dd of the setting called exactly ``name`` (dt and dd are siblings)."""
    return panel.locator('.ea-settings dt:has(.ea-setting-name:text-is("%s")) + dd' % name).first


def _dt(panel, name):
    return panel.locator('.ea-settings dt:has(.ea-setting-name:text-is("%s"))' % name).first


def _macro_content(client, name):
    return client.request("GET", "/servicesNS/nobody/search/admin/macros/%s" % q(name))["entry"][0]["content"]


def test_filter_with_text_shows_inherited_settings_too(open_view, macro):
    """Empty filter: only what the object sets. With text: every matching setting, inherited ones labelled."""
    name = macro()
    page = _open(open_view)
    panel = _open_panel(page, name)
    assert panel.locator(".ea-settings dt").count() == 1
    assert panel.locator(".ea-setting-inherited").count() == 0
    panel.locator("#ea-setting-filter").fill("disabled")
    # splunkd reports disabled for every macro (observed); this one does not set it.
    assert _dt(panel, "disabled").count() == 1
    assert _dt(panel, "disabled").locator(".ea-setting-inherited").inner_text() == "inherited"
    assert "match" in panel.locator(".ea-setting-count").inner_text()
    panel.locator("#ea-setting-filter").fill("")
    assert panel.locator(".ea-setting-inherited").count() == 0
    # The value is searched as well as the name.
    panel.locator("#ea-setting-filter").fill("_internal")
    assert panel.locator(".ea-settings dt").count() == 1
    assert _dt(panel, "definition").count() == 1


def test_copy_button_shows_on_hover_and_focus_and_announces_copied(open_view, macro):
    """Copy is drawn when the code block is hovered or holds focus, and says "Copied"."""
    name = macro()
    page = _open(open_view)
    panel = _open_panel(page, name)
    block = _setting(panel, "definition").locator(".ea-setting-value")
    copy = block.locator(".ea-copy")
    opacity = lambda: float(copy.evaluate("n => getComputedStyle(n).opacity"))  # noqa: E731
    page.mouse.move(0, 0)
    assert opacity() == 0
    block.hover()
    assert opacity() == 1
    page.mouse.move(0, 0)
    assert opacity() == 0
    copy.focus()   # the keyboard reaches it while it is hidden, and it shows
    assert opacity() == 1
    assert copy.get_attribute("aria-label") == "Copy the value of definition"
    copy.click()
    expect(copy).to_have_text("Copied")   # the clipboard call is asynchronous
    page.wait_for_function("() => /Copied the value of definition/.test(document.querySelector('%s [role=status]').textContent)"
                           % ROOT)


def test_edit_is_staged_with_old_and_new_value_and_can_be_discarded(open_view, macro, sandbox_client, shot):
    """Edit then Stage shows the old value struck through and the new one, outlined like a staged change."""
    name = macro()
    page = _open(open_view)
    panel = _open_panel(page, name)
    panel.locator('button[data-fid="setting-edit:definition"]').click()
    # The edit box keeps the size of the value it replaces, so it does not shrink on Edit.
    size = "n => getComputedStyle(n).fontSize"
    assert panel.locator("#ea-edit-value").evaluate(size) == \
        panel.locator('label[for="ea-edit-value"]').evaluate(size)
    panel.locator("#ea-edit-value").fill("index=_audit")
    panel.locator('button[data-fid="setting-stage:definition"]').click()

    item = _setting(panel, "definition")
    assert "staged" in _dt(panel, "definition").inner_text()
    assert item.locator(".ea-setting-old code").inner_text() == "index=_internal"
    assert item.locator(".ea-setting-new code").inner_text() == "index=_audit"
    style = item.evaluate("n => { const s = getComputedStyle(n); return [s.borderTopStyle, s.borderTopWidth]; }")
    assert style == ["dashed", "2px"]   # the outline every staged change has
    struck = item.locator(".ea-setting-old code").evaluate("n => getComputedStyle(n).textDecorationLine")
    assert "line-through" in struck
    assert "Apply writes this to" in item.inner_text()
    assert "settings changed (1)" in _object(page, "search", name).inner_text()
    shot(page, "app_management_setting_staged")
    # Labels and code are the page's body size, not smaller: compared with the
    # note beside them (plain inherited text), so no pixel size is hard-coded.
    body = item.locator(".ea-setting-note").evaluate(size)
    assert item.locator(".ea-setting-label").first.evaluate(size) == body
    assert item.locator(".ea-setting-new .ea-code code").evaluate(size) == body
    # Nothing has been written.
    assert _macro_content(sandbox_client, name)["definition"] == "index=_internal"

    panel.locator('button[data-fid="setting-discard:definition"]').click()
    assert "settings changed" not in _object(page, "search", name).inner_text()
    assert _setting(panel, "definition").locator(".ea-setting-old").count() == 0
    assert page.locator(ROOT + " .ea-apply").is_disabled()


def test_the_x_on_the_objects_row_discards_staged_settings(open_view, macro):
    name = macro()
    page = _open(open_view)
    panel = _open_panel(page, name)
    panel.locator('button[data-fid="setting-edit:definition"]').click()
    panel.locator("#ea-edit-value").fill("index=_audit")
    panel.locator('button[data-fid="setting-stage:definition"]').click()
    _object(page, "search", name).locator('.ea-discard-one[data-kind="settings"]').click()
    assert "settings changed" not in _object(page, "search", name).inner_text()
    assert page.locator(ROOT + " .ea-apply").is_disabled()


def test_cancel_leaves_the_setting_alone(open_view, macro):
    name = macro()
    page = _open(open_view)
    panel = _open_panel(page, name)
    panel.locator('button[data-fid="setting-edit:definition"]').click()
    panel.locator("#ea-edit-value").fill("index=_audit")
    panel.locator('button[data-fid="setting-cancel:definition"]').click()
    assert panel.locator("#ea-edit-value").count() == 0
    assert _setting(panel, "definition").locator(".ea-setting-value code").inner_text() == "index=_internal"
    assert "settings changed" not in _object(page, "search", name).inner_text()


def test_add_a_setting_from_splunkds_list_then_apply_writes_it_locally(open_view, macro, sandbox_client, shot):
    """The name box offers what splunkd lists; an unlisted name is refused on the spot; Apply writes."""
    name = macro()
    page = _open(open_view)
    panel = _open_panel(page, name)
    options = panel.locator("#ea-add-names option").evaluate_all("nodes => nodes.map(n => n.value)")
    assert "errormsg" in options and "definition" not in options

    stage = panel.locator('button[data-fid="setting-add-stage"]')
    assert stage.is_disabled()
    panel.locator("#ea-add-name").fill("splktest_unlisted")
    assert "does not list" in panel.locator("#ea-add-problem").inner_text()
    assert stage.is_disabled() and panel.locator("#ea-add-name").get_attribute("aria-invalid") == "true"
    panel.locator("#ea-add-name").fill("errormsg")
    assert panel.locator("#ea-add-problem").inner_text() == "" and stage.is_enabled()
    panel.locator("#ea-add-value").fill("splktest message")
    stage.click()
    assert "new, staged" in _dt(panel, "errormsg").inner_text()
    assert _setting(panel, "errormsg").locator(".ea-setting-old").count() == 0   # it had no old value
    assert _setting(panel, "errormsg").locator(".ea-setting-new code").inner_text() == "splktest message"
    shot(page, "app_management_setting_added")

    page.locator(PANEL + ' button[data-fid="panel-close"]').click()   # the panel covers Apply
    prompt = _apply(page)
    assert "change settings of 1 object" in prompt
    assert _macro_content(sandbox_client, name)["errormsg"] == "splktest message"
    panel = _open_panel(page, name)
    assert _dt(panel, "errormsg").locator(".ea-setting-layer").inner_text() == "local"
    assert panel.locator(".ea-setting-staged").count() == 0


def test_an_edit_is_applied_and_shown_as_local(open_view, macro, sandbox_client):
    name = macro()
    page = _open(open_view)
    panel = _open_panel(page, name)
    panel.locator('button[data-fid="setting-edit:definition"]').click()
    panel.locator("#ea-edit-value").fill("index=_audit | head 1")
    panel.locator('button[data-fid="setting-stage:definition"]').click()
    page.locator(PANEL + ' button[data-fid="panel-close"]').click()
    _apply(page)
    assert _macro_content(sandbox_client, name)["definition"] == "index=_audit | head 1"
    panel = _open_panel(page, name)
    assert _setting(panel, "definition").locator(".ea-setting-value code").inner_text() == "index=_audit | head 1"


def test_there_is_no_way_to_delete_a_setting_and_the_page_says_why(open_view, macro):
    name = macro()
    page = _open(open_view)
    panel = _open_panel(page, name)
    names = panel.locator(".ea-settings button").evaluate_all("nodes => nodes.map(n => n.textContent + n.getAttribute('aria-label'))")
    assert names and not any("delete" in n.lower() or "remove" in n.lower() for n in names)
    note = panel.locator(".ea-no-delete").inner_text()
    assert "cannot be removed here" in note and "no delete" in note


def test_show_default_value_lists_the_value_a_local_setting_hides(open_view, sandbox_client, shot):
    """A shipped report with a local ``search``: the toggle shows the value in default, once."""
    obj = None
    for candidate in sandbox_client.request("GET", ENDPOINT)["objects"]:
        if (candidate["type"] == "savedsearch" and candidate["app"] == "splunk_instrumentation"
                and candidate["name"] == "instrumentation.anonymized.eventsByTime"):
            obj = candidate
    if obj is None:
        pytest.skip("splunk_instrumentation does not ship the report")
    params = {k: obj[k] for k in ("type", "ns", "app", "name")}
    details = sandbox_client.request("GET", ENDPOINT, params)
    search = next(s for s in details["explicit"] if s["name"] == "search")
    default_text = search["overrides"][0]["value"] if search["overrides"] else search["value"]
    if search["layer"] == "default":
        # Make it local with the same text: harmless, and idempotent (no REST call removes it again).
        sandbox_client.request("POST", ENDPOINT, json_body={"changes": [dict(
            params, settings=[{"name": "search", "value": search["value"], "previous": search["value"]}])]})

    page = _open(open_view)
    panel = _open_panel(page, obj["name"], app="splunk_instrumentation")
    row = _setting(panel, "search")
    toggle = row.locator(".ea-show-default")
    assert toggle.inner_text() == "Show default value" and toggle.get_attribute("aria-expanded") == "false"
    assert row.locator(".ea-setting-default").count() == 0
    toggle.click()
    row = _setting(panel, "search")
    assert row.locator(".ea-show-default").get_attribute("aria-expanded") == "true"
    assert row.locator(".ea-setting-default code").inner_text().strip() == default_text.strip()
    shot(page, "app_management_setting_default")
    row.locator(".ea-show-default").click()
    assert _setting(panel, "search").locator(".ea-setting-default").count() == 0
