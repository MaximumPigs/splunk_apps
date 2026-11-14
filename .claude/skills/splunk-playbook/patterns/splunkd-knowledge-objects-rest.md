---
confirmed: 1
seen: [2026-11-14]
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
8. Apply edits in order move, then acl, per object, and report a result per
   object: after a move the object's path changes, so the acl call uses the
   new app (`easyadmin_apps_core`).

**Live tests:** never create or delete apps; `DELETE /services/apps/local`
leaves splunkd needing a restart
(`lessons/splunkd-app-create-delete-needs-restart.md`). Move throwaway
`splktest_*` objects between `search` and `launcher` and delete them wherever
the test left them (fixture `objects`).

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
