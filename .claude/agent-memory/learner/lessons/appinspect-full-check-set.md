---
hits: 1
seen: [2026-09-06]
area: appinspect
level: rule
---
**Symptom:** A package that passed `--included-tags cloud` AppInspect was
rejected on Splunkbase upload.

**Cause:** `check_for_updates_disabled` is tagged `private_app`, not `cloud`,
so the tag-filtered run (246 of 252 checks at the time) never ran it.

**Fix:** CI and `splk inspect` run the full, untagged check set; `app.conf`
leaves `check_for_updates` unset.

**Catch earlier:** Promoted to `.claude/rules/conf-files.md` and the
`appinspect-fix` skill. Seeded from the CI comments in `.github/workflows/ci.yml`.
