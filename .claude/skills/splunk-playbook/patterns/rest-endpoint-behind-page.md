---
confirmed: 1
seen: [2026-11-12]
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
2. `default/web.conf`, `[expose:<app>_<name>]`: `pattern = <app>/<name>` and
   only the methods used (`GET, POST`). Without it the browser gets a 404.
3. `bin/<app>_rest.py`: a thin `PersistentServerConnectionApplication` that
   adapts the request and makes the splunkd calls with the caller's session
   token. Everything else goes in `bin/<app>_core.py`, behind a gateway
   interface the unit tests fake.
4. Call splunkd with `splunk.rest.simpleRequest`. To repeat or clear a form
   field, pass `postargs={field: [v1, v2]}` or `{field: ""}`, never a list of
   pairs. URL-quote every name you put in a path (`quote(name, safe="")`).
5. Log to `$SPLUNK_HOME/var/log/splunk/<app>.log` (indexed into `_internal`),
   which is the audit trail of the changes it made.

**Why this way:**
- The caller's own token (no `passSystemAuth`) means splunkd enforces the
  user's capabilities, so the app can never grant more than Settings would.
- `persist` handlers keep their process alive. After changing `bin/`, a green
  deploy can serve the old code for minutes: restart (ask the person) or
  wait, and confirm which code is running from the app's log
  (`lessons/splk-persist-handler-stale-code.md`). A new endpoint needs one
  restart before it is registered at all.
- `simpleRequest` calls `.items()` on `postargs`
  (`lessons/python-simplerequest-postargs-dict.md`).
- splunkd returns numbers in REST JSON where `| rest` gives strings, and stores
  role lists sorted: normalise at the boundary and compare lists as sets
  (`lessons/splunkd-json-numbers-vs-rest-search.md`,
  `lessons/splunkd-role-index-lists-sorted.md`).

**Verify:** unit tests over `<app>_core` with a fake gateway; live tests that
call the endpoint through `splunk.request` and touch only throwaway objects
created and deleted by the test; a UI test that the page loads the data.
Run the `splunk-security-review` skill: these endpoints are the app's attack
surface.

**Reference:** `apps/easyadmin/default/restmap.conf`, `default/web.conf`,
`bin/easyadmin_rest.py`, `bin/easyadmin_core.py`,
`tests/live/easyadmin/test_easyadmin_live.py`.
