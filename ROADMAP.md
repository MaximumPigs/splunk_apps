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

### 1. Create a new app, or clone one
Status: blocked

Part of the original App management request.

- Creating or deleting an app makes splunkd ask for a restart (observed).
- [ ] Clone means copying every copyable object into the new app. Props-based
  objects, tags, lookup files and navigation cannot be copied through REST
  (see the README), so a clone would be partial. Is a partial clone, with a
  list of what was left out, acceptable?
- [ ] What does the person fill in to create an app? Options: (a) app id,
  label and visible only; (b) also description, author and version;
  (c) also a template (`barebones` or `sample_app`). Recommendation: (b),
  using the `barebones` template and version 1.0.0 by default.
- [ ] Are creating and cloning staged as pending changes and run by Apply,
  like every other change on the page, or done at once from a dialog?
  Recommendation: staged, so a clone's objects show as pending copies that
  can be discarded one by one before Apply.
- [ ] After a create or clone, splunkd asks for a restart. Should the page
  only show a notice ("restart Splunk to finish"), or also offer a restart
  button? Recommendation: notice only; a restart from an admin page affects
  every user, and whether Splunk Cloud allows it at all is unverified.

Probe first: whether `apps/local` accepts a create (with `template`) for an
admin on 9.3 and 10.x, and which of the new app's objects are visible before
the restart. Splunk Cloud may refuse app creation through REST altogether
(apps are installed there through ACS); confirm from Splunk's Cloud
documentation and say so in the README if it does.

### 2. Export and import an app as JSON
Status: blocked

Part of the original request: the whole app as a JSON object that can be
uploaded or pasted into another instance, without packaging an app.
Agreed: an import is staged as pending changes (new, changed, conflicting)
and committed with Apply; the person chooses the target app name. Lookup
CSV contents are included. Private user objects are in scope.

- [ ] An import writes objects the same way a copy does, so props-based
  objects, tags and navigation menus cannot be written (see the README), and
  lookup files may not be either (see the probe below). Options: (a) export
  them anyway and show them on import as "cannot import" with the reason;
  (b) leave them out of the export. Recommendation: (a), so the JSON is a
  complete record of the app and nothing is dropped silently. (Likely the
  same answer as the partial clone question in item 1.)
- [ ] What do "changed" and "conflicting" mean, and what does Apply do with
  each? Recommendation: "new" is absent from the target app and is created;
  "changed" exists in the target app with different settings and is
  overwritten (as a local override when it ships in the app's default
  folder); "conflicting" is a same-named object visible from another app,
  created anyway with a warning. Each can be discarded one by one before
  Apply, as staged changes already can.
- [ ] When the target instance has no user matching an object's owner, or
  lacks a role named in its permissions, what happens? Recommendation: the
  object is imported with the importing admin as owner and the missing
  roles dropped, each flagged on the pending change.

Probe first: whether a lookup file's contents can be written through REST
or a search on 9.3 and 10.x without Splunk's upload staging folder (for
example `outputlookup` run in the target app's namespace), and the largest
JSON body the page's REST endpoint accepts (upload and paste).

### 3. Edit individual settings of a knowledge object
Status: blocked

From inside the object's settings in the details panel.

- Changes to default settings are made in the object's local config.
- If the app has no local file yet, it is created in that app, and the
  object keeps its sharing and permissions.
- When viewing settings, each one shows where it is set (default or local).
  (Partly done in 1.4.0: own settings are badged `default`, `local` or
  `private`.)
- A setting set in both can show the default value on request.
- Local settings can be deleted.
- A filter searches the settings; when it has text, it shows every
  matching setting, including ones otherwise hidden (inherited defaults).
- Settings are shown in code blocks or similar, with a "copy" button on
  hover.
- [ ] Is an edit staged as a pending change and written by Apply, like the
  page's other changes, or saved at once? Recommendation: staged, with the
  old and new value shown on the pending change.
- [ ] Can the person add a setting the object does not have yet, or only
  edit and delete existing ones? Options: (a) existing only; (b) add any
  name as free text; (c) add from the settings splunkd reports for that
  object type. Recommendation: (c), with free text as a fallback for types
  where splunkd lists none.
- [ ] Which object types does this cover? Dashboards, navigation menus and
  prebuilt panels are one XML document each (their only setting is the
  XML). Recommendation: every listed type except those three, which are
  better edited in Splunk's own editors.
- [ ] If the probe below shows a single local setting cannot be removed
  through REST, what should "delete" do? Options: (a) leave delete out and
  say why in the README; (b) "reset to default" by writing the default value
  into local, which stops inheriting later changes to the default; (c) offer
  delete on Splunk Enterprise only, through file writes, if AppInspect
  allows it. Recommendation: (a), since (b) looks like a delete but is not
  one.

Probe first: splunkd's REST API sets a value but has no call to remove
one attribute from local while keeping the default. Posting an empty value
overrides it with empty instead. Deleting a local setting may need the
configuration endpoints (merged, see the copy lessons) or file writes, which
Splunk Cloud does not allow.

### Low priority: Deployment apps portal
Status: blocked

A portal like App management, for the deployment server's apps.

- [ ] More requirements are to be gathered when this work starts: which of
  the points below are in the first version, and are you happy for it to be
  Splunk Enterprise only (files on the deployment server)?

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
  app).
