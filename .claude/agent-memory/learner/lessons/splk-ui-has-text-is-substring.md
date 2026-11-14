---
hits: 1
seen: [2026-11-14]
area: splk
level: skill
---
**Symptom:** easyadmin 1.2.0 UI run at 2026-11-14T18:49:46:
`test_easyadmin_apps_ui::test_type_menu_shows_common_types_first` failed
`assert 2 == 0`. The helper `_object()` in
`tests/ui/easyadmin/test_easyadmin_apps_ui.py` found rows with
`page.locator(<row selector>, has_text=name)`. For an object named `default`
it matched every locked row, because each carries a "default" badge.

**Cause:** Playwright's `has_text` (and `:has-text()`) is a case-insensitive
**substring** match over all the text in the element, including badges,
labels and counts. Any UI test that finds a row, card or box by a name can
match the wrong one when that name is a common word or a prefix of another.
The page was right; the test logic was wrong.

**Fix:** match the name element exactly:
`.ea-object:has(.ea-object-name:text-is("<name>"))` (`_object()`). UI green,
34 passed, at 18:53:20.

**Catch earlier:** `write-ui-test` rule: find items by their name element
with `:text-is()`, never `has_text` over the whole row.
