---
hits: 1
seen: [2026-11-15]
area: splunkd
level: lesson
---
**Symptom:** easyadmin 1.4.0 UI run at 2026-11-15T07:26:19 (`1 failed, 47
passed`): a test of the details panel asserted that a macro's full settings
list contains `iseval`. splunkd's full macro entry has no such key; the
assertion failed (`'iseval' in 'Close\neasyadmin_ui_...Search macro in ...'`).

**Cause:** the setting name was guessed from what a macro "should" have
(`macros.conf` has `iseval`), not taken from what splunkd's REST content
actually returned. REST content keys differ from conf attribute names and
vary by type and version. Any test in any app that asserts on a specific
REST content key it has not seen is exposed. Same family as
`docs-unobserved-claims`.

**Fix:** the test asserts the full list is longer than the object's own
list (`tests/ui/easyadmin/test_easyadmin_apps_ui.py`, comment "The full list
... is longer"), which holds whatever keys splunkd sends.

**Catch earlier:** before asserting a key, look at a real response
(live test output or `splk search "| rest ..."`) and assert only keys seen
there, or assert a structural property instead.
