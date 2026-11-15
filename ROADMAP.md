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

### Proposed: Details panel makes two splunkd calls it does not need
Status: proposed

Opening an object's details panel runs `add_explicit`
(`apps/easyadmin/bin/easyadmin_apps_core.py:357`), which calls
`gateway.current_context()` only to check for `admin_all_objects`. In
`AppsGateway.current_context` (`apps/easyadmin/bin/easyadmin_apps_rest.py`)
that is two requests: `authentication/current-context`, then the user's
`user-prefs` for the theme, which the panel never uses. So every object
clicked costs four splunkd requests instead of two. Fix: pass a flag so the
details path skips the theme lookup (or read capabilities alone), with a unit
test on a fake gateway counting the calls. This is a small saving per click,
read from the code and not timed; the dev target is too small to show it.

- [ ] Confirm: should this be done? (Recommended, low priority: small, safe,
  and every details click benefits.)

## fillcontinuous

### Proposed: Real rows lose `_raw` and other internal fields when the first row written is a filled one
Status: proposed

`FillContinuousCommand.transform` (`apps/fillcontinuous/bin/fillcontinuous.py:232`)
yields the filled result without registering its field names in
`self._record_writer.custom_fields`. splunklib fixes a chunk's output columns
from the first record written (`lib/splunklib/searchcommands/internals.py:547-551`),
and synthesised rows deliberately omit internal fields other than `_span`.
So when the first row out is a synthesised one, every real row silently loses
its other `_`-prefixed fields. Observed on the dev target (10.6.1.1):

    | makeresults count=2 | streamstats count as n
    | eval _time=if(n==1, 0, 7200), host=if(n==1,"b","a"), _raw="event ".n
    | fields - n | fillcontinuous span=1h by host
    | eval raw=_raw | table _time host raw

returns `raw` on 0 rows; swap the hosts (so the first row is real) and it is
on both real rows. The same happened with a user field `_extra`. The README
says internal fields are omitted from *synthesised* rows only. Because the
writer resets its columns per output chunk, a large result can hit this in
any later chunk too. This breaks the rule in `.claude/rules/search-commands.md`
("register every field name the chunk will produce before yielding the first
record").

Fix: before yielding, add the union of all output records' keys to
`custom_fields`; a unit test with a stub writer copying the SDK's first-record
behaviour; a live test with a synthesised first row and a multi-chunk result
that checks `_raw` and a user `_` field through a downstream `table`. Patch
version bump.

- [ ] Confirm: should this be done? (Recommended: it is a silent data loss
  bug, and the fix is a few lines.)

## Tooling

### Proposed: Audit step can change code that is then pushed unverified
Status: proposed

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

- [ ] Confirm: should this be done? (Recommended: it is a one-line check like
  groom's. It changes `tools/splk/`, which loop steps may not edit, so it
  needs an interactive session.)

### Proposed: Question issues are closed before the groom PR that answers them is merged
Status: proposed

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

- [ ] Confirm: should this be done? (Recommended: close on merge. Interactive
  session, as above.)

### Proposed: Console errors without a source in `splk shot`, and the UX audit missing the app's own REST failures
Status: proposed

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

- [ ] Confirm: should this be done? (Recommended: the URL in `splk shot` at
  least, since CLAUDE.md relies on it to "look before you claim". Interactive
  session, as above.)
