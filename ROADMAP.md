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
| 1.6.2 | A box counts the copies staged into it ("0 objects, 60 staged") and says how many staged copies, moves and deletions the Types menu or name filter keep out of its list; the settings list, its labels and code use the page's body font size. |

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

### Proposed: No cap on the total size of one settings Apply
Status: in-progress

Left by the security review on #39 (1.6.0), low. Each object may carry 200
settings of up to 64 KB (`easyadmin_apps_core.py:365-367`, checked at
`:659-687`), and one Apply may hold 2000 changes (`MAX_CHANGES`, `:106`), so
one request can ask splunkd for gigabytes of writes. Only a caller with
`admin_all_objects` reaches it, so the harm is self-inflicted load. Fix: a
total byte cap across the request, refused with a clear message, plus a
unit test.

Agreed: probe, then set the cap. The person sees the error when they stage
the first change that takes the total above the cap, not at Apply; the
server-side refusal stays as the backstop.

- [x] Confirm: should this be done? (Recommended: yes, small and cheap; the
  web server's own body limit may already stop it, so probe that first.):
  Yes, probe and set the cap, but show the error when the first change above
  the cap is staged, not at Apply.

Probe first: the largest request body the page's REST endpoint accepts
through Splunk Web on the dev target, so the cap sits below it and the
staging check measures the same size the server counts.

### Proposed: Tests the settings panel still lacks
Status: ready

Left on #39 (1.6.0). No UI test covers the hint on masked or too-long
settings, nor staged settings staying listed under a filter; no live test
proves Apply refuses a setting called `name` (the reserved keys,
`easyadmin_apps_core.py:642`, are unit-tested only). Left on #40 (1.6.1):
the live test that the details panel no longer reads `user-prefs`
(`tests/live/easyadmin/test_easyadmin_apps_live.py:347-362`) depends on
`_internal` indexing lag, so it can pass falsely. Fix: the three tests, and
make the `user-prefs` check wait for a later marker request before
asserting absence.

- [x] Confirm: should this be done? (Recommended: yes, tests only, no
  behaviour change.): Yes, add the tests.

### Staged moved knowledge objects should not disappear from their origin app
Status: ready

- Knowledge Objects staged for move should display in the origin app 
  with a strike-through as though they are being deleted.
- Today a staged move lists the object only in its destination app
  (`appOf`, `easyadmin_apps.js:265-268`); it stays listed there as now.

### Local knowledge objects should be able to be deleted even when a default one exists under it.
Status: blocked

- Currently, no local knowledge object with a default one under it can be deleted from the app.
- The option to delete the local one should be available.

Already observed on 10.6.1 (README, "Why local settings cannot be
deleted"): `DELETE .../configs/conf-<file>/<stanza>` on an object that ships
in `default` is refused ("cannot be deleted in config"), and splunkd marks
such objects `removable` 0, so the typed endpoints refuse it too. No REST
call seen so far removes only the local layer.

- [ ] If the probe below finds no REST call that removes only the local
  layer, what then? Options: (a) drop the item, and say in the lock's
  tooltip and the README that the object has local changes that only an
  edit of the `local` file can remove; (b) a "reset to default" that posts
  each local setting's default value back (observed: the key stays in
  `local`, pinned to today's default, so a later app upgrade's new default
  is hidden); (c) delete the local stanza from the file (not possible on
  Splunk Cloud, fails vetting). Recommendation: (a), since (b) looks like a
  revert but is not one. If a REST call is found, the delete reverts the
  object to its default settings and leaves its permissions as they are.
  Agree?

Probe first: `DELETE` on the typed endpoint (for example
`saved/searches/<name>`) and on `configs/conf-<file>/<stanza>` for an object
with both a default and a local stanza, on 9.3 and 10.6, reading the
`local` file back through splunkd afterwards.

### Delete single setting from knowledge object by removing whole knowledge object and recreating.
Status: blocked

- There is no DELETE operation for stanza settings through the API
- In place of this, explore the viability of caching the local knowledge object, deleting the whole object
  then recreating without the deleted setting.
- Review this for security or functionality implications and raise issues before planning implementation.

Issues raised from the code and the README (to be confirmed by the probes
below, not yet observed):

- Only objects with no `default` layer can be handled: splunkd refuses to
  delete one that ships in `default` (see the item above), so its local
  settings stay undeletable.
- Only the types a copy can write: props-based objects, tags, navigation
  menus and lookup files are excluded for the same reasons as copying.
- splunkd's GET returns the merged settings (the stanza's own keys plus
  `[default]` and system defaults). Recreating from them would write every
  inherited value into `local`; the recreate must post only the stanza's own
  keys, which the page cannot yet tell apart.
- Between the delete and the create the object does not exist: a scheduled
  search due in that gap is skipped, and other users get "not found".
- A recreated saved search may lose scheduler state kept by name (alert
  throttling, next run time); its permissions and owner must be restored as
  a copy does.
- If the create fails after the delete, the object is gone: Apply must
  recreate the cached original and, if that fails too, show the cached
  settings so the person can restore it by hand.
- `_audit` records a delete and a create, not an edit; the app's own log
  line should name it as one setting removal.
- Security: the caller needs both delete and create rights on the object,
  with their own session token, as every other write; no new privilege.

- [ ] Given the issues above, build it? Options: (a) yes, for local-only
  objects of copyable types, with the staged change and the Apply
  confirmation saying the object is deleted and recreated (and, for a
  scheduled search, what is reset); (b) as (a), but refuse scheduled
  searches and alerts; (c) do not build it, and keep the README's advice to
  edit the `local` file. Recommendation: (a), once the probes show the
  recreate writes only the stanza's own keys.

Probe first: whether splunkd can list a stanza's own keys apart from
inherited ones (the precedence tab's reader, or `configs/conf-<file>` with
`list_inherited` or similar); what a deleted and recreated scheduled search
keeps (`next_scheduled_time`, alert suppression); on 9.3 and 10.6.

### Proposed: No screenshot shows the "hidden by the filters" note
Status: proposed

Left by the splunk-reviewer on #51 (1.6.2), low. In
`test_a_clone_box_counts_its_staged_copies_and_those_the_filters_hide`
(`tests/ui/easyadmin/test_easyadmin_apps_ui.py:793`) the
`app_management_clone_counts` screenshot is taken before the name filter
is applied, and with the common types every copy is listed, so no image
shows the `.ea-hidden-staged` note; the test asserts its text only. Fix: a
second `shot` after the name filter, and open it. Tests only.

- [ ] Confirm: should this be done? (Recommended: yes, one line; it could
  join "Tests the settings panel still lacks".)

## fillcontinuous

### Done

| Version | What |
| --- | --- |
| 1.1.2 | Real rows keep `_raw` and other `_` fields when a filled row is the first one written: the command registers every output field name with the record writer before yielding. |

### Proposed: `power` can change the command stanzas
Status: ready

Left by the security review on #41 (1.1.2), low, predating that change.
`metadata/default.meta` grants `write : [ admin, sc_admin, power ]` on `[]`
and `[commands]`, while its own comment says "writable only by admins". A
`power` user can change or unexport the commands for everyone. Fix: drop
`power` from both write lists, and check AppInspect stays clean.

- [x] Confirm: should this be done? (Recommended: yes, admins only, as the
  file's comment already says.): Admins only.

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

### Proposed: The UX audit covers only the theme the signed-in user prefers
Status: interactive

On #38, #39 and #40 the UX audit ran in dark only: `tools/splk/ux.py` asks
for each theme with `?theme=`, but a page that follows the user's preference
refuses it, and the audit records the theme Splunk actually drew (`ux.py:8-9`).
The light theme of easyadmin has gone unaudited for three releases (four
with #51, 1.6.2, where the UX review left the new muted `.ea-hidden-staged`
note, `easyadmin_apps.css:259`, unseen in light for the same reason). The
audit also never opens a panel, so the settings panel added in #39 has no
audit at all. Fix: switch the test user's theme preference through `sandbox`
for each pass (restored afterwards), and let an app list panels to open per
view. Changes `tools/splk/`, so it would be built in an interactive session.

- [x] Confirm: should this be done? (Recommended: yes, the theme switch at
  least; CLAUDE.md's definition of done assumes both themes are audited.):
  Yes.

### Proposed: One failed `git pull` after a merge leaves the loop stuck until resumed
Status: interactive

On 2026-11-15T19:43:24Z, after #41 merged, the loop notified "Loop stuck in
await: git pull -q failed: error: cannot lock ref 'refs/remotes/origin/main':
is at 593ef36 but expected 809be99" (loop log since the groom of
20261115-212527). Another git process had moved `origin/main` to #41's merge
while the pull was updating it (most likely the editor's background fetch;
inferred, not observed). `phase_await` (`tools/splk/loop.py:749-751`) runs
`git checkout`/`git pull --ff-only` with `check=True`, `run` turns any
non-zero exit into a `LoopError` (`loop.py:238-239`), and `run_loop` treats
every `LoopError` as stuck: it pauses and waits for the owner
(`loop.py:897-902`). The merge had already happened and the phase is safe to
repeat, so a retry a few seconds later would have carried on without the
owner. Fix: retry the post-merge `git pull` (and other read-only git calls in
`await`) a few times with a short wait before raising, with a unit test.
Changes `tools/splk/`, so it would be built in an interactive session.

- [x] Confirm: should this be done? (Recommended: yes, a small retry; it
  costs nothing when git succeeds, and a ref race should not need the owner.):
  Yes.

### Proposed: A fix for owner feedback reaches the PR with no security or UX review
Status: proposed

On #51, the owner asked for staged moves and deletions to be counted too.
The fix step (`.agent/loop/steps/20261116-085329-fix.json`) changed
`easyadmin_apps.js` and the CSS, `splk dev easyadmin` was green, and the
branch was pushed; the last security and UX reviews in the run log are from
08:17 and 08:18, before the fix (`.agent/runs/2026-11-16.jsonl`). After a
fix, `phase_fix` goes to `verify` with `after_verify="push"`
(`tools/splk/loop.py:776-786`), and `phase_push` (`:788-804`) pushes without
a review step and without notifying the owner, so the only notification for
#51 was "ready to merge" from before the fix. CLAUDE.md's definition of done
(items 5 and 6) wants a review recorded for every code change. Fix: after a
fix that changed files under `apps/`, run the review step before `push`, and
notify "PR #N updated" after the push, with unit tests. Changes
`tools/splk/`, so it would be built in an interactive session.

- [ ] Confirm: should this be done? (Recommended: yes; the fix after owner
  feedback is often the larger change, as on #51.)

### Proposed: The implement step is not told to see a new test fail first
Status: proposed

On #51 the implement step reported "I edited the JS before running the new
UI test, so there is no before-failure recorded for it"
(`.agent/loop/steps/20261116-080830-implement.json`). CLAUDE.md asks to
"prove a fix closes the original reproduction, before and after", but
`.claude/loop/prompts/implement.md` lists only the definition of done items
1 to 4; it says nothing about running the new tests against the old code.
The plan for #40 asked for "a live test that must fail before the fix and
pass after it" (`20261115-192038-plan.json`) and that run had the evidence;
the #51 plan did not, and the step skipped it. Fix: one line in
`implement.md` (and `plan.md`): write the new unit, live or UI test first
and record it failing on the current code before changing the app, unless
the item adds something that did not exist. Changes `.claude/loop/`, so it
would be built in an interactive session.

- [ ] Confirm: should this be done? (Recommended: yes, a prompt line; it
  costs one extra test run per item.)
