---
hits: 2
seen: [2026-11-14, 2026-11-15]
area: splunkd
level: pattern
---
**Symptom:** easyadmin 1.2.0. A probe live test created a throwaway app
(`POST /services/apps/local`) to move objects into, then deleted it
(`DELETE /services/apps/local/<name>`). After the DELETE splunkd reported
"restart required", so the target needed a restart just to run the live
tests. (Restarting the dev target no longer needs the person, since the
owner's commit 0cb296d, but a test that forces a restart each run is still
slow and leaves other targets dirty.)

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

**Exception (2026-11-15):** easyadmin 1.5.0 builds app creation, so
`tests/live/easyadmin/test_easyadmin_app_create_live.py` creates ONE throwaway
app per run and restarts the dev target in teardown only if splunkd asks. It
is the only module allowed to; each run costs a restart. Any new live test
that creates apps must reuse that fixture, not add its own.

**Pattern:** `splunkd-knowledge-objects-rest`.
