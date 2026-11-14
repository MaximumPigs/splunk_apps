"""UI tests for easyadmin's role management page, in a real browser.

The live tests prove the endpoint and the handler's writes; these prove what
only a browser shows: the page's JavaScript renders the grid, the tabs work,
and the page ends up in the signed-in user's theme. That last one was shipped
as working before anyone had seen it (see the docs-unobserved-claims lesson).

Read-only on purpose: nothing here saves a change, so the tests are safe to
run against any role set.
"""

import pytest

APP = "easyadmin"
VIEW = "role_management"
ROOT = "#easyadmin-roles"
# The grid exists only once the model has loaded and rendered.
READY = ROOT + " table.ea-table"
# The page's own endpoint, through Splunk Web's proxy (default/web.conf).
ENDPOINT = "/splunkd/__raw/services/easyadmin/roles?output_mode=json"


def _theme_preference(web, page):
    """The theme the endpoint reports for the signed-in user ("light", "dark" or None).

    Fetched inside the page so it runs as the browser's own session, exactly
    as the page's script does.
    """
    return page.evaluate(
        """async (url) => {
            const response = await fetch(url, {credentials: "same-origin",
                                               headers: {"X-Requested-With": "XMLHttpRequest"}});
            if (!response.ok) { throw new Error("HTTP " + response.status + " from " + url); }
            return (await response.json()).theme;
        }""",
        web.url(ENDPOINT),
    )


def test_role_grid_renders(open_view, shot, page_log):
    """The page loads the role model and draws one row per role, including admin."""
    page = open_view(APP, VIEW, ready=READY)
    shot(page, "role_management")
    roles = [name.strip() for name in page.locator(ROOT + " th.ea-role").all_inner_texts()]
    assert "admin" in roles
    # The same areas as Splunk Web's own role editor, and nothing more.
    labels = [t.strip() for t in page.locator(ROOT + " .ea-tab").all_inner_texts()]
    assert labels == ["Indexes", "Capabilities", "Inheritance", "Providers", "Restrictions",
                      "Resources"]
    assert page_log(page).page_errors == []


def test_switching_tabs_changes_the_active_tab(open_view):
    """Clicking another tab makes it the active one and redraws the grid."""
    page = open_view(APP, VIEW, ready=READY)
    tabs = page.locator(ROOT + " .ea-tab")
    second_label = tabs.nth(1).inner_text().strip()
    tabs.nth(1).click()
    active = page.locator(ROOT + " .ea-tab.ea-tab-active")
    assert active.count() == 1
    assert active.inner_text().strip() == second_label
    page.wait_for_selector(READY)


def test_page_follows_the_users_theme(web, open_view, shot):
    """With no ?theme=, the page ends up in the user's preferred theme.

    Classic dashboards ignore the preference on their own; the page reloads
    itself with ?theme=<preference> when Splunk drew the other one.
    """
    page = open_view(APP, VIEW, ready=READY)
    preference = _theme_preference(web, page)
    if preference not in ("light", "dark"):
        pytest.skip("signed-in user has no light/dark theme preference (got %r)" % preference)
    shot(page, "role_management-preference-%s" % preference)
    dark = "ea-dark" in (page.get_attribute(ROOT, "class") or "")
    assert dark == (preference == "dark")


def test_other_theme_in_url_is_corrected_once(web, open_view, shot):
    """Opened with the opposite ?theme=, the page reloads once into the preference."""
    page = open_view(APP, VIEW, ready=READY)
    preference = _theme_preference(web, page)
    if preference not in ("light", "dark"):
        pytest.skip("signed-in user has no light/dark theme preference (got %r)" % preference)
    other = "light" if preference == "dark" else "dark"
    page = open_view(APP, VIEW, theme=other, ready=READY)
    shot(page, "role_management-from-%s" % other)
    assert "theme=%s" % preference in page.url
    assert ("ea-dark" in (page.get_attribute(ROOT, "class") or "")) == (preference == "dark")
