---
hits: 1
seen: [2026-11-16]
area: splunkd
level: lesson
---
**Symptom:** easyadmin live test
`test_details_and_precedence_do_not_read_the_theme_preference` failed in
`splk dev` ("AssertionError: the theme preference was read: [...]", the rows
shown were `current-context` requests; the run-log text is truncated, so the
exact row that tripped it is not recorded). It went green after the check was
changed to wait for a later marker request before asserting absence
(`wait_for_marker` in `tests/live/easyadmin/easyadmin_live_support.py`).
**Cause:** a test that asserts a request is ABSENT from `splunkd_access`
searches a log that is indexed seconds after the request. "No row yet" proves
nothing until the log has caught up, so an absence check is either flaky or
vacuous. The old check only waited for a presence row of a different URI.
**Fix:** send a request nothing else sends (a GET for a random macro name), poll
until that marker is searchable, then assert absence of the earlier request.
Caveat: that splunkd_access.log is indexed in file order is inferred, not
observed; the reviewer flagged it as an open finding.
**Catch earlier:** any "did not call X" live test must pass through
`wait_for_marker` first. Not yet promoted; if a second absence test appears,
add a line to `write-live-test`.
