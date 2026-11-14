---
hits: 1
seen: [2026-11-14]
area: splk
level: skill
---
**Symptom:** easyadmin UI tests. `test_easyadmin_edit_ui::test_add_a_column_by_name`
failed (`"added here" != "not known here"`), and
`test_save_writes_the_change_to_splunkd` passed only by luck. The `_save()`
helper waited for `.ea-message.ea-success` (or `.ea-error`), then the grid.

**Cause:** a page whose save re-loads its model passes through an
intermediate render. In `apps/easyadmin/appserver/static/easyadmin_roles.js`,
`save()` shows the result message, then `load()` first re-renders the **old**
model with "Working..." beside the message, and only later the new one. Both
the message and the grid's ready selector exist during that intermediate
render, so a test that waits for either reads stale state. Any UI test of an
async save, delete or refresh that redraws the page can hit this.

**Fix:** `_save()` in `tests/ui/easyadmin/test_easyadmin_edit_ui.py` also
waits for `#easyadmin-roles .ea-message.ea-info` with text "Working..." to
detach before waiting for the ready selector.

**Catch earlier:** after an async action that reloads, wait for the busy
indicator to go, not for the result to appear. Added to the rules in
`.claude/skills/write-ui-test/SKILL.md`.
