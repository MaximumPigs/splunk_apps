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
| 1.6.3 | One Apply is capped at 16 MB of request body: the server refuses a larger one with HTTP 413 before anything is written, and the page refuses, at the click that would take the staged changes over it, and puts the staged state back (the editor, form or panel stays open with what was typed). Splunk Web passed 64 MB bodies in a probe and splunkd allows 2 GB, so the cap is the app's own. |
| 1.6.3 (tests only) | Tests for the settings panel: the hint on masked and too-long settings, staged settings staying listed under a filter, Apply refusing a setting called `name` or `sharing`; the check that the details panel does not read `user-prefs` now waits for a later marker request before asserting absence. No change to the app. |
| 1.6.4 | A staged move also shows in the app the object is leaving, struck through and labelled "moving to <app>", with its own ×; filters hiding it are counted there as a "staged move away". |

Not built (owner's decision, 2026-11-16, #53): deleting a single setting by
deleting the whole knowledge object and recreating it without that setting.
The issues raised, from the code and the README (not observed by a probe),
are kept here as the record:

- Only objects with no `default` layer could be handled: splunkd refuses to
  delete one that ships in `default`, so its local settings stay undeletable.
- Only the types a copy can write: props-based objects, tags, navigation
  menus and lookup files are excluded for the same reasons as copying.
- splunkd's GET returns the merged settings (the stanza's own keys plus
  `[default]` and system defaults). Recreating from them would write every
  inherited value into `local`; the recreate would have to post only the
  stanza's own keys, which the page cannot yet tell apart.
- Between the delete and the create the object does not exist: a scheduled
  search due in that gap is skipped, and other users get "not found".
- A recreated saved search may lose scheduler state kept by name (alert
  throttling, next run time); its permissions and owner would have to be
  restored as a copy does.
- If the create failed after the delete, the object would be gone: Apply
  would have to recreate the cached original and, if that failed too, show
  the cached settings so the person could restore it by hand.
- `_audit` would record a delete and a create, not an edit.
- Security: the caller would need both delete and create rights on the
  object, with their own session token; no new privilege.

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
- [ ] Since 1.6.3 one Apply is capped at 16 MB of request body, and an
  import carries lookup CSV contents, so a large app's import can exceed
  it. What then? Options: (a) refuse the import when staging it would take
  the staged changes over the cap, naming the size, so the person discards
  some objects (for example a large lookup) and imports the rest; (b) Apply
  sends an import in several requests under the cap, so a failure part-way
  leaves the target app half imported; (c) a higher cap for imports only.
  Recommendation: (a), the same refusal at staging that 1.6.3 already
  shows, and nothing is written half-way.

Probe first: whether a lookup file's contents can be written through REST
or a search on 9.3 and 10.x without Splunk's upload staging folder (for
example `outputlookup` run in the target app's namespace). The body size is
settled: the 1.6.3 probe saw Splunk Web pass 64 MB bodies to the endpoint
and splunkd allows 2 GB, so the app's own 16 MB cap is the limit.

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

### Staged moved knowledge objects should not disappear from their origin app
Status: done

- Knowledge Objects staged for move should display in the origin app 
  with a strike-through as though they are being deleted.
- Today a staged move lists the object only in its destination app
  (`appOf`, `easyadmin_apps.js:266`); it stays listed there as now.

### Local knowledge objects should be able to be deleted even when a default one exists under it.
Status: ready

- Currently, no local knowledge object with a default one under it can be deleted from the app.
- The option to delete the local one should be available.
- Agreed: if the probe below finds no REST call that removes only the
  local layer, the delete is not built; instead the lock's tooltip and the
  README say the object has local changes that only an edit of the `local`
  file can remove. If a call is found, the delete reverts the object to its
  default settings and leaves its permissions as they are; how that staged
  revert shows on the page is then a question for the owner before it is
  built.

Already observed on 10.6.1 (README, "Why local settings cannot be
deleted"): `DELETE .../configs/conf-<file>/<stanza>` on an object that ships
in `default` is refused ("cannot be deleted in config"), and splunkd marks
such objects `removable` 0, so the typed endpoints refuse it too. No REST
call seen so far removes only the local layer.

- [x] If the probe below finds no REST call that removes only the local
  layer, what then? Options: (a) drop the item, and say in the lock's
  tooltip and the README that the object has local changes that only an
  edit of the `local` file can remove; (b) a "reset to default" that posts
  each local setting's default value back (observed: the key stays in
  `local`, pinned to today's default, so a later app upgrade's new default
  is hidden); (c) delete the local stanza from the file (not possible on
  Splunk Cloud, fails vetting). Recommendation: (a), since (b) looks like a
  revert but is not one. If a REST call is found, the delete reverts the
  object to its default settings and leaves its permissions as they are.
  Agree?: Agreed, (a).

Probe first: `DELETE` on the typed endpoint (for example
`saved/searches/<name>`) and on `configs/conf-<file>/<stanza>` for an object
with both a default and a local stanza, on 9.3 and 10.6, reading the
`local` file back through splunkd afterwards.

### Proposed: No screenshot shows the "hidden by the filters" note
Status: ready

Left by the splunk-reviewer on #51 (1.6.2), low. In
`test_a_clone_box_counts_its_staged_copies_and_those_the_filters_hide`
(`tests/ui/easyadmin/test_easyadmin_apps_ui.py:793`) the
`app_management_clone_counts` screenshot is taken before the name filter
is applied, and with the common types every copy is listed, so no image
shows the `.ea-hidden-staged` note; the test asserts its text only. Fix: a
second `shot` after the name filter, and open it. Tests only.

- [x] Confirm: should this be done? (Recommended: yes, one line; it could
  join "Tests the settings panel still lacks".): Yes. ("Tests the settings
  panel still lacks" has since shipped, so this is its own item.)

### Proposed: The marker wait in the `user-prefs` check rests on an unobserved ordering
Status: proposed

Left by the splunk-reviewer on #58 (tests only), low. `wait_for_marker`
(`tests/live/easyadmin/easyadmin_live_support.py:99`), used by the check
that the details panel does not read `user-prefs`
(`tests/live/easyadmin/test_easyadmin_apps_live.py:391-416`), assumes
`splunkd_access.log` is indexed in file order, so that once the marker
request is searchable any earlier `user-prefs` request would be too. Both
docstrings say the ordering is inferred, not observed. If a marker were
searchable before an earlier line, the absence assertion could pass
falsely. Fix: observe the ordering over several runs (a probe sending a
burst of requests and checking they become searchable in order); if it
holds, record it as observed in the comments; if not, poll one more cycle
after the marker before asserting absence. Tests only.

- [ ] Confirm: should this be done? (Recommended: yes, a probe and at most a
  one-line change; it closes the last inferred step in that test.)

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

### Done

| Change | What |
| --- | --- |
| Loop | The audit step may only edit ROADMAP.md, as groom may; anything else stops the loop before a commit. |
| Loop | A question issue is closed only once main no longer asks its questions, so a groom PR closed unmerged leaves the thread open. |
| Loop | In `await`, a failed `gh pr view` or post-merge `git checkout`/`pull` is retried every 30 s; the loop is stuck only after 20 minutes of failures. |
| Loop | A fix that changes `apps/` goes through the review step (scoped to the fix's commits) before the push, and every push after a fix notifies "PR #N updated". |
| Loop prompts | Plan and implement say to see each new test fail on the current code first, and to record it in the PR body. |
| `splk shot`, UX audit | Console errors carry their source URL; the audit also blocks on errors from the app's own REST endpoints (`/splunkd/__raw/services/<app>/`). |
| UX audit | Each theme is a pass with the signed-in user's theme preference set through `sandbox` and put back; views list panels and other states to open in `ux.toml`. easyadmin's light theme, details panel and cap refusal are audited for the first time. |

### Proposed: Audit step can change code that is then pushed unverified
Status: done

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
Status: done

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
Status: done

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
Status: done

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

Again on #57 (1.6.3): the UX review saw the cap refusal alert
(`easyadmin_apps.js:2310`) only in source and UI tests, since the audit ran
in dark only and opens no panel. The page can force the refusal with
`?ea_max_request_bytes=` (`easyadmin_apps.js:638-642`), so a listed panel
state could include it.

- [x] Confirm: should this be done? (Recommended: yes, the theme switch at
  least; CLAUDE.md's definition of done assumes both themes are audited.):
  Yes.

### Proposed: One failed `git pull` after a merge leaves the loop stuck until resumed
Status: done

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

Again on 2026-11-16T10:15:04Z, waiting on #57: "Loop stuck in await: gh pr
view failed: error connecting to api.github.com" (loop log since the groom
of 20261116-092127). The network outage was outside the loop, but
`phase_await` polls (`loop.py:744`), so one failed `gh pr view` could simply
be retried at the next poll instead of pausing for the owner. The same
retry should cover it: a failed read-only `gh` or `git` call in `await` is
logged and retried, and only repeated failures over some minutes mark the
loop stuck.

- [x] Confirm: should this be done? (Recommended: yes, a small retry; it
  costs nothing when git succeeds, and a ref race should not need the owner.):
  Yes.

### Proposed: A fix for owner feedback reaches the PR with no security or UX review
Status: done

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

- [x] Confirm: should this be done? (Recommended: yes; the fix after owner
  feedback is often the larger change, as on #51.): Yes.

### Proposed: The implement step is not told to see a new test fail first
Status: done

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

- [x] Confirm: should this be done? (Recommended: yes, a prompt line; it
  costs one extra test run per item.): Yes.

### Proposed: A step can end its turn while its own background work still runs
Status: proposed

On #58 the review step started the `splunk-reviewer` agent and
`splk dev easyadmin` in the background, then ended its turn waiting for
them; the session forced a structured result at once, and the step
reported `failed` ("The review step is not finished") at 10:44:01, before
either had finished. Only because the agent's hand-back re-woke the session
did it go on and report `done` ten minutes later
(`.agent/loop/steps/20261116-215352-review.json`, session transcript
`58f5ee7b`). Had the session stopped at the first result, the supervisor
would have treated a clean review as a failed step (`_step_failed`) and
retried or marked the loop stuck. Nothing in `.claude/loop/prompts/_common.md`
says that a headless step must wait for its own work. Fix: one line in
`_common.md`: run subagents and long commands (`splk dev`, `splk test`) in
the foreground, and never give the structured result while one is still
running. Changes `.claude/loop/`, so it would be built in an interactive
session.

- [ ] Confirm: should this be done? (Recommended: yes, a prompt line; the
  cost of a false `failed` is a repeated review or a stuck loop.)

### Proposed: The review step recorded a security pass without running the security review
Status: proposed

On #58 the review step ran `splk review security easyadmin pass --summary
"Tests-only branch; no app code, conf or tooling changed. No findings."`
at 10:43:39, three seconds after starting the `splunk-reviewer` agent, and
never ran the `splunk-security-review` skill or the `security-reviewer`
agent (session transcript `58f5ee7b`,
`.agent/loop/steps/20261116-215352-review.json`). `review.md` step 1 says
to run the skill, with no exception for a tests-only branch, so the run log
now holds a security review that did not happen, and the Stop hook and the
owner read it as one. The branch did add live-test code that signs in and
sends requests to splunkd. Fix: in `.claude/loop/prompts/review.md`, either
always run the skill, or allow skipping it only for a branch with no change
under `apps/`, `tools/`, `scripts/` or `.claude/hooks/`, and then record
nothing rather than `pass`. Changes `.claude/loop/`, so it would be built
in an interactive session.

- [ ] Confirm: which? Options: (a) always run the security review;
  (b) skip it for test-only branches and record no review. Recommendation:
  (a); test code that talks to splunkd is still code, and the review costs
  minutes.

### Proposed: The review step reads the groom commit as part of the change
Status: proposed

Every item branch starts with the supervisor's "Roadmap: groom before
<item>" commit (`phase_groom`, `tools/splk/loop.py:603`), so
`git diff main...HEAD`, which `.claude/loop/prompts/review.md` tells the
step to review, includes that groom's ROADMAP.md edits. On #58 the review
step listed "`ROADMAP.md` carries groom additions unrelated to this change"
as an open finding in the PR body
(`.agent/loop/steps/20261116-215352-review.json`), so the owner was shown
the loop's own design as a defect. Fix: one line in `review.md`: the
branch's first commit is the groom and its ROADMAP.md changes are not part
of the item; review the item's own commits. Changes `.claude/loop/`, so it
would be built in an interactive session.

- [ ] Confirm: should this be done? (Recommended: yes, a prompt line.)
