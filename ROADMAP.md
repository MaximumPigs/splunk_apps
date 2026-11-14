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
| 1.4.0 (branch `feature/easyadmin-clone-objects`) | Copy objects into another app (the default for objects in a default folder); discard one staged change; the object's own settings in the panel; locks from splunkd's `removable` flag. |

### 1. Create a new app, or clone one
Status: blocked

Part of the original App management request.

- Creating or deleting an app makes splunkd ask for a restart (observed).
- [ ] Clone means copying every copyable object into the new app. Props-based
  objects, tags, lookup files and navigation cannot be copied through REST
  (see the README), so a clone would be partial. Is a partial clone, with a
  list of what was left out, acceptable?

### 2. Export and import an app as JSON
Status: ready

Part of the original request: the whole app as a JSON object that can be
uploaded or pasted into another instance, without packaging an app.
Agreed: an import is staged as pending changes (new, changed, conflicting)
and committed with Apply; the person chooses the target app name. Lookup
CSV contents are included.

### 3. Edit individual settings of a knowledge object
Status: ready

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
