---
hits: 1
seen: [2026-11-14]
area: splunkd
level: pattern
---
**Symptom:** easyadmin 1.2.0 (App management). A second
`PersistentServerConnectionApplication` subclass (`AppsHandler`) was added to
`apps/easyadmin/bin/easyadmin_rest.py`. Unit tests were green, then the live
run at 2026-11-14T17:42:10 failed 89 of 92 tests with
`GET /services/easyadmin/apps failed: HTTP 500 Error starting: More than one
class implements PersistentServerConnectionApplication`. Both persist
endpoints in that script (roles and apps) were down, not just the new one.

**Cause:** splunkd's persistent-handler loader (seen on 10.6.1) scans the
script for subclasses of `PersistentServerConnectionApplication` and refuses
to start if it finds more than one, even though `restmap.conf` `handler =
<module>.<Class>` names exactly one. `from other_rest import SomeHandler`
counts too: an imported subclass is in the module namespace. Any app with two
persist endpoints can hit this.

**Fix:** one handler class per script: `bin/easyadmin_apps_rest.py` holds
`AppsHandler` only and imports the shared gateway as a module
(`import easyadmin_rest as roles_rest`, never `from easyadmin_rest import
...Handler`). The reason is in that file's docstring. Live green at 17:43:41
(one unrelated failure), all 92 at 17:44:53.

**Catch earlier:** unit tests cannot see it; only a live call to the endpoint
does. Recipe step in playbook `rest-endpoint-behind-page`.

**Pattern:** `rest-endpoint-behind-page` (step 3).
