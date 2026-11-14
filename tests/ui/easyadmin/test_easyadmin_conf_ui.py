"""UI tests for the Configuration precedence tab of easyadmin's App management page.

A macro with the same name but different definitions is created in the search
and launcher apps (each in its app's local/macros.conf) and deleted after the
test; the tab must show the clash in btool's global order.
"""

import time
import urllib.parse

import pytest

from splk.rest import SplunkError

APP = "easyadmin"
VIEW = "app_management"
ROOT = "#easyadmin-apps"
READY = ROOT + " .ea-grid"
STANZAS = ROOT + " .ea-stanzas, " + ROOT + " .ea-conf .ea-empty"


def q(name):
    return urllib.parse.quote(name, safe="")


@pytest.fixture
def clashing_macro(sandbox_client):
    name = "easyadmin_ui_conf_%d" % int(time.time() * 1000)
    made = []
    try:
        for app, definition in (("search", "index=_internal"), ("launcher", "index=_audit")):
            sandbox_client.request("POST", "/servicesNS/nobody/%s/admin/macros" % app,
                                   {"name": name, "definition": definition})
            made.append(app)
        yield name
    finally:
        for app in made:
            try:
                sandbox_client.request("DELETE", "/servicesNS/nobody/%s/admin/macros/%s" % (app, q(name)))
            except SplunkError:
                pass


def _open_tab(open_view, conf="macros"):
    page = open_view(APP, VIEW, ready=READY)
    page.locator(ROOT + ' button[data-fid="tab:conf"]').click()
    page.wait_for_selector(STANZAS)
    if conf:
        page.locator(ROOT + " .ea-conf-file").select_option(conf)
        page.locator(ROOT + " .ea-busy").wait_for(state="detached")
        page.wait_for_selector(STANZAS)
    return page


def test_tab_shows_a_clash_in_precedence_order(open_view, clashing_macro, shot, page_log):
    """The precedence tab lists a stanza set differently in two apps, the value in effect first."""
    page = _open_tab(open_view)
    tab = page.locator(ROOT + ' button[data-fid="tab:conf"]')
    assert tab.get_attribute("aria-selected") == "true"
    page.locator(ROOT + " .ea-conf-filter").fill(clashing_macro)
    stanza = page.locator(ROOT + ' .ea-stanza:has(.ea-stanza-name:text-is("[%s]"))' % clashing_macro)
    assert stanza.count() == 1
    assert "1 conflicting setting" in stanza.locator("summary").inner_text()
    stanza.locator("summary").click()
    row = stanza.locator('tr:has(.ea-prec-name code:text-is("definition"))')
    assert "values differ" in row.inner_text()
    sources = row.locator(".ea-prec-sources li").all_inner_texts()
    # macros.conf is read at search time, per app: the page says so and does
    # not claim the first value is the one in effect everywhere.
    assert sources[0].startswith("first in global order")
    assert "launcher / local" in sources[0] and "index=_audit" in sources[0]
    assert sources[1].startswith("later in global order") and "search / local" in sources[1]
    assert "read at search time, per app" in page.locator(ROOT + " .ea-prec-searchtime").inner_text()
    # Nothing is styled as winning or struck through: per app, either may apply.
    decorations = row.locator(".ea-prec-value").evaluate_all(
        "nodes => nodes.map(n => getComputedStyle(n).textDecorationLine)")
    assert "line-through" not in decorations
    assert row.locator(".ea-prec-effective, .ea-prec-overridden").count() == 0
    shot(page, "app_management_precedence")
    assert page_log(page).page_errors == []


def test_app_filter_keeps_stanzas_that_app_sets(open_view, clashing_macro):
    """"Only stanzas set by app" keeps the stanzas that app sets something in."""
    page = _open_tab(open_view)
    page.locator(ROOT + " .ea-conf-app").select_option("launcher")
    names = [n.strip("[]") for n in page.locator(ROOT + " .ea-stanza-name").all_inner_texts()]
    assert clashing_macro in names


def test_stanzas_without_conflicts_are_listed_on_request(open_view, clashing_macro, sandbox_client):
    """Without a clash the stanza is hidden until "Include stanzas without conflicts" is ticked."""
    sandbox_client.request("DELETE", "/servicesNS/nobody/launcher/admin/macros/%s" % q(clashing_macro))
    page = _open_tab(open_view)
    page.locator(ROOT + " .ea-conf-filter").fill(clashing_macro)
    assert page.locator(ROOT + " .ea-stanza").count() == 0
    # Either other stanzas still clash ("No stanzas match the filters.") or
    # none do ("No conflicts: ..."); both say why the list is empty.
    text = page.locator(ROOT + " .ea-conf").inner_text()
    assert "No stanzas match the filters." in text or "No conflicts:" in text
    page.locator(ROOT + ' input[data-fid="conf-all"]').check()
    page.locator(ROOT + " .ea-busy").wait_for(state="detached")
    page.wait_for_selector(ROOT + " .ea-stanza")
    assert page.locator(ROOT + " .ea-stanza").count() == 1


def test_secret_values_show_as_hidden(open_view):
    """Passwords and keys are listed as set but their values are never shown."""
    page = _open_tab(open_view, conf="server")
    page.locator(ROOT + ' input[data-fid="conf-all"]').check()
    page.locator(ROOT + " .ea-busy").wait_for(state="detached")
    page.wait_for_selector(ROOT + " .ea-stanza")
    # pass4SymmKey is set in etc/system on every instance ([general]).
    page.locator(ROOT + " .ea-conf-filter").fill("general")
    stanza = page.locator(ROOT + ' .ea-stanza:has(.ea-stanza-name:text-is("[general]"))')
    stanza.locator("summary").click()
    more = stanza.locator(".ea-prec-more")
    if more.count():
        more.click()
    # Exact name: has_text would also match pass4SymmKey_minLength and the like.
    row = stanza.locator('tr:has(.ea-prec-name code:text-is("pass4SymmKey"))')
    assert "secret, hidden" in row.inner_text()
    # server.conf is not a search-time file: its first value is in effect,
    # and any later ones are struck through as overridden.
    assert row.locator(".ea-prec-sources li").first.inner_text().startswith("in effect")
    later = row.locator(".ea-prec-overridden .ea-prec-value")
    if later.count():
        assert later.first.evaluate("n => getComputedStyle(n).textDecorationLine") == "line-through"
    assert page.locator(ROOT + " .ea-prec-searchtime").count() == 0
    assert set(v.strip() for v in row.locator(".ea-prec-value").all_inner_texts()) <= {"********", "(empty)"}


def test_precedence_link_opens_the_tab(web, page):
    """#precedence in the address opens the precedence tab straight away, so the view can be linked."""
    page.goto(web.url("/app/%s/%s#precedence" % (APP, VIEW)), wait_until="load")
    page.wait_for_selector(STANZAS, timeout=60000)
    assert page.locator(ROOT + ' button[data-fid="tab:conf"]').get_attribute("aria-selected") == "true"


def test_tabs_follow_the_arrow_keys(open_view):
    """Left and Right move between the tabs; only the active tab is in the Tab order."""
    page = open_view(APP, VIEW, ready=READY)
    apps_tab = page.locator(ROOT + ' button[data-fid="tab:apps"]')
    assert apps_tab.get_attribute("tabindex") == "0"
    assert page.locator(ROOT + ' button[data-fid="tab:conf"]').get_attribute("tabindex") == "-1"
    apps_tab.focus()
    page.keyboard.press("ArrowRight")
    conf_tab = page.locator(ROOT + ' button[data-fid="tab:conf"]')
    assert conf_tab.get_attribute("aria-selected") == "true"
    assert page.evaluate("document.activeElement.getAttribute('data-fid')") == "tab:conf"
    assert page.locator(ROOT + " #ea-tabpanel").get_attribute("aria-labelledby") == "ea-tab-conf"
