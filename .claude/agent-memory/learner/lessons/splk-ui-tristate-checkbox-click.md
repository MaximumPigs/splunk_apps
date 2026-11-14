---
hits: 1
seen: [2026-11-14]
area: splk
level: skill
---
**Symptom:** easyadmin 1.2.0 UI run at 2026-11-14T18:49:46:
`test_easyadmin_apps_ui::test_select_all_in_an_app_selects_what_it_shows`
failed `assert 1 == 0`. The test called `uncheck()` on an app's half-ticked
(indeterminate) select-all box, expecting it to clear the selection.

**Cause:** an indeterminate checkbox has `checked = false`. Playwright's
`uncheck()` sees it already unchecked and does nothing (and `check()` would
only tick it). Neither does what a person's click does. Affects any UI test
of a tri-state "select all" control.

**Fix:** `click()` the box, as a browser user would: from indeterminate it
ticks (selects all), a second `click()` clears. The test also asserts
`indeterminate` is true first (`evaluate("n => n.indeterminate")`). UI green,
34 passed, at 18:53:20.

**Catch earlier:** `write-ui-test` rule: drive tri-state checkboxes with
`click()` and assert the resulting state, never `check()`/`uncheck()`.
