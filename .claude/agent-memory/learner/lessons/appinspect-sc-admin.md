---
hits: 1
seen: [2026-09]
area: appinspect
level: rule
---
**Symptom:** `check_kos_are_accessible` failed.

**Cause:** `default.meta` granted write to `admin` only; that role does not
exist for Splunk Cloud customers.

**Fix:** Every write list with `admin` also has `sc_admin`.

**Catch earlier:** Promoted to `.claude/rules/conf-files.md`, `new-app` and
`appinspect-fix`.
