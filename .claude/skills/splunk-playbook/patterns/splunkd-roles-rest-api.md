---
confirmed: 2
seen: [2026-11-13, 2026-11-14]
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
8. Live and UI tests create throwaway roles and users through the `sandbox`
   fixture (named `splktest_*`); the environment guard snapshots roles, users
   and app permissions around every test and fails one that leaves a change.
   A real role a test might touch is recorded first with `sandbox.remember`.
   Afterwards confirm the target is clean (`write-live-test`, "Confirm the
   target is clean"): zero `splktest_*` roles and users, no pending file.
9. Decide what an app may change by what **Splunk Web's role editor** offers,
   not by what splunkd accepts. The REST API accepts more (table below), and
   some of the extra attributes behave badly:
   - `fieldFilterExemption` only ever appends: posting `""` stores an empty
     entry beside the old ones, and `configs/conf-authorize` changes are not
     seen by the roles endpoint, so an entry cannot be removed;
   - `deleteIndexesAllowed` is refused (403) unless the role being written
     holds `delete_by_keyword`;
   - `federatedProviders` is refused (403) to admin with no provider defined.

**Splunk Web's role editor on 10.6.1** (Settings > Roles > a role's name):
a full page at `/manager/launcher/authorization/roles/edit/<role>`, not a
modal, with tabs as `[role=tab]` and Cancel / Save Role at the bottom.

| Editor tab | Control | Attribute |
| --- | --- | --- |
| Inheritance | a checkbox per role | `imported_roles` |
| Capabilities | a checkbox per capability | `capabilities` |
| Indexes | *Included* / *Default* per index, plus a wildcard box | `srchIndexesAllowed` / `srchIndexesDefault` |
| Providers | *Included* / *Default* per provider, plus a wildcard box | `srchFederatedProvidersAllowed` / `srchFederatedProvidersDefault` (a new role has `*` in both, shown ticked) |
| Restrictions | *Search filter* (`name=srchFilter`) and a filter generator | `srchFilter` |
| Resources | *Default app* | `defaultApp` |
| | *Standard* / *Real-time role search limit* | `cumulativeSrchJobsQuota` / `cumulativeRTSrchJobsQuota` (input `name`) |
| | *Standard* / *Real-time user search limit* | `srchJobsQuota` / `rtSrchJobsQuota` (input `name`) |
| | *Role search time window limit* (drop-down) | `srchTimeWin` |
| | *earliest searchable event time* (drop-down) | `srchTimeEarliest` |
| | *Disk space limit* (`name=srchDiskQuota`) | `srchDiskQuota` |

Not in the editor, though splunkd's `authorization/roles/_new` lists them as
writable: `srchIndexesDisallowed`, `deleteIndexesAllowed`, `grantable_roles`,
`queuedSearchQuota`, `srchMinScheduleInterval` (and `.<pattern>`),
`srchAllowAdvancedCron`, `federatedProviders`, `fieldFilterExemption`, and the
six `kvstore_{create,update,delete}.{deny_list,implicit_deny_list}` lists.

To probe a newer version: open the edit page for a `sandbox` role in a UI
test, click each `[role=tab]`, record `body.inner_text()`, every form control
(`input, select, textarea, [role=checkbox], [role=combobox]`, with `name` and
`aria-label`) and a screenshot per tab, then leave with Cancel. Controls
without a `name` are mapped by label and by comparing what splunkd reports
for the role (`| rest /services/authorization/roles`) with what the editor
shows ticked. Do not assume the editor's DOM (it was guessed as a modal
`[role=dialog]` and failed): take the screenshot first, and read the
`-FAILED.png` before theorising (`lessons/process-evidence-before-theory.md`).
Delete the probe test once its findings are recorded here.

**Why this way:** each step is a failed live test, with details in the
lessons `splunkd-json-numbers-vs-rest-search`,
`splunkd-role-index-lists-sorted`, `splunkd-role-capabilities-reporting` and
`python-simplerequest-postargs-dict`. The type mismatch was missed because the
endpoint was investigated through `| rest`.

**Verify:** a unit test that the app's attribute list equals the editor's
table above, and a live test that every other attribute is refused (400);
unit tests over the normalisers (`as_text`, `as_list`) with each
shape above; live tests that read back what they wrote and compare sets and
unions.

**Reference:** `apps/easyadmin/bin/easyadmin_core.py` (`as_list`, `as_text`),
`apps/easyadmin/bin/easyadmin_rest.py` (`SplunkdGateway`),
`tests/live/easyadmin/test_easyadmin_live.py` (`make_role`, `_as_set`, `_text`),
`tests/live/easyadmin/test_easyadmin_features_live.py` (`NOT_IN_EDITOR`).
