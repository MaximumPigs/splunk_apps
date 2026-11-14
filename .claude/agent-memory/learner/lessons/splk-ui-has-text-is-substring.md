---
hits: 2
seen: [2026-11-14, 2026-11-14]
area: splk
level: rule
---
**Symptom:** easyadmin 1.2.0 UI run at 2026-11-14T18:49:46:
`test_easyadmin_apps_ui::test_type_menu_shows_common_types_first` failed
`assert 2 == 0`. The helper `_object()` in
`tests/ui/easyadmin/test_easyadmin_apps_ui.py` found rows with
`page.locator(<row selector>, has_text=name)`. For an object named `default`
it matched every locked row, because each carries a "default" badge.

Second hit, 1.3.0 (20:22:24):
`test_easyadmin_conf_ui::test_secret_values_show_as_hidden` failed with a
Playwright strict mode violation: `has_text="pass4SymmKey"` also matched
`pass4SymmKey_minLength`. This was after the `write-ui-test` rule existed.
Fixed with `tr:has(.ea-prec-name code:text-is("pass4SymmKey"))`.

**Cause:** Playwright's `has_text` (and `:has-text()`) is a case-insensitive
**substring** match over all the text in the element, including badges,
labels and counts. Any UI test that finds a row, card or box by a name can
match the wrong one when that name is a common word or a prefix of another.
The page was right; the test logic was wrong.

**Fix:** match the name element exactly:
`.ea-object:has(.ea-object-name:text-is("<name>"))` (`_object()`). UI green,
34 passed, at 18:53:20.

**Catch earlier:** `write-ui-test` rule: find items by their name element
with `:text-is()`, never `has_text` over the whole row. Promoted at 2 hits to
`.claude/rules/ui-ux.md`, which loads whenever `tests/ui/**` is touched, so
it is in context while writing the test, not only when the skill is read.
Next step if it recurs: a unit test over `tests/ui/` flagging `has_text=`
on item locators (existing uses on buttons and messages are fine).
