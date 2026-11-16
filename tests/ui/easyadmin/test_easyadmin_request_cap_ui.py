"""UI tests for the cap on the size of one Apply in the App management page.

The server refuses a request over 16 MB (see the live test). The page refuses
earlier, at the click that would take the staged changes over the cap, and puts
the staged state back as it was. Reaching 16 MB through the page would take
hundreds of staged edits, so these tests open the page with
``?ea_max_request_bytes=<n>``, a hook that can only lower the cap, and use
sizes a few hundred bytes wide. One test per family of staging control.

Sizes the tests rely on (JSON the page sends, for macros named
``easyadmin_ui_<13 digits>``): an empty body is 24 bytes, one move or copy
about 130 bytes, two about 240, a settings edit about 230 plus its value, and a
permission change or a delete adds about 60 to a change.
"""

import pytest

from test_easyadmin_apps_ui import (APP, READY, ROOT, VIEW, _object, macro, q)  # noqa: F401
from test_easyadmin_settings_ui import PANEL, _dt, _open_panel, _setting

MESSAGES = ROOT + " .ea-messages"


def _open_capped(web, page, cap):
    """Open App management with the page's cap lowered to ``cap`` bytes."""
    web.open(page, "/app/%s/%s?ea_max_request_bytes=%d" % (APP, VIEW, cap), READY)
    page.locator(ROOT + ' input[data-fid="builtin"]').check()
    page.wait_for_selector(ROOT + ' .ea-app[data-app="search"]')
    return page


def _staged_count(page):
    return page.locator(ROOT + " .ea-apply").inner_text()


def _select(page, names):
    page.locator(ROOT + " .ea-filter").fill("easyadmin_ui_")
    for name in names:
        _object(page, "search", name).locator(".ea-select").check()


def test_a_setting_edit_over_the_cap_is_not_staged_and_keeps_what_was_typed(web, page, macro, shot):
    name = macro()
    other = macro()
    _open_capped(web, page, 600)

    # A short edit fits and is staged.
    panel = _open_panel(page, other)
    panel.locator('button[data-fid="setting-edit:definition"]').click()
    panel.locator("#ea-edit-value").fill("index=_audit")
    panel.locator('button[data-fid="setting-stage:definition"]').click()
    assert "settings changed (1)" in _object(page, "search", other).inner_text()
    staged_before = _staged_count(page)
    assert "1 object" in staged_before

    # A long value on another object would take the request over 600 bytes.
    panel = _open_panel(page, name)
    panel.locator('button[data-fid="setting-edit:definition"]').click()
    long_value = "index=" + "x" * 1500
    panel.locator("#ea-edit-value").fill(long_value)
    panel.locator('button[data-fid="setting-stage:definition"]').click()
    message = page.locator(MESSAGES).inner_text()
    assert "Not staged" in message
    assert "one Apply can send at most 600 bytes" in message
    assert "Apply what is staged first" in message
    # The panel covers the page's message area, so it shows the refusal itself.
    assert "Not staged" in panel.locator(".ea-panel-refusal").inner_text()
    shot(page, "app_management_over_cap_setting")
    # The editor is still open with the typed value, the object has nothing staged,
    # and the earlier edit is still counted (its row is filtered out of view).
    assert panel.locator("#ea-edit-value").input_value() == long_value
    assert page.evaluate("() => document.activeElement && document.activeElement.id") == "ea-edit-value"
    assert "settings changed" not in _object(page, "search", name).inner_text()
    assert _staged_count(page) == staged_before

    # A shorter value in the same editor now fits.
    panel.locator("#ea-edit-value").fill("index=_audit")
    panel.locator('button[data-fid="setting-stage:definition"]').click()
    assert "settings changed (1)" in _object(page, "search", name).inner_text()


def test_a_new_setting_over_the_cap_is_not_staged_and_the_form_keeps_its_draft(web, page, macro):
    name = macro()
    _open_capped(web, page, 600)
    panel = _open_panel(page, name)
    panel.locator("#ea-add-name").fill("errormsg")
    long_value = "y" * 1500
    panel.locator("#ea-add-value").fill(long_value)
    panel.locator('button[data-fid="setting-add-stage"]').click()
    assert "Not staged" in page.locator(MESSAGES).inner_text()
    assert _dt(panel, "errormsg").count() == 0
    assert panel.locator("#ea-add-name").input_value() == "errormsg"
    assert panel.locator("#ea-add-value").input_value() == long_value
    assert "settings changed" not in _object(page, "search", name).inner_text()
    # Shorter, it stages.
    panel.locator("#ea-add-value").fill("short")
    panel.locator('button[data-fid="setting-add-stage"]').click()
    assert "new, staged" in _dt(panel, "errormsg").inner_text()
    assert _setting(panel, "errormsg").locator(".ea-setting-new code").inner_text() == "short"


def test_a_move_that_goes_over_the_cap_stages_nothing_and_keeps_the_selection(web, page, macro):
    first, second = macro(), macro()
    _open_capped(web, page, 200)
    _select(page, [first, second])
    page.locator(ROOT + " .ea-move-target").select_option("launcher")
    page.locator(ROOT + ' button[data-fid="move-selected"]').click()
    message = page.locator(MESSAGES).inner_text()
    assert "Not staged" in message and "at most 200 bytes" in message
    # Nothing at all was staged, not one of the two, and both are still ticked.
    assert "moving from" not in page.locator(ROOT + " .ea-grid").inner_text()
    assert page.locator(ROOT + " .ea-apply").is_disabled()
    assert "2 objects selected" in page.locator(ROOT + " .ea-selection").inner_text()
    # One object fits. (A refusal re-renders the bar, so choose the app again.)
    _object(page, "search", second).locator(".ea-select").uncheck()
    page.locator(ROOT + " .ea-move-target").select_option("launcher")
    page.locator(ROOT + ' button[data-fid="move-selected"]').click()
    assert "moving from" in _object(page, "launcher", first).inner_text()
    assert "Not staged" not in page.locator(MESSAGES).inner_text()


def test_a_copy_and_a_delete_over_the_cap_are_refused_too(web, page, macro):
    first, second = macro(), macro()
    _open_capped(web, page, 200)
    _select(page, [first, second])
    page.locator(ROOT + " .ea-move-target").select_option("launcher")
    page.locator(ROOT + ' button[data-fid="copy-selected"]').click()
    assert "Not staged" in page.locator(MESSAGES).inner_text()
    assert page.locator(ROOT + " .ea-apply").is_disabled()
    page.locator(ROOT + ' button[data-fid="delete-selected"]').click()
    assert "Not staged" in page.locator(MESSAGES).inner_text()
    assert page.locator(ROOT + " .ea-apply").is_disabled()
    assert "will be deleted" not in page.locator(ROOT + " .ea-grid").inner_text()


def test_bulk_permissions_over_the_cap_keep_the_panel_open(web, page, macro):
    first = macro()
    _open_capped(web, page, 150)
    _select(page, [first])
    page.locator(ROOT + ' button[data-fid="bulk-acl"]').click()
    page.locator(ROOT + ' input[data-fid="bulk-owner"]').fill("nobody")
    page.locator(ROOT + ' button[data-fid="bulk-stage"]').click()
    assert "Not staged" in page.locator(MESSAGES).inner_text()
    # The panel is still there with the owner that was typed, and nothing is staged.
    assert page.locator(ROOT + ' input[data-fid="bulk-owner"]').input_value() == "nobody"
    assert "Not staged" in page.locator(ROOT + " .ea-panel-refusal").inner_text()
    assert "permissions changed" not in _object(page, "search", first).inner_text()
    assert page.locator(ROOT + " .ea-apply").is_disabled()


def test_a_clone_over_the_cap_is_refused_and_the_form_keeps_its_draft(web, page):
    _open_capped(web, page, 200)
    page.locator(ROOT + ' button[data-fid="clone:search"]').click()
    form = page.locator(ROOT + " .ea-panel")
    name = form.locator('input[data-fid="newapp-name"]').input_value()
    assert name == "search_copy"
    page.locator(ROOT + ' button[data-fid="newapp-stage"]').click()
    assert "Not staged" in page.locator(MESSAGES).inner_text()
    assert form.locator('input[data-fid="newapp-name"]').input_value() == name
    assert "Not staged" in form.locator(".ea-panel-refusal").inner_text()
    assert page.locator(ROOT + ' .ea-app[data-app="%s"]' % name).count() == 0
    assert page.locator(ROOT + " .ea-apply").is_disabled()


def test_without_the_hook_the_cap_is_16_mb_and_the_hook_cannot_raise_it(web, page, macro):
    """A short edit stages with no parameter; a huge ``ea_max_request_bytes`` is no looser than 16 MB."""
    name = macro()
    _open_capped(web, page, 99999999999)
    panel = _open_panel(page, name)
    panel.locator('button[data-fid="setting-edit:definition"]').click()
    panel.locator("#ea-edit-value").fill("index=" + "x" * 5000)
    panel.locator('button[data-fid="setting-stage:definition"]').click()
    assert "settings changed (1)" in _object(page, "search", name).inner_text()
    assert "Not staged" not in page.locator(MESSAGES).inner_text()
