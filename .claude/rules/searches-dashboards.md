---
paths:
  - "apps/**/savedsearches.conf"
  - "apps/**/macros.conf"
  - "apps/**/eventtypes.conf"
  - "apps/**/tags.conf"
  - "apps/**/data/ui/**"
---

# Searches, macros and dashboards

- Never hard-code an index in a saved search or dashboard: use a macro
  (e.g. `` `<app>_index` ``) so customers can override it.
- Every macro and saved search that returns data has a live test asserting the
  result shape on synthetic input (`| makeresults`) or seeded test-index data.
- Saved searches ship `enableSched = 0` and alerts disabled unless the app's
  purpose is that schedule.
- Prefer `tstats` over raw searches where the data model supports it; note the
  reason in a comment when you cannot.
- Dashboards: Dashboard Studio (JSON definition in XML) for new dashboards.
  Every panel's search references macros, not raw indexes.
- No inline `<script>` or external resources in dashboards: AppInspect fails them.
