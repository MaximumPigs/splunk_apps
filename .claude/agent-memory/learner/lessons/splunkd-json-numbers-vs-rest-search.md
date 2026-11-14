---
hits: 1
seen: [2026-11-13]
area: splunkd
level: pattern
---
**Symptom:** easyadmin live `test_bulk_update_across_tabs_in_one_submit` and
`test_settings_tab_reads_back_what_was_written` failed with HTTP 400 "previous
must be the value the page loaded": the tests passed a role's `srchJobsQuota`
straight from the REST response as the expected previous value.

**Cause:** splunkd's JSON (`output_mode=json` on a REST endpoint) returns numeric
attributes such as `srchJobsQuota` as JSON numbers. The same attributes read
through `| rest` in SPL (`splk search`) come back as strings, which is what the
investigation had looked at. Any code or test that compares REST values to
strings, or checks `isinstance(value, str)`, is affected.

**Fix:** the app's core normalises with `as_text()` before comparing; the live
tests read through a `_text()` helper and compare `str(...)`.

**Catch earlier:** when inspecting an endpoint to design against, read it the
way the code will (the REST JSON, e.g. through a live-test fixture), not
through `| rest`. Normalise scalar REST values to text at the boundary.

**Pattern:** the working recipe is in playbook `splunkd-roles-rest-api`.
