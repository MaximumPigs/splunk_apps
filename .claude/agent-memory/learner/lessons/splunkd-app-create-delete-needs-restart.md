---
hits: 1
seen: [2026-11-14]
area: splunkd
level: pattern
---
**Symptom:** easyadmin 1.2.0. A probe live test created a throwaway app
(`POST /services/apps/local`) to move objects into, then deleted it
(`DELETE /services/apps/local/<name>`). After the DELETE splunkd reported
"restart required", so the target needed a restart (which always needs the
person) just to run the live tests.

**Cause:** creating or deleting an app is a splunkd change that only fully
applies after a restart. Any live test, in any app, that creates or deletes
apps leaves the target in that state on every run.

**Fix:** live tests never create or delete apps. Objects are moved between
`search` and `launcher`, two apps every instance has
(`tests/live/easyadmin/test_easyadmin_apps_live.py`, `APPS`), and the
`objects` fixture deletes them wherever the test left them.

**Catch earlier:** playbook `splunkd-knowledge-objects-rest` ("Live tests").
If this recurs, make it a `write-live-test` rule or a guard check on
`apps/local` writes.

**Pattern:** `splunkd-knowledge-objects-rest`.
