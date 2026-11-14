---
name: write-ui-test
description: Write a browser test that drives Splunk Web with Playwright and asserts on what the page renders. Use when adding or changing a view, dashboard JavaScript or CSS, navigation, or theme handling, or before documenting any behaviour only visible in a browser.
argument-hint: "[app-id] [what to test]"
---

# Write a UI test

UI tests live in `tests/ui/<app>/test_<app>_<topic>_ui.py` and run with
`splk test --ui <app>`, or as the last stage of `splk dev <app>` for any app
that has the directory. Plain `pytest` and CI never collect them.

They sign in to Splunk Web with `SPLUNK_WEB_USERNAME` / `SPLUNK_WEB_PASSWORD`
from `.env`, once per run (the session is cached in `.agent/ui/`). Add
`--headed` to watch the browser.

## Look first

Before writing assertions, look at the page:

```bash
splk shot <app>/<view> --wait-for "<selector>" [--theme dark]
```

Open the PNG it reports with Read. Write the test from what you saw, not from
what the code should do. `console_errors` and `page_errors` in the output show
JavaScript problems the screenshot may not.

## Fixtures (from `tests/ui/conftest.py`)

| Fixture | Use |
| --- | --- |
| `open_view(app, view, theme=None, ready=None)` | Open a view in this test's tab and return the Playwright `Page`. Always pass `ready`, a selector the page's JS renders once it is usable: the load event fires long before that. |
| `shot(page, name)` | Save `build/reports/ui/<app>/<name>.png` and return its path. Take one for every visual claim, then look at it. |
| `page_log(page)` | `.console_errors` and `.page_errors` (uncaught exceptions) since the page was opened. |
| `web` | The signed-in session: `web.url(path)` for Splunk Web URLs, `web.new_page()`. |
| `page` | This test's tab. A failure saves `<test>-FAILED.png` and `<test>-trace.zip`. |

Replay a failure step by step with `python -m playwright show-trace build/reports/ui/<app>/<test>-trace.zip`.

## Rules

- Select by the app's own ids and classes (`#easyadmin-roles .ea-tab`), never
  by Splunk Web's internal DOM, which changes between versions.
- One behaviour per test; the docstring says what the README promises.
- Assert `page_log(page).page_errors == []` on the main page test. Do not
  assert on all `console_errors`: Splunk Web logs its own.
- Read-only by default. A test that saves must create and delete its own
  objects (like the live tests' throwaway roles), and never edits real roles,
  users or preferences.
- When a result depends on the signed-in user's settings (theme, timezone),
  read the setting in the test and `pytest.skip` if it does not apply. Do not
  change the user's preferences.
- Each test must fail if the feature is removed. Check that by breaking it
  once (comment out the call, run, restore).
- After a change under `appserver/static/`, bump `[install] build` or the
  test sees the old JS.

## Example

```python
def test_role_grid_renders(open_view, shot, page_log):
    """The page loads the role model and draws one row per role, including admin."""
    page = open_view("easyadmin", "role_management", ready="#easyadmin-roles table.ea-table")
    shot(page, "role_management")
    roles = [n.strip() for n in page.locator("#easyadmin-roles th.ea-role").all_inner_texts()]
    assert "admin" in roles
    assert page_log(page).page_errors == []
```

See `tests/ui/easyadmin/test_easyadmin_ui.py` for theme assertions that read
the user's preference and skip when it does not apply.

## UX audit settings

Every view also gets the `splk ux` audit (screenshots in both themes,
accessibility scan, errors) without a test. Tell it how to read each view in
`tests/ui/<app>/ux.toml`: `ready` (the same selector the tests wait for) and
`scope` (the app's root element, so Splunk Web's own chrome is not scanned).
See `tests/ui/easyadmin/ux.toml` and the `splunk-ux` skill. UI tests cover
what the audit cannot: states, validation and flows the standard asks for.
