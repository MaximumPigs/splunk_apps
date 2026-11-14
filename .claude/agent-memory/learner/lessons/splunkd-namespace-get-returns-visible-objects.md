---
hits: 1
seen: [2026-11-14]
area: splunkd
level: pattern
---
**Symptom:** easyadmin 1.4.0 (copy objects into another app). The "already
exists in the target app" check for a copy said yes for objects that were
not in the target: `GET /servicesNS/<ns>/launcher/<endpoint>/<name>`
answered with the search app's globally shared view and macros, and with a
props extraction from `etc/system`. Live runs from 22:22:07 failed
`test_copy_keeps_sharing_and_a_dashboards_source` (`assert 0 == 1`).

**Cause:** a GET under `/servicesNS/<ns>/<app>/` returns any object
**visible** from that app, not only objects that live in it. Anything shared
globally (from another app or `etc/system`) is visible from every app. Every
read-then-act by name had the same latent defect: move, acl, delete and
details in `easyadmin_apps_core` could have acted on another app's object
with the same name. Any code in any app that addresses an object by
`/servicesNS/<ns>/<app>/.../<name>` and assumes it is in `<app>` is exposed.

**Fix:** `get_in_app()` in `apps/easyadmin/bin/easyadmin_apps_core.py`
accepts the result only when its `acl.app` equals the app asked for,
otherwise a 404. Used by every per-object action. Unit-tested with a
`VisibleGateway` fake in `tests/test_easyadmin_apps_core.py` that answers
for shared objects from any app, as splunkd does.

**Catch earlier:** test fakes must copy splunkd's visibility, not a flat
dict keyed by path. Playbook `splunkd-knowledge-objects-rest` step 4.

**Pattern:** `splunkd-knowledge-objects-rest`.
