---
confirmed: 4
seen: [2026-11-12, 2026-11-14, 2026-11-14, 2026-11-14]
apps: [easyadmin]
---
# REST endpoint behind a page

**Use when:** a page needs to read or change splunkd state (roles, indexes,
conf) through the app's own Python, with the signed-in user's permissions.

**Recipe:**

1. `default/restmap.conf`, `[script:<app>_<name>]`: `match = /<app>/<name>`,
   `scripttype = persist`, `handler = <module>.<Class>`,
   `requireAuthentication = true`, `output_modes = json`, `passPayload = true`
   (for a JSON body), and both `python.version = python3` and
   `python.required = 3.9, 3.13`. Leave `passSystemAuth` at its default (false).
   For an admin-only endpoint add `capability = <cap>` and re-check it in core
   from `current-context`, so unit tests cover the refusal
   (`[script:easyadmin_conf]`).
2. `default/web.conf`, `[expose:<app>_<name>]`: `pattern = <app>/<name>` and
   only the methods used (`GET, POST`). Without it the browser gets a 404.
3. `bin/<app>_rest.py`: a thin `PersistentServerConnectionApplication` that
   adapts the request and makes the splunkd calls with the caller's session
   token. Everything else goes in `bin/<app>_core.py`, behind a gateway
   interface the unit tests fake. **One handler class per script**: a second
   endpoint gets its own `bin/<app>_<name>_rest.py`, and shares code by
   importing the other script as a module (`import <app>_rest as roles_rest`),
   never `from <app>_rest import <Handler>`.
4. Call splunkd with `splunk.rest.simpleRequest`. To repeat or clear a form
   field, pass `postargs={field: [v1, v2]}` or `{field: ""}`, never a list of
   pairs. URL-quote every name you put in a path (`quote(name, safe="")`).
5. Log to `$SPLUNK_HOME/var/log/splunk/<app>.log` (indexed into `_internal`),
   which is the audit trail of the changes it made.

**Why this way:**
- splunkd refuses to start a persist script that holds more than one
  `PersistentServerConnectionApplication` subclass, defined or imported,
  whatever `handler =` names: HTTP 500 "Error starting: More than one class
  implements PersistentServerConnectionApplication", and every endpoint in
  that script goes down. Only a live call shows it
  (`lessons/splunkd-persist-one-handler-class-per-script.md`).
- The caller's own token (no `passSystemAuth`) means splunkd enforces the
  user's capabilities, so the app can never grant more than Settings would.
- `persist` handlers keep their process alive. After changing `bin/`, a green
  deploy can serve the old code for 2 to 10 minutes (seen in three sessions). `splk
  deploy --restart` does **not** help: it restarts only when splunkd posts
  "restart required", which a Python change never does. Wait, and prove the
  new code runs with something only it shows (a label, a message) before
  trusting a test run (`lessons/splunkd-persist-handler-stale-code.md`). A
  new endpoint needs one restart before it is registered at all; after it,
  token calls can return 401 for about 30 s, so run `splk doctor` until it
  passes before the live stage (`lessons/splk-token-auth-lags-restart.md`).
- `simpleRequest` calls `.items()` on `postargs`
  (`lessons/python-simplerequest-postargs-dict.md`).
- splunkd returns numbers in REST JSON where `| rest` gives strings, and stores
  role lists sorted: normalise at the boundary and compare lists as sets
  (`lessons/splunkd-json-numbers-vs-rest-search.md`,
  `lessons/splunkd-role-index-lists-sorted.md`). For roles specifically, follow
  `splunkd-roles-rest-api`.

**Verify:** unit tests over `<app>_core` with a fake gateway; live tests that
call the endpoint through `splunk.request` and touch only throwaway objects
created and deleted by the test; a UI test that the page loads the data.
Run the `splunk-security-review` skill: these endpoints are the app's attack
surface.

**Reference:** `apps/easyadmin/default/restmap.conf`, `default/web.conf`,
`bin/easyadmin_rest.py`, `bin/easyadmin_core.py`, `bin/easyadmin_apps_rest.py`
and `bin/easyadmin_conf_rest.py` (one script each),
`tests/live/easyadmin/test_easyadmin_live.py`.
