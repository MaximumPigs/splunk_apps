---
hits: 1
seen: [2026-11-13]
area: splunkd
level: lesson
---
**Symptom:** easyadmin live `test_bulk_update_across_tabs_in_one_submit`
expected a role's `capabilities` to be its starting set plus
`schedule_search`, and got only `schedule_search`. An earlier version expected
a new role to have no capabilities and got five.

**Cause:** observed on 10.6.1 with a throwaway role, one change at a time:
- A role created over REST already reports five capabilities as its own
  (`edit_own_objects`, `list_all_objects`, `run_collect`, `run_mcollect`,
  `schedule_rtsearch`) without any being written.
- Once the role imports a role that also has a capability, splunkd lists that
  capability only under `imported_capabilities`, not under `capabilities`.
  Clearing the import brings them back.
- Writing `capabilities` replaces the set: the role's conf stanza then has
  every unlisted default as `<capability> = disabled`.
Nothing was lost; the role kept every capability, reported elsewhere.

**Fix:** live tests assert the total (`capabilities` plus
`imported_capabilities`), and the app's README explains why such a cell shows
as inherited rather than ticked.

**Catch earlier:** never assert on a role's own `capabilities` alone after
changing its imports; compare the union. Do not assume a new role starts
empty.
