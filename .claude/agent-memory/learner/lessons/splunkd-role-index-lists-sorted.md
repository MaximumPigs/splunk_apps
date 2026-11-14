---
hits: 1
seen: [2026-11-12]
area: splunkd
level: pattern
---
**Symptom:** easyadmin live `test_unknown_role_is_reported_without_failing_the_rest`
failed at 06:34: `assert ['_internal', 'main'] == ['main', '_internal']`.

**Cause:** splunkd stores a role's `srchIndexesAllowed` and
`srchIndexesDefault` sorted, not in the order they were written.

**Fix:** `tests/live/easyadmin/test_easyadmin_live.py` now compares these as
sets (the `_indexes()` helper).

**Catch earlier:** in live tests, compare multi-value role attributes read
back from splunkd as sets, not ordered lists.

**Pattern:** the working recipe is in playbook `splunkd-roles-rest-api`.
