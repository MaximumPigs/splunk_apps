---
hits: 1
seen: [2026-11-12]
area: python
level: pattern
---
**Symptom:** easyadmin live `test_bulk_update_grants_and_revokes_in_one_submit`
and `test_revoking_the_last_index_empties_the_list` failed (`assert 0 == 1`,
runs 06:24-06:28). For each role POST, the handler reported
`'list' object has no attribute 'items'`.

**Cause:** `splunk.rest.simpleRequest(postargs=...)` calls `.items()` on
`postargs`, so it only accepts a dict. A list of `(key, value)` pairs, the
usual way to repeat a form field, breaks it.

**Fix:** `SplunkdGateway.update_role` in `apps/easyadmin/bin/easyadmin_rest.py`
now passes a dict with a list value. Each item is sent as its own form value,
and `""` clears a multi-valued attribute.

**Catch earlier:** to repeat or clear a field with `simpleRequest`, pass
`{field: [v1, v2]}` or `{field: ""}`. Never pass a list of pairs.

**Pattern:** the working recipe is in playbook `rest-endpoint-behind-page`.
