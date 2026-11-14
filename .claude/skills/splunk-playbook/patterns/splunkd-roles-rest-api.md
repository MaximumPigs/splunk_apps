---
confirmed: 1
seen: [2026-11-13]
apps: [easyadmin]
---
# Reading and writing roles through splunkd REST

**Use when:** app code or a live test reads or changes roles at
`/services/authorization/roles` (indexes, capabilities, imports, quotas).
Everything below was observed on Splunk 10.6.1 with throwaway roles.

**Recipe:**

1. Read the way the code will: REST JSON (`output_mode=json`), through the
   live-test `splunk` fixture, not `| rest` in `splk search`. The two give
   different types (step 2).
2. Normalise every value at the boundary, in `<app>_core.py`:
   - scalars to text: REST JSON returns numbers (`srchJobsQuota`) as JSON
     numbers, while `| rest` returns strings;
   - multi-valued fields to lists: one value arrives as a bare string
     (`imported_roles = "user"`), and unset can be `None`, `""` or absent.
3. Compare multi-valued fields as **sets**. splunkd stores `srchIndexesAllowed`
   and `srchIndexesDefault` sorted, not in the order they were written.
4. A role's effective capabilities are `capabilities` **plus**
   `imported_capabilities`. Once a role imports another that has a
   capability, splunkd lists it only under `imported_capabilities`.
5. Expect a new role to start with five capabilities of its own
   (`edit_own_objects`, `list_all_objects`, `run_collect`, `run_mcollect`,
   `schedule_rtsearch`). It does not start empty.
6. Writing `capabilities` replaces the whole set: every unlisted default is
   written to the stanza as `<capability> = disabled`. To add one, write the
   current set plus the new one. To clear a multi-valued field, post `""`.
7. Write with the caller's session through `simpleRequest`, with
   `postargs={field: [v1, v2]}`, never a list of pairs (see
   `rest-endpoint-behind-page`).
8. Live tests create throwaway roles (`easyadmin_live_<uuid8>`) in a fixture
   that deletes them afterwards, and never touch real roles.

**Why this way:** each step is a failed live test, with details in the
lessons `splunkd-json-numbers-vs-rest-search`,
`splunkd-role-index-lists-sorted`, `splunkd-role-capabilities-reporting` and
`python-simplerequest-postargs-dict`. The type mismatch was missed because the
endpoint was investigated through `| rest`.

**Verify:** unit tests over the normalisers (`as_text`, `as_list`) with each
shape above; live tests that read back what they wrote and compare sets and
unions.

**Reference:** `apps/easyadmin/bin/easyadmin_core.py` (`as_list`, `as_text`),
`apps/easyadmin/bin/easyadmin_rest.py` (`SplunkdGateway`),
`tests/live/easyadmin/test_easyadmin_live.py` (`make_role`, `_as_set`, `_text`).
