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
| 1.7.1 (tests only) | The live check that the details panel does not read `user-prefs` relies on `splunkd_access` lines becoming searchable in the order they were written. That is now observed (four probe runs, 220 snapshots, never a later request searchable before an earlier one; Splunk 10.6.1, one ingestion pipeline) and a live test checks it on every run. No change to the app. |
| 1.7.2 | "Filter objects by name" and "Filter apps by name" wait for a quarter-second pause in typing before filtering, and a filter change redraws only the app boxes, not the whole page; the field keeps focus and caret. Row icons are built once and copied. A click during the pause acts on the list on screen, and any other full redraw (Reload, a tick) applies the typed text first. |

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
Status: ready

When viewing apps in App Management with a filter applied, apps with no matching knowledge objects are shown which can crowd the screen when there are logs of apps. Add switch to hide apps with no matching knowledge objects (hidden by default)

- The switch hides an app only while text is typed in "Filter objects by
  name" and the app's box would list none of the matching objects. With no
  text typed, every app shows as today, including an empty or newly created
  one.
- Today the object filter and the Types menu narrow objects, never apps, on
  purpose: every app box stays on show as a place to drop a dragged object
  (`visibleApps`, `apps/easyadmin/appserver/static/easyadmin_apps.js:1014`).
  The details panel's App and Copy to lists name every app whatever is on
  show, so a move or copy into a hidden app stays possible from the panel.
- Dropping on a hidden app: once a drag starts, and only if the switch has
  hidden at least one app, a "Hidden apps" area appears; hovering the
  dragged objects over it lists the hidden apps, and dropping on one of
  them does what dropping on that app's box does (move, or copy with Ctrl
  or Cmd held or for objects in a default folder). The area goes away when
  the drag ends. The app then has a staged change, so its box shows.
- A box with staged changes, and a pending new app, keep showing as today,
  whatever the switch says. The switch sits beside "Show Splunk's built-in
  apps" and, like it, is not remembered between page loads.
- [x] On easyadmin's App management page, when should the new "hide apps
  with no matching objects" switch hide an app? Options: (a) only while
  text is typed in "Filter objects by name", as the request describes;
  (b) whenever the app's box would list no objects, filter or not, so an
  app with none of the types chosen in the Types menu (such as one just
  created) is hidden too until the switch is turned off. Recommendation:
  (a), so an empty or newly created app stays in view when nothing is
  typed.: (a).
- [x] On easyadmin's App management page, objects are moved by dragging
  them onto another app's box, and the new switch hides boxes with no
  matching objects, which are often the destination. How does a person
  reach a hidden app? Options: (a) they cannot drop on it: they use the
  object's details panel (its App and Copy to lists name every app) or turn
  the switch off; (b) as (a), and an app whose name matches text typed in
  "Filter apps by name" always shows, so a destination can be brought back
  by typing its name; (c) hidden apps reappear while an object is being
  dragged (boxes then shift under the pointer). Recommendation: (b).: The
  owner asked instead for a "Hidden apps" area, shown once a drag has
  started, that lists the hidden apps when the dragged items hover over it,
  to drop on. It can be built: the page uses the browser's own drag and
  drop, whose drag-over events fire on any element (`dragover` handlers in
  `easyadmin_apps.js`).

Probe first: that adding the "Hidden apps" area to the page as a drag
starts does not cancel the drag in Chrome and Firefox (some browsers end a
drag when the page changes inside `dragstart`; adding it just after, or
keeping it in the page hidden until then, avoids that), with a UI test that
drags an object onto a listed hidden app.

### User management page
Status: ready

- Same intent as Role management, but for bulk user configuration.
- Editable in the first version: roles, default app, time zone, real name
  and email, unlocking a locked-out account, and forcing a password change
  at next sign-in. Not in the first version: creating and deleting users,
  and setting passwords, so no secret is ever typed into the page.
- Laid out like Role management: a grid of users against roles with tick
  boxes, plus a table of the other settings.
- Users signed in through LDAP or SAML (roles from group mappings) are
  listed read-only, saying why.
- An admin may stage a change to their own account's roles; the save
  confirmation then warns, naming their own account, as Role management
  warns when a save changes a role the signed-in user holds.
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
- [x] On easyadmin's planned User management page, what happens when an
  admin stages a change to their own account's roles (for example removing
  their own admin role, which can lock them out of the page and of Splunk
  administration)? Options: (a) allowed, with a warning in the save
  confirmation naming their own account, as Role management already warns
  when a save changes a role you hold; (b) refused at staging, so the page
  never changes the signed-in user's own roles; (c) allowed without a
  warning. Recommendation: (a), the same behaviour as Role management.: (a).

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
Since 1.7.1 the UI tests delete such leftover macros before they start, and
the macro was gone at the second groom of 2026-11-18 (`splk search`: 0
rows), so the branch's tests should pass once the item is resumed.

- [x] Confirm: should this be done? (Recommended: yes, one line; it could
  join "Tests the settings panel still lacks".): Yes. ("Tests the settings
  panel still lacks" has since shipped, so this is its own item.)

### Export an app as a .spl or .tgz file
Status: ready

- Exports the whole app to one file named `<app>-<version>.spl` (no .tgz
  choice).
- A separate feature from item 2 (export and import as JSON): the package
  holds the app's files for installing as an app; the JSON moves knowledge
  objects into an existing app.
- The person chooses at export whether the app's `local` settings are
  merged into `default` (the form Splunk itself packages and installs, no
  user-private objects) or not (the app's folder as it is on disk, `local`
  kept as its own folder).
- [x] How does this relate to item 2 (export and import an app as JSON)?
  Options: (a) a separate feature: the package holds the app's files (code,
  dashboards, conf) for installing as an app, while the JSON moves knowledge
  objects into an existing app; (b) it replaces the JSON export.
  Recommendation: (a), since they serve different moves.: (a).
- [x] What goes into the package? Options: (a) the app as Splunk packages
  it, with `local` settings merged into `default` and no user-private
  objects; (b) the app's folder as it is on disk, `local` included; (c) as
  (a), plus the app's lookup files. Recommendation: (a), the form Splunk
  itself installs and AppInspect expects.: Give the person the option to
  merge or not.
- [x] .spl and .tgz are the same format (a gzipped tar) under two names.
  Offer one, or let the person choose? Recommendation: one file named
  `<app>-<version>.spl`.: Just use .spl.

Probe first: splunkd's `apps/local/<app>/package` endpoint on 9.3 and 10.6
(what it writes, where, and whether a page can download the result), and
whether a handler that reads another app's files passes the Splunk Cloud
AppInspect checks; if neither works on Splunk Cloud, report back to the
owner before building. Also whether the endpoint can leave `local`
unmerged; if not, the unmerged choice means the handler packs the app's
folder itself, under the same AppInspect check.

### Proposed: The UX audit never draws the struck "moving to" row
Status: ready

Left by the UX review on #63 (1.6.4), minor. The `.ea-moving-out` row
(`apps/easyadmin/appserver/static/easyadmin_apps.css:352`) was seen only in
dark, in the UI test screenshot `app_management_staged_move_origin.png`; it
reuses existing colour variables. Since #64 the audit runs both themes, but
`tests/ui/easyadmin/ux.toml` lists only the `details` and `cap-refusal`
states, and neither stages a move. Fix: a third state in `ux.toml` that
stages a move of one object and waits for `.ea-moving-out`. Tests only.

Probe first: whether a `ux.toml` state's `click` list can stage a move
(how the page picks the destination app), or whether a query hook is needed.

- [x] Confirm: should this be done? (Recommended: yes; it is the only way the
  row is seen in light, and every later audit keeps checking it.): Yes.

### Proposed: Two UI test gaps for the staged move away row
Status: ready

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

- [x] Confirm: should this be done? (Recommended: yes, tests only, small;
  it could be built with "No screenshot shows the hidden by the filters
  note", which edits the same test file.): Yes.

### Proposed: The toolbar's room for an open panel is fixed at 456px
Status: proposed
Context: Since 1.7.1 the App management toolbar leaves room for an open side
panel so its buttons stay in view. The room is a fixed width, so in a narrow
window (under about 700px) the buttons are squeezed and stack. The question
is whether to change that for narrow windows.

Left by the splunk-reviewer on #84 (1.7.1), low. While a panel is open the
toolbar and selection bar reserve `padding-right: 456px`
(`apps/easyadmin/appserver/static/easyadmin_apps.css:432-435`), with no
`@media` rule anywhere in the file. In a window under about 700px wide the
toolbar is squeezed and its buttons stack. Fix: a `max-width` media query
that drops the padding, so in a narrow window the panel covers the toolbar
again as before 1.7.1, with a UI test at a narrow viewport (the UI tests
run only at the default size today). Left because it needs a design choice.

- [ ] Confirm: on easyadmin's App management page, in a browser window too
  narrow for both the toolbar and the side panel (under about 700px),
  should the panel cover the toolbar again (as before 1.7.1, so the panel
  must be closed to reach Apply), or keep today's squeezed, stacked
  buttons? (Recommended: cover the toolbar below that width; a narrow
  Splunk Web window is rare for an admin page, and stacked buttons beside a
  panel are hard to use.)

### Proposed: The prompt on leaving a panel does not say what is lost
Status: proposed
Context: Since 1.7.1, pressing a toolbar button while the side panel holds
unsaved typing asks "Discard what you typed in the panel and continue?".
It does not say what the typing was, and Discard changes can then ask a
second question. The question is whether to reword and combine these
prompts.

Left by the UX review on #84 (1.7.1), minor. `leavePanel`
(`apps/easyadmin/appserver/static/easyadmin_apps.js:2421`) asks "Discard
what you typed in the panel and continue? It is not staged yet." without
naming the draft (a setting being edited, a new app form, permission
choices). Discard changes (`:1195-1201`) then asks "Discard the staged
changes to ...?", so one click can show two prompts in a row. Fix: name the
draft in the prompt, and ask once for Discard changes, naming both the
typing and the staged changes. UI tests change with the wording.

- [ ] Confirm: on easyadmin's App management page, should the prompt shown
  when a toolbar button would lose typing in the side panel name what is
  lost (for example "Discard the setting you are editing and continue?"),
  and should Discard changes ask once for both the typing and the staged
  changes instead of two prompts in a row? (Recommended: yes to both; a
  person can then tell what they are throwing away from one prompt.)

### Proposed: No test that an untouched permissions panel closes silently
Status: proposed
Context: Since 1.7.1, pressing a toolbar button while a side panel is open
closes the panel, asking first only if it holds unsaved typing. The tests
cover the bulk Edit permissions panel only when something was changed in it.
Doing this adds the untouched case. Tests only.

Left by the splunk-reviewer on #84 (1.7.1), low.
`test_untouched_clone_form_and_bulk_choices`
(`tests/ui/easyadmin/test_easyadmin_apps_ui.py:1210`) checks an untouched
Clone form and a changed bulk Edit permissions panel; no test opens the
bulk panel, changes nothing and presses Reload, which should close it with
no prompt. Fix: that case, asserting no dialog and no panel. Tests only.

- [ ] Confirm: should this be done? (Recommended: yes, a few lines; it
  could be built with "Two UI test gaps for the staged move away row",
  which edits the same test file.)

### Proposed: The access-log order check has a fallback that has never run
Status: proposed
Context: A live test checks that Splunk's access log becomes searchable in
the order requests were made, which another test relies on. If indexing
lags, it falls back to a weaker check that has never run and cannot see a
gap. Doing this replaces the fallback with a visible skip. Tests only.

Left by the splunk-reviewer on #90 (1.7.1, tests only), low. In
`test_access_log_becomes_searchable_in_request_order`
(`tests/live/easyadmin/test_easyadmin_apps_live.py:439-455`) the branch for
"indexing lagged the whole probe" checks only the final set of markers, so
it cannot see a transient gap, and no probe so far (220 snapshots) has
reached it. A pass from it would be close to vacuous. Fix: drop the branch
and `pytest.skip` with the reason when no snapshot saw a marker. Tests only.

- [ ] Confirm: should this be done? (Recommended: yes, a few lines; a
  visible skip is more honest than a weak pass.)

### Proposed: The filter's result count is not announced to screen readers
Status: proposed
Context: On the App management page, typing in a name filter redraws the
app boxes and updates the "Showing N apps and M objects" line, but a screen
reader does not read the new count aloud. Doing this has the page announce
the count after each filter change.

Left by the UX review on #94 (1.7.2), polish. The summary and the "No
objects match the filter" message
(`apps/easyadmin/appserver/static/easyadmin_apps.js:1660`) sit in the
redrawn grid, which is not a live region, so after the debounced redraw a
screen-reader user hears nothing. The page already has a polite live
region (`$liveStatus`, `:1117`) that `renderFilterResults` (`:2827`) does
not write to. The code before 1.7.2 did not announce it either. Fix: write
the summary into `$liveStatus` from `renderFilterResults`, with a UI test
on the region's text.

- [ ] Confirm: on easyadmin's App management page, should a screen reader
  announce the new "Showing N apps and M objects" count after each change
  to a name filter? (Recommended: yes, a few lines; the polite region only
  speaks once typing pauses, so it does not interrupt.)

### Proposed: No test for typing a character and deleting it within the pause
Status: proposed
Context: Since 1.7.2 the App management name filters wait for a short
pause in typing before redrawing. If a person types a character and
deletes it within the pause, nothing should be redrawn. That case is
untested. Doing this adds the test. Tests only.

Left by the splunk-reviewer on #94 (1.7.2), minor. `filterSoon`
(`apps/easyadmin/appserver/static/easyadmin_apps.js:1102-1111`) returns
without redrawing when the typed text equals the filter already applied;
correct by reading, but none of the four debounce UI tests in
`tests/ui/easyadmin/test_easyadmin_apps_ui.py` (`:273-340`) exercises it.
Fix: a UI test that types then deletes a character within 250 ms and
asserts the grid was not redrawn. Tests only.

- [ ] Confirm: should this be done? (Recommended: yes, a few lines; it
  could be built with "No test that an untouched permissions panel closes
  silently", which edits the same test file.)

### Proposed: A filter change on a very large App management page still takes about a second
Status: proposed
Context: 1.7.2 made the App management filters wait for a pause in typing
and redraw less; on a test page with 300 apps and 5,000 objects, typing a
word now settles in about 1.2 s instead of 8 s. Going further means drawing
fewer rows at once, which changes what a box shows. The question is
whether to do that.

Left open by the implement step of #94 (1.7.2): on that stubbed model a
single filter change still costs about 0.6 s of browser layout after the
pause (`.agent/loop/steps/20261118-212334-implement.json`). Cutting it
means not drawing every matching row of every box at once. Probe first:
how many apps and objects the owner's instances have, measured with the
same stubbed-model timing as #94, before and after.

- [ ] Confirm: on easyadmin's App management page with hundreds of apps and
  thousands of objects, a filter change still takes about a second to show
  (down from 8 s before 1.7.2). Options: (a) leave it as 1.7.2 left it;
  (b) each box draws its first 100 matching objects and a "Show all N"
  button, so a long box needs one click to see the rest; (c) a box draws
  its rows only once it scrolls into view, so what a box lists is unchanged
  but rows appear a moment after scrolling. (Recommended: (a) unless the
  page is still slow on your instances; (b) and (c) each change how boxes
  behave for a small gain on very large instances.)

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
| easyadmin UI tests | Before the first test, macros named `easyadmin_ui_<ms>` and stamped before the run started are deleted from `search` and `launcher`, so a killed run cannot fail the next one (built with easyadmin 1.7.1, #84; the stray macro of 2026-11-17 is gone). Leftover `easyadmin_ui_newapp` and `easyadmin_ui_clone` test apps are not swept. |

### Proposed: A step can end its turn while its own background work still runs
Status: interactive

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

Again on #84 (easyadmin 1.7.1): the implement step's first attempts at its
result said `failed`, because "the last full run was still going (only the
build stage had logged) when I had to stop" (session transcript
`4757c819`, `.agent/loop/steps/20261118-052720-implement.json`).

Again on #94 (easyadmin 1.7.2): the review step started the
`splunk-reviewer` agent in the background at 10:38:36Z, then, to wait for
it, called the wake-up scheduling tool meant for interactive `/loop`
sessions and ended its turn. The session forced a structured result at
10:39:55Z, which said `failed` ("The splunk-reviewer agent was still
running when this step ended"); the agent's hand-back then re-woke the
session, which wrote the findings and finished in text only, so the step
record holds `output: {}` and the run log "FAIL easyadmin loop-review ok"
(session transcript `3c37ac08`,
`.agent/loop/steps/20261118-214405-review.json`). `phase_review`
(`tools/splk/loop.py:744-751`) checks only the step's `kind`, so the loop
went on; no harm this time, but the record says nothing true.

- [x] Confirm: should the step instructions say to run `splk dev` and
  `splk test --ui` in the background with at least an hour's limit, and to
  wait for them before reporting? (Recommended: yes, a prompt line; a
  10-minute limit cuts easyadmin's run of 11 minutes or more mid-test and
  leaves test objects on the dev target, and a false `failed` repeats a
  step or stops the loop.): Yes.

### Proposed: The review step recorded a security pass without running the security review
Status: interactive

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

- [x] Confirm: which? Options: (a) always run the security review;
  (b) skip it for test-only branches and record no review. Recommendation:
  (a); test code that talks to splunkd is still code, and the review costs
  minutes.: Yes, taken as the recommendation: (a), always run it.

Again on #90 (easyadmin 1.7.1, tests only): the review step started at
09:32:11 local, recorded `splk review security easyadmin pass` at 09:32:40
("Tests-only change: ...") and again at 09:45:47 ("Re-recorded after
reviewer fixes; tests only") in `.agent/runs/2026-11-18.jsonl`, and its
session (transcript `796bc7c8`) called only the `splunk-reviewer` agent,
never the `splunk-security-review` skill or the `security-reviewer` agent
(`.agent/loop/steps/20261118-094550-review.json`).

### Proposed: The review step reads the groom commit as part of the change
Status: interactive

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

- [x] Confirm: should this be done? (Recommended: yes, a prompt line.): Yes.

### Proposed: The full dev loop runs twice more after a review that changed nothing
Status: interactive

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

- [x] Confirm: should this be done? (Recommended: yes; the supervisor's
  verify still runs after every change, so nothing goes unchecked.): Yes.

### Proposed: A two-line notification reappears in every groom's loop log
Status: interactive

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
And for the sixth time in the groom after #84 merged (2026-11-18), and the
seventh in the groom after #90 merged (2026-11-18), and the eighth in the
groom after #94 merged (2026-11-19).

- [x] Confirm: should this be done? (Recommended: yes, two lines; low
  value on its own, so it could join the next loop change.): Yes.

### Proposed: A step that reports blocked without an owner question parks its item for good
Status: interactive

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

- [x] Confirm: should a loop step's "blocked" result with no open question on
  the item count as a failed attempt (retried, then the loop stops and
  notifies the full reason) instead of parking the item? (Recommended: yes;
  today such an item is set aside with no issue to answer and never comes
  back.): Yes.

### Proposed: A second roadmap PR on the same day cannot be pushed
Status: interactive

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

- [x] Confirm: should the loop's roadmap-only and audit branches get a
  unique name each time (date and time), so a second roadmap PR on the same
  day can be pushed? (Recommended: yes, a one-line change; GitHub's
  "Automatically delete head branches" setting would also prevent it, but
  the loop should not depend on a repository setting.): Yes.

### Proposed: A step whose result is rejected leaves no trace of why
Status: proposed
Context: Each loop step ends by handing the loop a short result (done,
blocked or failed, and a summary). On two PRs a step ended without one, so
the loop logged a failure that just reads "ok", with no reason anywhere.
Doing this records the step's last words and logs a clear "no result"
instead.

On #84 (easyadmin 1.7.1) the implement step tried its structured result 11
times and each was rejected by the schema check: the `status` value carried
the rest of the call's markup ("failed</parameter> <parameter
name="summary">..."), so `status` was not an allowed value and `summary`
was missing (session transcript `4757c819`). The session ended with no
structured output: the step record has `kind: ok`, `detail: ""` and
`output: {}` (`.agent/loop/steps/20261118-052720-implement.json`, 1530 s,
$0.97). `run_step` (`tools/splk/loop.py:450-452`) then logs
`output.get("summary") or detail or kind`, so the run log says "FAIL
easyadmin loop-implement ok" and the session-start notice lists "Unresolved
stage failures: easyadmin loop-implement: ok". The step's final text, which
said the change was done and `splk dev` green, is only in the transcript,
because the record keeps neither the result's `subtype` nor its `result`
text. No harm this time: `phase_implement` (`:689-699`) went on to the
supervisor's verify, which decides. Lesson
`splk-loop-step-ok-exit-empty-output-logs-fail` records the log wording
(cause unknown when it was written; the transcript now shows it). Fix: in
`run_step`, when there is no structured output, keep the result's `subtype`
and the last 500 characters of its `result` text in the record's `detail`,
and log "no structured result: <detail>", with a unit test. Changes
`tools/splk/`, so it would be built in an interactive session.

Again on #94 (easyadmin 1.7.2), with another cause: the review step gave a
structured result (`failed`) while its background reviewer agent still
ran, then carried on when the agent finished and ended in text only, so
the record again has `kind: ok`, `output: {}` and the run log "FAIL
easyadmin loop-review ok" (`.agent/loop/steps/20261118-214405-review.json`,
transcript `3c37ac08`; see "A step can end its turn while its own
background work still runs"). The lesson now has 2 hits. Keeping the last
result text, as proposed, would have shown the step's real outcome.

- [ ] Confirm: when a loop step ends without a usable result, should the
  loop record the step's last message and log "no structured result" with
  it, instead of a failure that reads "ok"? (Recommended: yes, a few lines;
  today the only way to learn what happened is to dig through the session
  transcript.)

### Proposed: The review step records a UX pass before fixing a UX finding
Status: proposed
Context: Before a PR opens, the loop reviews how the page looks and fixes
what it finds. On one PR it fixed a layout problem after recording the UX
review as passed, and never looked at the page again. Doing this makes the
step look at the fixed page, and record the review, only after its fixes.

On #84 (easyadmin 1.7.1) the review step recorded the UX review, then fixed
one of its findings (the selection bar running under the open panel) by
changing the stylesheet, and said: "I didn't re-run the UX or security
reviews after the fix, and I didn't open the new screenshots to confirm the
selection bar now clears the panel"
(`.agent/loop/steps/20261118-060040-review.json`; in
`.agent/runs/2026-11-18.jsonl` the `ux-review` row comes before the
rebuild). So the shipped CSS change was never seen, against the repo's
rule to open the screenshots before saying a page looks right. Cause:
`.claude/loop/prompts/review.md` step 2 says "Fix findings; record with
`splk review ux ...`" and step 4 only re-runs `splk dev`, which checks the
UX audit's automatic checks, not the look. Fix: step 2 says that after
fixing a UX finding the step re-runs `splk ux <app>`, opens the screenshots
that show the fix in both themes, and only then records the outcome.
Changes `.claude/loop/`, so it would be built in an interactive session.

- [ ] Confirm: should the loop's review step, after fixing something the UX
  review found, look at fresh screenshots of the fix in both themes before
  recording the UX review? (Recommended: yes, a prompt line and a few
  minutes per fix; otherwise a visible change can ship that nobody looked
  at.)

### Proposed: What the implement step leaves for the owner never reaches the roadmap
Status: proposed
Context: When the loop builds an item, it sometimes stops short of a part
that needs the owner's choice and says so only in the pull request text.
Nothing then turns that into a roadmap question, so it can be forgotten
once the PR merges. Doing this queues such leftovers for the next roadmap
grooming, as review findings already are.

On #94 (easyadmin 1.7.2) the implement step's result said a filter change
on a very large page "still takes about 0.6 s of browser layout after the
pause. Fixing that means capping or lazily drawing rows, which changes what
a box lists, so I left it for the owner"
(`.agent/loop/steps/20261118-212334-implement.json`). It went into the PR
body only. The review step's findings, which the groom reads, held two
other points and not this one (`.agent/loop/inbox/findings.md`), so it
reached the roadmap only because this groom read the loop log. Cause:
`.claude/loop/prompts/implement.md` says to put "anything left open" in the
PR body, while only `review.md` writes the findings file that
`hand_over_findings` (`tools/splk/loop.py:559`) queues for the groom. Fix:
`implement.md` also writes each point it leaves for the owner to the
findings file, in the review step's format, and `review.md` keeps entries
already in it rather than replacing the file. Changes `.claude/loop/`, so
it would be built in an interactive session.

- [ ] Confirm: should the loop's implement step queue anything it leaves for
  the owner as a proposal for the next roadmap grooming, as the review step
  already does with its findings? (Recommended: yes, a prompt line each in
  two step instructions; otherwise a choice raised only in a merged pull
  request is easily lost.)
