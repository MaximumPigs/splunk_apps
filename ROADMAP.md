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
- An item with open questions has a `Context:` paragraph under its status
  line: a short, plain summary that heads its GitHub issue.

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
| 1.7.0 | A locked object (shipped in a default folder) that also has a stanza in the app's `local` file names that file in the lock's tooltip, the disabled Delete button's tooltip and the legend; no delete is built, since on 10.6.1 no REST call removes only the local layer (eight DELETE variants probed on a saved search; the `properties` stanza DELETE answers success and changes nothing). New model key `local_file`, filled in for callers with `admin_all_objects`. |
| 1.7.1 | While a panel is open (an object's details, Edit permissions, New app or Clone) the toolbar keeps clear of it, so New app, Reload, Discard changes and Apply changes stay in view. Pressing one closes the panel first; if the panel holds typing that is not staged (a setting being edited or added, permission choices, a changed new app or clone form) the page asks "Discard what you typed in the panel and continue?" and does nothing if declined. Close, Escape, Cancel, Clone, another object and the selection bar's buttons are unchanged. |

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

### An option to hide all apps in "app management" which do not have any knowledge objects displayed.
Status: request
When viewing apps in App Management with a filter applied, apps with no matching knowledge objects are shown which can crowd the screen when there are logs of apps. Add switch to hide apps with no matching knowledge objects (hidden by default)

### App Management - filtering is slow when there are lots of apps.
When in app management and there are lots of apps and knowledge objects - the filter is very slow to react to input. It may be trying to filter with every new character input. Find a way to make it faster, perhaps a short wait for more input before triggering filter.

### User management page
Status: blocked
Context: A new easyadmin page like Role management, but for users: a grid of
users against roles plus a table of their other settings, changed in bulk
and saved together. The open question decides what the page does when an
admin changes the roles of their own account.

- Same intent as Role management, but for bulk user configuration.
- Editable in the first version: roles, default app, time zone, real name
  and email, unlocking a locked-out account, and forcing a password change
  at next sign-in. Not in the first version: creating and deleting users,
  and setting passwords, so no secret is ever typed into the page.
- Laid out like Role management: a grid of users against roles with tick
  boxes, plus a table of the other settings.
- Users signed in through LDAP or SAML (roles from group mappings) are
  listed read-only, saying why.
- [x] Which user settings can the page change? Options: roles, default
  app, time zone, real name and email, unlocking a locked-out account,
  forcing a password change at next sign-in, creating and deleting users,
  setting passwords. Recommendation: everything except creating, deleting
  and passwords in the first version, so no secret is ever typed into the
  page.: As recommended.
- [x] How is it laid out? Options: (a) like Role management, a grid of
  users against roles with tick boxes, plus a table of the other settings;
  (b) a list of users with a panel that edits the selected ones together.
  Recommendation: (a), so both admin pages work the same way.: (a).
- [x] Users signed in through LDAP or SAML get their roles from group
  mappings, so their roles cannot be changed here. Options: (a) list them
  read-only, saying why; (b) leave them out. Recommendation: (a).: (a).
- [ ] On easyadmin's planned User management page, what happens when an
  admin stages a change to their own account's roles (for example removing
  their own admin role, which can lock them out of the page and of Splunk
  administration)? Options: (a) allowed, with a warning in the save
  confirmation naming their own account, as Role management already warns
  when a save changes a role you hold; (b) refused at staging, so the page
  never changes the signed-in user's own roles; (c) allowed without a
  warning. Recommendation: (a), the same behaviour as Role management.

Probe first: the `authentication/users` fields for unlocking an account and
forcing a password change on 9.3 and 10.x, how splunkd marks an LDAP or SAML
user (the `type` field), and whether Splunk Cloud lists system users that an
`sc_admin` cannot edit.

### 2. Export and import an app as JSON
Status: blocked
Context: Save a whole app (its knowledge objects and lookups) as a JSON file
and load it into another Splunk instance, staged as pending changes until
you press Apply. The open questions decide where an import may land, what
it may overwrite or delete, and what happens when it is too big for one Apply.

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
Context: A page like App management for a deployment server: edit the apps
it pushes to forwarders, manage server classes, and back up and revert. The
open questions decide whether it lives in a separate Enterprise-only app,
how changes reach clients, where backups are kept, and how the work is split.

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

### Proposed: No screenshot shows the "hidden by the filters" note
Status: ready

Left by the splunk-reviewer on #51 (1.6.2), low. In
`test_a_clone_box_counts_its_staged_copies_and_those_the_filters_hide`
(`tests/ui/easyadmin/test_easyadmin_apps_ui.py:793`) the
`app_management_clone_counts` screenshot is taken before the name filter
is applied, and with the common types every copy is listed, so no image
shows the `.ea-hidden-staged` note; the test asserts its text only. Fix: a
second `shot` after the name filter, and open it. Tests only.

Parked by the loop on 2026-11-17: the change is built on branch
`feature/easyadmin-proposed-no-screenshot-shows-the-hidden` (the new
screenshot was opened and shows the note), but its last `splk dev easyadmin`
failed two UI tests on a stray macro, `easyadmin_ui_1794881048778`, still in
the dev target's `search` app (seen by `splk search` at the groom). The loop
skips the item while it is parked and has no way to resume it: see the
Tooling proposals "A step that reports blocked without an owner question
parks its item for good" and "A killed UI test run leaves its macros behind".
The stray macro was still there at the groom of 2026-11-18 (`splk search`).

- [x] Confirm: should this be done? (Recommended: yes, one line; it could
  join "Tests the settings panel still lacks".): Yes. ("Tests the settings
  panel still lacks" has since shipped, so this is its own item.)

### Proposed: The marker wait in the `user-prefs` check rests on an unobserved ordering
Status: proposed
Context: One easyadmin test proves the details panel makes no extra request
by checking Splunk's access log, and it assumes the log becomes searchable in
order. Doing this would check that assumption with a probe, so the test
cannot pass by accident. Tests only.

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

### Export an app as a .spl or .tgz file
Status: blocked
Context: Download any app on the instance as one package file, ready to
install on another Splunk instance, from App management. The open questions
decide how it relates to the planned JSON export, and what goes into the
package.

- Exports the whole app to a .tgz or .spl file.
- [ ] How does this relate to item 2 (export and import an app as JSON)?
  Options: (a) a separate feature: the package holds the app's files (code,
  dashboards, conf) for installing as an app, while the JSON moves knowledge
  objects into an existing app; (b) it replaces the JSON export.
  Recommendation: (a), since they serve different moves.
- [ ] What goes into the package? Options: (a) the app as Splunk packages
  it, with `local` settings merged into `default` and no user-private
  objects; (b) the app's folder as it is on disk, `local` included; (c) as
  (a), plus the app's lookup files. Recommendation: (a), the form Splunk
  itself installs and AppInspect expects.
- [ ] .spl and .tgz are the same format (a gzipped tar) under two names.
  Offer one, or let the person choose? Recommendation: one file named
  `<app>-<version>.spl`.

Probe first: splunkd's `apps/local/<app>/package` endpoint on 9.3 and 10.6
(what it writes, where, and whether a page can download the result), and
whether a handler that reads another app's files passes the Splunk Cloud
AppInspect checks; if neither works on Splunk Cloud, report back to the
owner before building.

### Proposed: The UX audit never draws the struck "moving to" row
Status: proposed
Context: Since 1.6.4 an object with a staged move stays listed, struck
through, in the app it is leaving. No audit screenshot has ever shown that
row, so it has not been checked in the light theme. Doing this adds a staged
move to the page's UX audit, so both themes are seen on every run.

Left by the UX review on #63 (1.6.4), minor. The `.ea-moving-out` row
(`apps/easyadmin/appserver/static/easyadmin_apps.css:352`) was seen only in
dark, in the UI test screenshot `app_management_staged_move_origin.png`; it
reuses existing colour variables. Since #64 the audit runs both themes, but
`tests/ui/easyadmin/ux.toml` lists only the `details` and `cap-refusal`
states, and neither stages a move. Fix: a third state in `ux.toml` that
stages a move of one object and waits for `.ea-moving-out`. Tests only.

Probe first: whether a `ux.toml` state's `click` list can stage a move
(how the page picks the destination app), or whether a query hook is needed.

- [ ] Confirm: should this be done? (Recommended: yes; it is the only way the
  row is seen in light, and every later audit keeps checking it.)

### Proposed: Two UI test gaps for the staged move away row
Status: proposed
Context: Two small test gaps left by the 1.6.4 change that keeps a moved
object listed in the app it leaves. Doing this adds two assertions; the app
does not change.

Left by the splunk-reviewer on #63 (1.6.4), both low:

- The "hidden by the filters" note's "staged move away" wording is asserted
  only combined with a deletion
  (`tests/ui/easyadmin/test_easyadmin_apps_ui.py:969`), and the plural
  "staged moves away" (`apps/easyadmin/appserver/static/easyadmin_apps.js:1007`)
  is never asserted. Fix: a case with two hidden moves away.
- The moving-out row's `data-fid` is `moving:<key>`
  (`easyadmin_apps.js:1440`); the UI test covers focus after its discard button
  but not focus restored to the row after another re-render. Fix: one
  assertion after a re-render (for example toggling a filter).

- [ ] Confirm: should this be done? (Recommended: yes, tests only, small;
  it could be built with "No screenshot shows the hidden by the filters
  note", which edits the same test file.)

## fillcontinuous

### Done

| Version | What |
| --- | --- |
| 1.1.2 | Real rows keep `_raw` and other `_` fields when a filled row is the first one written: the command registers every output field name with the record writer before yielding. |
| 1.1.3 | Only `admin` and `sc_admin` can change or unexport the command: `power` no longer has write on the app or its command stanzas. |

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

### Proposed: A step can end its turn while its own background work still runs
Status: proposed
Context: Loop steps run long test commands in the background. One step
reported "failed" while its tests were still running; another had its test
run stopped at a 10-minute limit, which left a test object behind and failed
the next run. Doing this adds step instructions on how long to let such
commands run and to wait for them.

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

Again on 2026-11-17, with a different outcome: the implement step for "No
screenshot shows the hidden by the filters note" started `splk dev easyadmin
--restart` as a background command with a 600000 ms (10-minute) limit at
12:54:12 local (session transcript `d87cfce4`). `splk dev easyadmin` takes
about 11 minutes to the end of its UI stage (13:04:15 to 13:15:13 for the
step's second run), and the UX audit follows when that is green, so the
command was stopped at 13:04:12, inside the UI stage: no `ui`
row reached `.agent/runs/2026-11-17.jsonl` for that run, and the macro
`easyadmin_ui_1794881048778` (created 13:04:08, by its millisecond name) was
never deleted by the fixture's teardown. The step's second run, with a
longer limit, then failed two UI tests on that macro, and the step reported
`blocked` (`.agent/loop/steps/20261117-131623-implement.json`). A foreground
command is capped at 10 minutes too, so "run it in the foreground" alone
cannot hold `splk dev easyadmin`. Revised fix: `_common.md` says to run
`splk dev` and `splk test --ui` in the background with a limit of at least
an hour, to wait for the completion notice before reading the output, and
never to give the structured result while one is still running.

- [ ] Confirm: should the step instructions say to run `splk dev` and
  `splk test --ui` in the background with at least an hour's limit, and to
  wait for them before reporting? (Recommended: yes, a prompt line; a
  10-minute limit cuts easyadmin's run of 11 minutes or more mid-test and
  leaves test objects on the dev target, and a false `failed` repeats a
  step or stops the loop.)

### Proposed: The review step recorded a security pass without running the security review
Status: proposed
Context: On a tests-only PR the loop recorded "security review: pass" without
running the review, so the record says something that did not happen. The
question is whether every branch gets the review, or tests-only branches
skip it and record nothing.

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
Context: Each PR starts with the loop's own roadmap tidy-up commit, and the
reviewer counted those roadmap edits as a finding in a PR. Doing this tells
the reviewer to skip that first commit.

Every item branch starts with the supervisor's "Roadmap: groom before
<item>" commit (`phase_groom`, `tools/splk/loop.py:603`), so
`git diff main...HEAD`, which `.claude/loop/prompts/review.md` tells the
step to review, includes that groom's ROADMAP.md edits. On #58 the review
step listed "`ROADMAP.md` carries groom additions unrelated to this change"
as an open finding in the PR body
(`.agent/loop/steps/20261116-215352-review.json`), so the owner was shown
the loop's own design as a defect. Again on #80 (fillcontinuous 1.1.3): the
splunk-reviewer's notes included "unrelated ROADMAP groom edits"
(`.agent/loop/steps/20261117-133426-review.json`). Fix: one line in `review.md`: the
branch's first commit is the groom and its ROADMAP.md changes are not part
of the item; review the item's own commits. Changes `.claude/loop/`, so it
would be built in an interactive session.

- [ ] Confirm: should this be done? (Recommended: yes, a prompt line.)

### Proposed: The full dev loop runs twice more after a review that changed nothing
Status: proposed
Context: Each roadmap item runs the full build-and-test cycle (about ten
minutes for easyadmin) several times. After a review that changed no file,
it still ran twice more on identical code. Doing this skips both, saving
about twenty minutes per item without skipping any check on changed code.

On #63 (easyadmin 1.6.4) `splk dev easyadmin` ran green five times
(`.agent/runs/2026-11-17.jsonl`): twice inside the implement step, once in
the supervisor's verify (05:07 to 05:17), once inside the review step (05:20
to 05:30) and once more in verify after it (05:30 to 05:41). The review step
fixed nothing (`.agent/loop/steps/20261117-053057-review.json`: no security
findings, nothing blocking from the splunk-reviewer, the rest left as open
findings), so the last two ran on the code already verified at 05:17. The
retro of the same item named these repeated runs. Causes:
`.claude/loop/prompts/review.md` step 4 is read as "always re-run", and
`phase_review` (`tools/splk/loop.py:736-751`) always goes to `verify`, even
when `commit_all` returns False because nothing changed. Fix: `review.md`
step 4 says to run `splk dev` only after changing a file, since the
supervisor verifies anyway; `phase_review` goes straight to `retro` (or
`push` in a fix) when the review committed nothing, with a unit test.
Changes `tools/splk/` and `.claude/loop/`, so it would be built in an
interactive session.

Again on #80 (fillcontinuous 1.1.3): the review step found nothing and
committed nothing (`.agent/loop/steps/20261117-133426-review.json`; the PR
has no review commit), yet `splk dev fillcontinuous` ran green inside the
review step (13:33 to 13:34 local) and again in the supervisor's verify
after it (13:34 to 13:35), on the code verified at 13:32
(`.agent/runs/2026-11-17.jsonl`). Cheap for an app with no views, but the
same two runs cost about twenty minutes on easyadmin.

- [ ] Confirm: should this be done? (Recommended: yes; the supervisor's
  verify still runs after every change, so nothing goes unchecked.)

### Proposed: A two-line notification reappears in every groom's loop log
Status: proposed
Context: The loop keeps a log of what it told the owner, and each roadmap
tidy-up reads the part since the last tidy-up. One old message split over
two lines, and its second half is shown again every time. Doing this keeps
each message on one line so old ones drop out.

The "Loop stuck in await: gh pr view failed: error connecting to
api.github.com" notification of 2026-11-16T10:15:04Z carried gh's second
line, so `.agent/loop/notifications.log` holds a line "check your internet
connection or https://githubstatus.com" with no timestamp. The loop log
filters notifications with `line[:20] > since` (`tools/splk/loop.py:390`);
"c" sorts after "2", so the orphan line passes every cut-off and was listed
again in this groom's loop log, a day after the event. `notify`
(`loop.py:282-288`) writes the message as given. Fix: in `notify`, replace
newlines in the message with " / " before writing the file (ntfy can keep
the original), and skip lines without a timestamp when reading, with a unit
test. Changes `tools/splk/`, so it would be built in an interactive session.

Again in the groom of 2026-11-17 13:16 local: the same orphan line headed
the loop log's notifications, and `state.json` still holds the two-line
message as `stuck_reason`. And again in the groom after #80 merged (18:07
local): the orphan line headed the notifications for the third time, and
for the fourth in the groom after #81 merged (18:15 local).

Again in the groom of 2026-11-18, for the fifth time. The two "Loop stuck in
publish" notifications of 2026-11-17 (07:15:54Z and 17:19:40Z) were
multi-line too: `notifications.log` holds only their first two lines, which
end at "(non-fast-", so the notification cut off the cause ("the tip of
your current branch is behind its remote counterpart"), and `state.json`
holds the full git output as `stuck_reason`. Their continuation lines start
with a space, which sorts before "2", so only the gh line keeps returning.

- [ ] Confirm: should this be done? (Recommended: yes, two lines; low
  value on its own, so it could join the next loop change.)

### Proposed: A step that reports blocked without an owner question parks its item for good
Status: proposed
Context: When a loop step reports "blocked", the loop sets the item aside
until the owner answers its question. A step used "blocked" for a test
failure with no question, so there is nothing to answer and the item never
resumes. Doing this sends such a result back for another attempt instead,
and shows the step's full reason.

On 2026-11-17 the implement step for "No screenshot shows the hidden by the
filters note" reported `blocked` because two UI tests failed on a stray
macro, not because of an owner decision
(`.agent/loop/steps/20261117-131623-implement.json`). `phase_implement`
(`tools/splk/loop.py:689-697`) parks on any `blocked`; `_park` (`:928-939`)
records the issue title, but `sync_question_issues` (`:468-516`) creates
issues only for items with open questions (`loop_core.awaiting_owner`), and
the item has none, so no issue was created (the "Parked" notification
listed no URL). `phase_groom` (`:608-617`) resumes a parked item only when
an answer arrives on that issue, so the item stays parked for good, and
`next_item` skips it. The notification also cut the summary at 120
characters (`:937`), before the step's "To unblock: delete that macro". The
parked branch holds the finished change and a fix for the unit test that
fails inside every loop step (lesson
`tests-git-subprocess-inherits-git-config-env`; red at 12:44 and 12:53 local
in `.agent/runs/2026-11-17.jsonl`). #80 has since fixed the same failing
test on main (`tests/test_splk_loop.py`), so the parked branch's own fix to
it will need reconciling with main when the branch is resumed.
`_common.md` defines `blocked` as "the owner must answer first", and the step
used it anyway. Fix: `_park` only when the item on the branch has an open
question; otherwise treat `blocked` as a failed attempt (back to `implement`
with the summary as `last_failure`, within `max_attempts`, then stuck with
the full summary notified), with unit tests. Changes `tools/splk/`, so it
would be built in an interactive session, which can also resume this
item's branch.

- [ ] Confirm: should a loop step's "blocked" result with no open question on
  the item count as a failed attempt (retried, then the loop stops and
  notifies the full reason) instead of parking the item? (Recommended: yes;
  today such an item is set aside with no issue to answer and never comes
  back.)

### Proposed: A killed UI test run leaves its macros behind
Status: proposed
Context: easyadmin's browser tests create test macros and delete them when
each test ends. A test run stopped part-way left one behind, and the next
run failed two tests that count every test macro on the page. Doing this
makes the tests clear out leftovers from earlier runs, so one stopped run
cannot fail the next. Tests only.

The `macro` fixture (`tests/ui/easyadmin/test_easyadmin_apps_ui.py:27-44`)
deletes the macros it made in its teardown, which does not run when the
process is killed. On 2026-11-17 a `splk dev easyadmin` stopped mid-UI-stage
left `easyadmin_ui_1794881048778` in the dev target's `search` app (still
there at the grooms of 13:16, 18:07 and 18:15 local, and of 2026-11-18, by `splk search`, so any
easyadmin item the loop builds next will fail the same two UI tests). The tests filter the page with the
prefix `easyadmin_ui_` (`:191`, `:392`, `:608`, and
`test_easyadmin_request_cap_ui.py:37`), so the stray macro was listed and
selected too: `test_select_all_in_an_app_selects_what_it_shows` and
`test_select_all_skips_the_struck_row` saw one object more than they made
(`.agent/runs/2026-11-17.jsonl`, 13:15:13 local). The implement step could
not delete it: a direct REST call is outside `splk` and was refused, and
the sandbox guard snapshots users, roles and app permissions, not macros.
Fix: a session-scoped fixture in `tests/ui/easyadmin/` that deletes, through
`sandbox_client`, any `easyadmin_ui_*` macro (and the `easyadmin_ui_newapp`
and `easyadmin_ui_clone` apps) older than the session before the tests run,
with a log line naming each; or filter each test by its own macro names
rather than the shared prefix. Tests only, so the loop can build it. Found
from the loop log of 2026-11-17 (implement step record above).

- [ ] Confirm: should easyadmin's UI tests delete leftover `easyadmin_ui_*`
  test macros from earlier runs before they start? (Recommended: yes, a
  sweep at session start; filtering by exact names would also work but
  touches every test and still leaves strays on the dev target.)

### Proposed: A second roadmap PR on the same day cannot be pushed
Status: proposed
Context: When the loop has only roadmap edits to publish, it names the branch
after the date. A second such PR on the same day reused the first one's
branch name, git refused the push, and the loop stood still for ten hours
until the branch was replaced by hand. Doing this gives each roadmap branch
a unique name.

`phase_groom` names a roadmap-only branch `roadmap/groom-<YYYYMMDD>`
(`tools/splk/loop.py:651`), and an audit `roadmap/audit-<YYYYMMDD>`
(`:645`). `new_branch` (`:259-266`) recreates the branch locally from main,
but the merged PR's branch is never deleted on GitHub (`origin/roadmap/
groom-20261116`, `groom-20261117` and `audit-20261115` all still exist), so
`phase_publish` (`:780`) pushes a branch that does not descend from the
remote one. On 2026-11-17 #81 merged from `roadmap/groom-20261117`; the next
groom (`.agent/loop/steps/20261117-181550-groom.json`) committed to the
same name and the push was rejected as non-fast-forward: "Loop stuck in
publish" at 07:15:54Z, and again at 17:19:40Z after a resume. The remote
branch was then replaced from this clone at 17:27Z (the remote-tracking
reflog shows `db70cd6` to `321c2a0`, which does not descend from it, so a
plain push could not have done it), and #82 opened at 17:28Z. The owner's
answers on #66 and #68 (10:45Z) waited until the groom of 2026-11-18. Fix:
add the time to the stamp (`%Y%m%d-%H%M%S`) for groom and audit branches,
with a unit test; optionally also turn on GitHub's "Automatically delete
head branches" repository setting, which removes merged branches.
Changes `tools/splk/`, so it would be built in an interactive session.

- [ ] Confirm: should the loop's roadmap-only and audit branches get a
  unique name each time (date and time), so a second roadmap PR on the same
  day can be pushed? (Recommended: yes, a one-line change; GitHub's
  "Automatically delete head branches" setting would also prevent it, but
  the loop should not depend on a repository setting.)
