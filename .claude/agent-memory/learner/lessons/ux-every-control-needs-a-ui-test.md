---
hits: 1
seen: [2026-11-14]
area: ux
level: skill
---
**Symptom:** easyadmin 1.2.0 App management. With all stages green, the
`splunk-ux-review` at 18:17:34 recorded a Major: "bulk panel: typing an owner
never re-renders, so 'Stage for N objects' stays disabled when owner is the
only change ... (inferred, no UI test covers the bulk panel)". A bulk owner
change could not be staged by the obvious path.

**Cause:** the UI tests covered the main flows (drag, single-object panel,
delete) but not every control on a secondary panel. The button's enabled
state was computed only at render, and no test typed into the owner field
alone. A control without a test is unverified, however green the stage.

**Fix:** an `input` handler on the owner field that updates just that button
(no full re-render), plus UI test
`test_easyadmin_apps_ui::test_bulk_owner_change_is_staged_and_applied`. UI
green with 30 tests at 18:22:02; re-review at 18:23:33 "previous major fixed".

**Catch earlier:** `write-ui-test` rule: each control on a page, including
secondary panels, gets a test that uses it alone; a button whose state
depends on an input is tested with only that input changed.

**Note (not a lesson):** a later UI run (19:04:33,
`test_sharing_is_colour_coded_and_labelled`, `assert 4 == 3`) failed only
because the test pinned the sharing key at three colours after a fourth
(System) was added on purpose; the test was updated (green 19:07:55).
