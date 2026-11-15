# Roadmap

What is planned for the apps in this repo, in priority order within each
app. Requirements are recorded as the owner gave them; open questions are
for settling before the work starts.

`splk loop` works through this file from top to bottom (see the README), so
its format is fixed:

- `## <app id>` per app, `## Tooling` for repo-wide work.
- `### <title>` per item, with `Status:` on the line below:
  `ready`, `in-progress`, `blocked`, `proposed` (from a code review, waiting
  for the owner) or `done`.
- Open questions are `- [ ] question`; answered ones `- [x] question: answer`.
  An item with an open question never starts, whatever its status says.
  The loop opens a GitHub issue per blocked item; answer there.

## easyadmin

### Done

| Version | What |
| --- | --- |
| 1.2.0 | App management page: apps as boxes of knowledge objects, move, re-permission and delete, staged and applied at once (#17). |
| 1.3.0 | Configuration precedence tab, btool-style (#19). |
| 1.4.0 | Copy objects into another app (the default for objects in a default folder); discard one staged change; the object's own settings in the panel; locks from splunkd's `removable` flag (#20). |
| 1.5.0 | Create a new app (barebones template), or clone one with copies of its copyable objects, staged as pending boxes and run by Apply; a restart notice only when splunkd asks (creating needs none on 10.6.1). |
| 1.6.0 | Edit the individual settings of a knowledge object from its panel: filter, copy, show the default value, edit and add settings, staged with the old and new value and written to the app's local configuration by Apply. No delete of a local setting: splunkd has no REST call for it. |
| 1.6.1 | The details panel, settings edits, app creation and the precedence view read only the caller's capabilities from splunkd, not the theme preference as well: one splunkd request fewer per details click. |

### 2. Export and import an app as JSON
Status: blocked

Part of the original request: the whole app as a JSON object that can be
uploaded or pasted into another instance, without packaging an app.
Agreed: an import is staged as pending changes (new, changed) and committed
with Apply; the person chooses the target app name. Lookup CSV contents are
included. Private user objects are in scope.

- Objects that cannot be written (props-based objects, tags, navigation
  menus, and lookup files if the probe says so) are still exported, and
  show on import as "cannot import" with the reason.
- "New" is absent from the target app and is created; "changed" exists in
  the target app with different settings and is overwritten (as a local
  override when it ships in the app's default folder). There is no
  "conflicting" state. Each can be discarded one by one before Apply.
- An object whose owner has no matching user on the target is imported with
  the importing admin as owner; roles the target lacks are dropped; each is
  flagged on the pending change.
- [x] An import writes objects the same way a copy does, so props-based
  objects, tags and navigation menus cannot be written (see the README), and
  lookup files may not be either (see the probe below). Options: (a) export
  them anyway and show them on import as "cannot import" with the reason;
  (b) leave them out of the export. Recommendation: (a), so the JSON is a
  complete record of the app and nothing is dropped silently. (Likely the
  same answer as the partial clone question in item 1.): (a).
- [x] What do "changed" and "conflicting" mean, and what does Apply do with
  each? Recommendation: "new" is absent from the target app and is created;
  "changed" exists in the target app with different settings and is
  overwritten (as a local override when it ships in the app's default
  folder); "conflicting" is a same-named object visible from another app,
  created anyway with a warning. Each can be discarded one by one before
  Apply, as staged changes already can.: "Conflicting" is not required;
  use only "new" and "changed".
- [x] When the target instance has no user matching an object's owner, or
  lacks a role named in its permissions, what happens? Recommendation: the
  object is imported with the importing admin as owner and the missing
  roles dropped, each flagged on the pending change.: Agreed, as
  recommended.
- [ ] Can the target app name be an app that does not exist yet? Options:
  (a) existing apps only; (b) a new name stages a create first, as 1.5.0's
  "create a new app" does (same fields, defaults from the JSON's app label,
  description, author and version, and the same restart notice).
  Recommendation: (b), so an app can be moved to another instance in one
  step; the create path already exists since 1.5.0.
- [ ] When the target app already exists, what happens to its objects that
  are not in the JSON? Options: (a) left alone (an import only creates and
  overwrites); (b) staged for deletion, so the target ends up matching the
  JSON. Recommendation: (a), since a delete is not undoable and the person
  can still stage deletes by hand on the page.
- [ ] When the target app already exists, are its app-level settings (label,
  description, version, visibility) changed to the JSON's? Options: (a) never,
  objects only; (b) staged as one "changed" entry for the app, discardable
  like any other. Recommendation: (a), keeping the import to knowledge
  objects; the label and version belong to whoever owns the target app.

Probe first: whether a lookup file's contents can be written through REST
or a search on 9.3 and 10.x without Splunk's upload staging folder (for
example `outputlookup` run in the target app's namespace), and the largest
JSON body the page's REST endpoint accepts (upload and paste).

### Low priority: Deployment apps portal
Status: blocked

A portal like App management, for the deployment server's apps.

- Every point below is in the first version, where possible. Report back
  to the owner on any point that cannot be built, or that could cause
  issues on the Splunk stack.
- Splunk Enterprise only. The page first confirms the instance is
  configured as a deployment server, and is hidden if it is not.
- [x] More requirements are to be gathered when this work starts: which of
  the points below are in the first version, and are you happy for it to be
  Splunk Enterprise only (files on the deployment server)?: All points,
  where possible; report back where something cannot be built or could
  cause issues on the Splunk stack. Enterprise only is fine, but first
  confirm the instance is configured as a deployment server, and hide the
  page if not.
- [ ] Every app in this repo must pass Splunk Cloud vetting, but this page
  writes files outside its own app (`deployment-apps`, `serverclass.conf`).
  If AppInspect's Cloud checks flag that, what then? Options: (a) a
  separate Enterprise-only app, exempt from the Cloud checks; (b) keep it in
  easyadmin and record the flagged checks as reviewed; (c) leave the file
  writes out (server classes through REST only). Recommendation: (a), so
  easyadmin stays clean for Splunk Cloud.
- [ ] Are changes staged and run by Apply, like App management, and does
  Apply also reload the deployment server (which pushes the changed apps to
  every matching client)? Recommendation: staged; Apply writes the files,
  then asks for a separate confirmation, naming how many clients are
  affected, before it reloads.
- [ ] Where are server class groups, backups and history kept? Options:
  (a) all in the KV store; (b) groups in the KV store, backups as archives
  of `deployment-apps` and `serverclass.conf` on disk under
  `$SPLUNK_HOME/var`; (c) all as files in the app's folder (lost when the
  app is upgraded). Recommendation: (b), since backups of app files can be
  large.
- [ ] This is several pages of work, too large to review as one PR. Options:
  (a) one item and one PR with every point; (b) split into items built and
  merged in order, released together or one by one: detection and a
  read-only view of `deployment-apps`, knowledge-object editing, the server
  class tabs, server class groups and precedence, export and import, backup
  and revert. Recommendation: (b), so each part can be reviewed on its own;
  all of them are still in the first version, as agreed.

Probe first: how to tell that the instance is a deployment server (for
example `deployment/server/config` or a configured `serverclass.conf`),
which AppInspect checks a file write outside the app's own folder trips,
and whether a navigation entry can be hidden per instance (app navigation
is static XML; if it cannot, report back to the owner with the fallback,
such as the page showing "not a deployment server" instead).

- The same ability to create, update, delete and move knowledge objects,
  working on the `deployment-apps` folder. Default settings can be modified.
- A tab of server classes, where apps can be dragged and dropped or copied
  between server classes.
- A tab to modify server class settings.
- Persistent "server class groups", with a page showing setting precedence
  within each group. For example, one group holds `base_app` and
  `windows_app`, another `base_app` and `linux_app`: every host gets
  `base_app`, then either the Windows or the Linux app, whose settings
  override `base_app`'s. Conflicts are not obvious without such groups.
- Export and import to JSON.
- Backup and revert.

Notes:

- Deployment apps are files on the deployment server, outside splunkd's
  knowledge-object REST API, so this means reading and writing files
  (Splunk Enterprise only; Splunk Cloud has no customer deployment server).
  Server classes have REST endpoints (`deployment/server/serverclasses`).
- Where groups, backups and history are stored (KV store, or files in the
  app): see the open question above.

## fillcontinuous

### Done

| Version | What |
| --- | --- |
| 1.1.2 | Real rows keep `_raw` and other `_` fields when a filled row is the first one written: the command registers every output field name with the record writer before yielding. |

## Tooling

### Proposed: Audit step can change code that is then pushed unverified
Status: interactive

`phase_audit` (`tools/splk/loop.py:500`) commits whatever the audit step
changed and goes straight to `publish`, with no `splk dev`/`splk test`. The
audit prompt says "Edit ROADMAP.md only", but unlike `phase_groom`, which
refuses anything else (`loop.py:459`, "Groom may only edit ROADMAP.md"),
nothing enforces it. In loop mode, `guard_files` blocks hooks, prompts and
`tools/splk`, but not `apps/`, so an audit step that "fixed" what it found
would have its app change committed as the owner and pushed in a roadmap PR
that no verify stage has seen. Fix: apply the groom check to the audit step
(only `ROADMAP.md` outside `.agent/`), with a unit test. Found by reading the
code. Not observed: no audit has gone wrong yet.

- [x] Confirm: should this be done? (Recommended: it is a one-line check like
  groom's. It changes `tools/splk/`, which loop steps may not edit, so it
  needs an interactive session.): Yes.

### Proposed: Question issues are closed before the groom PR that answers them is merged
Status: interactive

`phase_groom` runs the groom step with `main` checked out and calls
`sync_question_issues` (`tools/splk/loop.py:375-398`) before it creates the
`roadmap/groom-*` branch. Any issue whose item no longer has an open question
is closed at once, with the comment "Answers recorded in ROADMAP.md on branch
main" (`loop.py:397`, `git branch --show-current` at that moment). The answers
are not on main; they are on a branch waiting for the owner. If the owner
closes that PR instead of merging, the issue is already closed, and the next
groom opens a new issue for the same questions, so the earlier answer thread
is lost from view. Fix: close the issues after the groom PR merges (in
`phase_await` on `merged`), or name the real branch and PR in the comment.
Found by reading the code, not observed on GitHub.

- [x] Confirm: should this be done? (Recommended: close on merge. Interactive
  session, as above.): Close on merge.

### Proposed: Console errors without a source in `splk shot`, and the UX audit missing the app's own REST failures
Status: interactive

`PageLog._on_console` (`tools/splk/ui.py:150`) keeps only `message.text`, so
`splk shot easyadmin/app_management` reports six bare "Failed to load
resource: ... 404" lines, with nothing to say whether they are the app's.
The UX audit does keep the URL, and its report showed all six were Splunk
Web's own `configs/conf-limits/structured_data_service` (the search app's
search page shows five of the same). Separately, `own_console_errors`
(`tools/splk/ux.py:234`) treats an error as the app's only when it points at
`/static/app/<app>/`. A failing call to the app's own REST endpoint
(`/splunkd/__raw/services/<app>/...`, say a 500 from the details panel or the
precedence tab) is not counted, so it would pass the audit. Fix: record the
URL in `PageLog` and print it in `splk shot`; also match
`/splunkd/__raw/services/<app>/` in `own_console_errors`, with unit tests.
The second half is inferred from the code: no app endpoint has failed during
an audit yet.

- [x] Confirm: should this be done? (Recommended: the URL in `splk shot` at
  least, since CLAUDE.md relies on it to "look before you claim". Interactive
  session, as above.): Yes.
