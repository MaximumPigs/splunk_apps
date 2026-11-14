---
hits: 1
seen: [2026-11-14]
area: splk
level: skill
---
**Symptom:** easyadmin
`test_easyadmin_edit_ui::test_read_only_user_sees_a_read_only_page` signed in
a second user by opening a second `splk.ui.SplunkWeb(...)` inside the test
session's one, and failed with "It looks like you are using Playwright Sync
API inside the asyncio loop". The `write-ui-test` skill recommended exactly
that approach.

**Cause:** Playwright's sync API cannot start a second `sync_playwright()`
in a thread where one is already running. Every UI test runs inside the
session's `SplunkWeb`, so any test needing another account hits this.

**Fix:** `SplunkWeb.new_user_page(user, password)` in `tools/splk/ui.py`
opens a new browser context in the same browser, signs in as that user, never
writes the owner's cached state file, and is closed with the session. Unit
test in `tests/test_splk_ui.py`; the read-only test now uses
`web.new_user_page(name, password)`.

**Catch earlier:** `.claude/skills/write-ui-test/SKILL.md` now says to use
`web.new_user_page` and never a second `SplunkWeb`.
