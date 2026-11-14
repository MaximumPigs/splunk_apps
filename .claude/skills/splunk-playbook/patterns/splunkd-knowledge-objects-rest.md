---
confirmed: 2
seen: [2026-11-14, 2026-11-14]
apps: [easyadmin]
---
# List, move and re-permission knowledge objects through splunkd REST

**Use when:** app code or a live test lists knowledge objects across apps
(reports, dashboards, macros, lookups...), moves them between apps, changes
their owner or sharing, or deletes them. Everything below was observed on
Splunk 10.6.1 and is pinned by `tests/live/easyadmin/test_easyadmin_apps_live.py`.

**Recipe:**

1. List each type from its own collection:
   `GET /servicesNS/-/-/<endpoint>?count=0&f=disabled`. `count=0` returns
   all; `f=disabled` trims `content` to one field (a dashboard's XML is
   otherwise in every entry). Keep `acl` and `links` from each entry. The
   type registry (id, label, endpoint) is `TYPES` in
   `apps/easyadmin/bin/easyadmin_apps_core.py`.
2. Do **not** use `admin/directory` for a complete list: it omits
   `data/lookup-table-files`, `datamodel/model` and `data/props/calcfields`.
3. Read what splunkd allows from each entry's `links`, not from the user's
   role: no `move` link means it cannot be moved, no `remove` link means it
   cannot be deleted. Objects in an app's `default/` have neither, and a move
   of one is refused with HTTP 400 "cannot be deleted and thus it cannot be
   moved". Lookup table files do have both.
4. The namespace is the user part of the entry id
   (`/servicesNS/<ns>/<app>/...`): `nobody` for shared objects, the owner for
   private ones. Admin sees other users' private objects under `/-/-`.
   A GET of `/servicesNS/<ns>/<app>/<endpoint>/<name>` returns any object
   **visible** from `<app>`, including global ones from other apps and
   `etc/system`: accept it only if `acl.app == <app>` (`get_in_app()`), before
   any move, acl, delete, details or "already exists" check
   (`lessons/splunkd-namespace-get-returns-visible-objects.md`).
5. Move: `POST <object>/move` with `app=<target>`, `user=<ns>`. Owner and
   sharing are kept, private objects included.
6. Permissions: `POST <object>/acl` **always** with `sharing` (HTTP 400
   without it), plus `owner`, `perms.read`, `perms.write` as comma-joined
   role lists. An empty `perms.write` reads back as `['']`: normalise it to
   `[]` (`as_list`). Sharing a private object to `app` moves it to
   namespace `nobody`, so re-key it.
7. Apps: `GET /services/apps/local?count=0`; `content.core = 1` marks the
   apps Splunk ships. Objects in `etc/system` report `acl.app = system`,
   which is not an app: never offer it as a move target.
8. Copy: post only the names in the entry's `fields` (`required`,
   `optional`, or matching a `wildcard` pattern), plus `eai:data` and no other
   `eai:*`, booleans and numbers as text, to
   `/servicesNS/<ns>/<target>/<endpoint>`; then set the ACL. If the ACL
   fails, delete the copy and report it not copied. Verified live: macros,
   views (`eai:data`), a `default/` macro; by probe: saved searches, event
   types, transforms, lookup definitions, workflow actions, times, data
   models, collections. **Not copyable** (`"copy": None`): props-based
   objects and tags (`lessons/splunkd-props-tags-copy-unreliable.md`),
   lookup table files, navigation.
9. Apply edits in order (copy or move), then acl, per object, and report a result per
   object: after a move the object's path changes, so the acl call uses the
   new app; return `copied_to`/`moved_to` even when the acl step fails, so the
   page keeps only the failed edit staged (`easyadmin_apps_core`).

**Live tests:** never create or delete apps; `DELETE /services/apps/local`
leaves splunkd needing a restart
(`lessons/splunkd-app-create-delete-needs-restart.md`). Move throwaway
`splktest_*` objects between `search` and `launcher` and delete them wherever
the test left them (fixture `objects`).

**Page:** a staged copy shows as a ghost row in the target app (dashed,
italic, no tick box, not counted); every path (drag, selection bar, panel)
stages through one function (`stageTransfer` in `easyadmin_apps.js`), which
also runs the name-clash check.

**Why this way:** `admin/directory` looked like the one-call answer and was
incomplete; links are splunkd's own verdict per object, so the page never
offers an action splunkd will refuse; the `['']` read-back failed
`test_empty_write_list_clears_write_roles` before normalising. Calls go
through the caller's session (`rest-endpoint-behind-page`).

**Verify:** live tests that read back app, owner, sharing and perms after
each write, a refused move of a `default/` object, a private object moved
and shared, and a user without rights refused.

**Reference:** `apps/easyadmin/bin/easyadmin_apps_core.py`,
`apps/easyadmin/bin/easyadmin_apps_rest.py` (gateway),
`tests/test_easyadmin_apps_core.py`,
`tests/live/easyadmin/test_easyadmin_apps_live.py`.
