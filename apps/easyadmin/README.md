# MaximumPigs Easy Admin App

App ID `easyadmin`. An administration page for Splunk Enterprise and Splunk
Cloud Platform that makes bulk changes to settings quick and visible.

It has two pages:

- **Role management** shows every role's configuration in one place, split
  into tabs. Every tab lists the roles down the side. Change as many cells as
  you like, on as many tabs as you like, then save them all at once.
- **App management** shows every app as a box holding its knowledge objects.
  Drag objects between apps, or select several and move, copy,
  re-permission or delete them, then apply all the changes at once. Create a
  new app, or clone one with copies of its objects, in the same way. A second tab,
  **Configuration precedence**, shows like btool which file every setting
  comes from and where apps set the same setting differently. See
  [App management](#app-management) and
  [Configuration precedence](#configuration-precedence).

## The problem

Splunk's own role editor works one role at a time. Answering "which roles can
search this index?" or "who holds this capability?" means opening every role,
and granting a new index to ten roles means ten edit-and-save round trips.
Nothing shows the whole picture.

## The tabs

The app changes exactly what Splunk Web's own role editor (**Settings >
Roles**, then a role's name) can change, and nothing more. Its tabs follow
the editor's: each attribute below was matched to the editor's control on
Splunk Enterprise 10.6.1.

| Tab | Columns | Role attributes | Editor tab and control |
| --- | --- | --- | --- |
| **Indexes** | every index, one checkbox each | `srchIndexesAllowed`, `srchIndexesDefault` | Indexes: *Included*, *Default* (and its wildcard box) |
| **Capabilities** | every capability Splunk defines, one checkbox each | `capabilities` | Capabilities |
| **Inheritance** | every role, one checkbox each | `imported_roles` | Inheritance |
| **Providers** | one field per setting | `srchFederatedProvidersAllowed`, `srchFederatedProvidersDefault` | Providers: *Included*, *Default* (and its wildcard box) |
| **Restrictions** | one field | `srchFilter` | Restrictions: *Search filter* |
| **Resources** | one field per setting | `defaultApp`, `cumulativeSrchJobsQuota`, `cumulativeRTSrchJobsQuota`, `srchJobsQuota`, `rtSrchJobsQuota`, `srchTimeWin`, `srchTimeEarliest`, `srchDiskQuota` | Resources: *Default app*, *Standard* and *Real-time role search limit*, *Standard* and *Real-time user search limit*, *Role search time window limit*, *earliest searchable event time*, *Disk space limit* |

Role attributes Splunk's REST API accepts but the editor does not offer are
neither shown nor accepted: `srchIndexesDisallowed`, `deleteIndexesAllowed`,
`grantable_roles`, `queuedSearchQuota`, `srchMinScheduleInterval`,
`srchAllowAdvancedCron`, `federatedProviders`, `fieldFilterExemption` and the
KV store deny lists. Each column header shows the attribute's name as well as
its label, so you can look it up in `authorize.conf`.

A tab with several attributes has a **Show** selector to switch between them.
A tab with unsaved changes shows how many on its label.

## Using the page

Open **Easy Admin > Role management**.

| Control | What it does |
| --- | --- |
| **Filter** | Narrows the columns (checkbox tabs) or the roles (settings tabs) to names containing the text. |
| **Add a column by name** | On a checkbox tab, adds a column for a name no role holds yet, such as a wildcard (`web_*`) or an index that exists only on your indexers. |
| **Save N change(s)** | Submits every pending change, on every tab, in one request, after a confirmation. |
| **Discard changes** | Drops all pending changes. |
| **Reload** | Fetches the current state again. Pending changes are kept. |

The app follows the light or dark theme chosen in your Splunk account
preferences. Classic dashboards do not pick that preference up on their own,
so when Splunk draws the page in the other theme, the page reloads itself
once with `?theme=light` or `?theme=dark` in the address.

The confirmation warns you when the save changes a role you hold yourself,
since removing capabilities from your own roles can lock you out of the page.

### Reading a checkbox

- **Ticked** means the item is listed on the role itself. This is the only
  thing a save changes.
- **Shaded** means the role already has the item without listing it. It may
  come from an imported role (including roles further up the inheritance
  chain, on the Inheritance tab) or from a wildcard (on the Indexes tab).
  Hover over the cell for the reason. Unticking cannot remove inherited
  access: change the role it comes from.
- **Outlined** means an unsaved change.

Splunk lists a capability a role also gets from an imported role only under
the imported role, so such a capability shows as shaded rather than ticked,
even if it was set on the role too.

### Columns that are not known items

A role can hold entries that are not indexes, capabilities or roles on this
search head. They are shown as columns so that every entry on every role can
be seen and removed:

| Badge | Meaning |
| --- | --- |
| `wildcard` | A pattern such as `*` or `_*`. As in Splunk itself, a pattern only matches internal indexes when it starts with an underscore. |
| `not known here` | A name this instance has no index, capability or role for. Common when indexes are defined only on the indexers, or after something is deleted. |
| `added here` | A column you added with **Add a column by name**; it disappears on reload unless you save a tick in it. |

### Settings tabs

Each field holds the value set on the role itself. Beneath it, **imported**
shows the value the role's imported roles provide, where there is one. List
settings are edited comma-separated. Whole-number settings accept negative
numbers, since Splunk uses `-1` for "unset" (a stock `user` role has
`srchTimeWin = -1`). The editor shows the time window and earliest event
time as drop-down lists; here they are typed as a number of seconds. As the
editor says, a search job limit of `0` means no limit.

## How a save is applied

- **Checkbox changes are deltas.** Each role is re-read immediately before it
  is written and only the items you changed are altered, so an item someone
  else added since you loaded the page is kept.
- **Settings changes are checked first.** A setting is written only if the
  role still has the value the page loaded. If someone changed it in the
  meantime, nothing on that role is written and the page says which setting
  changed; reload and decide again.
- **One write per role**, however many tabs the changes were on.
- **Not atomic across roles.** Splunk has no transaction spanning roles. Every
  role is attempted; any that Splunk refuses are listed with Splunk's reason
  and stay marked as unsaved, while the others are applied.
- **Effective immediately**, as with any role edit, for every user holding the
  role.
- A malformed request, or one naming an attribute the app does not edit, is
  rejected whole and changes nothing.

## App management

Open **Easy Admin > App management**. Every app is a box, in alphabetical
order of the name in its title. Each box lists the app's knowledge objects,
grouped by type, each with an icon for its type. The legend above the boxes
names every icon. An object shows its sharing, colour-coded and in words:
**Private** (purple), **This app** (blue), **All apps** (green), or **System**
for objects in `etc/system`. It also shows whether it is disabled.

Objects of these types are listed: reports and alerts, dashboards, navigation
menus, prebuilt panels, search macros, event types, tags, field extractions,
field aliases, calculated fields, automatic lookups, source type renaming,
field transformations, lookup definitions, lookup table files, workflow
actions, time ranges, data models, KV store collections and alert actions.
Private objects are listed under their app, for every user whose objects your
account can see. Objects in `$SPLUNK_HOME/etc/system` appear in a
**System (etc/system)** box, which cannot take objects.

Splunk's own apps (Home, the Monitoring Console and the like) are hidden
until you tick **Show Splunk's built-in apps**. Search & Reporting and
Enterprise Security (`SplunkEnterpriseSecuritySuite`) are always shown with
the installed apps, since that is where users keep their objects.

At first the page shows the types users create day to day: reports and
alerts, dashboards, search macros, event types, tags, field extractions,
field aliases, calculated fields, automatic lookups, lookup definitions,
lookup table files, workflow actions and data models. The administrator's
types (navigation menus, prebuilt panels, source type renaming, field
transformations, time ranges, KV store collections and alert actions) are
added from the **Types** menu.

| Control | What it does |
| --- | --- |
| **Filter objects by name** and **Types** | Narrow the objects in every box. **Types** is a drop-down of every type, with shortcuts for the common types, all and none. Every app stays on show, so you can filter for an object and then drag it to any app. |
| **Filter apps by name** | Shows only the apps whose name or label contains the text. An app with staged changes stays on show. |
| The tick box in an app's title | Selects every object shown in that app (after the filters). It is half-ticked when only some are selected. |
| Drag an object onto another app's box | Stages a move, or a copy for an object that ships in a default folder (which cannot be moved). Hold Ctrl (Cmd on a Mac) while dropping to copy instead. Dragging a ticked object takes every ticked object. |
| Tick objects, then **To app...** and **Move** or **Copy** | Stages a move or a copy without dragging. **Move** copies the objects that cannot be moved, as a drop does, and says so. |
| **Edit permissions** | Opens a panel to set sharing, owner, and read and write roles on every ticked object. Fields left unchanged keep each object's own value. |
| **Delete** | Stages the ticked objects for deletion. |
| **New app...**, and **Clone...** in an app's title | Opens a form to stage a new app, or a clone of that app with copies of its objects: see [Creating and cloning apps](#creating-and-cloning-apps). Shown only to accounts that can create apps. |
| A **new app** or **clone of** box, outlined with dashes | An app that exists only as a staged change. It takes objects like any other app, and its × drops the app and every change staged into it, after asking. Its header counts the objects it holds and the copies staged into it, for example "0 objects, 60 staged". |
| Click an object's name | Opens a panel with its app, sharing, owner, read and write roles (all editable), **Copy to app**, and its settings, which can be filtered, copied and edited: see [Settings in the panel](#settings-in-the-panel). |
| **Apply changes to N objects** | Applies every staged change, after a confirmation that says how many apps are created and how many objects are moved, copied, re-permissioned and deleted. New apps are created first. |
| The × on a staged-change badge | Drops that one change (a move, a copy, a permission change, edited settings or a deletion) and keeps the object's other staged changes. A staged copy's dashed row in the other app has one too. |
| **Discard changes** | Drops every staged change, after asking. |

A staged change is outlined and labelled on the object (`moving from search`,
`copying to launcher`, `permissions changed`, `will be deleted`). A moved
object shows in the box it is moving to; a staged copy shows there as a
dashed `copy from` row, and the original stays where it is.

The filters narrow what a box lists, but a clone copies every type. Copies the
**Types** menu or the name filter keep out of a box are counted in a line at
its foot ("1 staged copy is hidden by the filters."), and a box that has such
copies stays on show whatever the app filter says.

### Creating and cloning apps

**New app...** opens a form with these fields:

| Field | Rule |
| --- | --- |
| App ID | Required. The directory name: letters, digits, `_`, `-` and `.`, starting with a letter, digit or `_`, at most 100 characters. It must not be taken, ignoring case (on Windows and macOS `Search` and `search` are one directory), and `system` is reserved. |
| Label | Required. 5 to 80 characters, not starting with "Splunk for" (Splunk's own rule for app labels). |
| Visible | Ticked by default: the app is listed in the app menu. |
| Description, Author | Optional. The author is pre-filled with your user name. |
| Version | `1.0.0` unless you change it. |

The app is made from Splunk's `barebones` template; the form offers no other.
The page checks each field as you type, with the reason beside it, and the
server checks them again.

**Clone...** in an app's title opens the same form, pre-filled with
`<id>_copy` (or the next free name), the label `<label> (copy)`, and the
source's description and author. Staging it adds the new app **and** a
staged copy of every object in the source that can be copied: private
objects too, each with its owner, sharing and read and write roles, as for
[any copy](#copying-objects). It ignores the filters on the page. The message
after staging lists what was left out, by type: props-based objects, tags,
lookup table files and navigation menus cannot be copied, so a clone is
partial, and the new app has the barebones template's own navigation menu.
Objects that already had a staged move, copy or deletion are not copied, and
the message says so. Each copy shows as a dashed row in the new app's box and
can be discarded on its own before **Apply**. A clone of more than 2000
objects is refused (the limit of one apply).

Nothing is created until **Apply**. The new app's own permissions are
splunkd's defaults for a new app (everyone may read it; `admin` and `power`
may write). It needs the `admin_all_objects` or `edit_local_apps` capability;
without one the buttons are not shown and the endpoint answers 403.

The page never restarts Splunk. On Splunk Enterprise 10.6.1 creating an app,
and creating objects in it, asked for no restart (observed); splunkd does ask
for one when an app is deleted. If splunkd does ask after an apply, the page
shows a notice (hideable) that tells you to restart from **Settings > Server
controls** when it suits your users. That notice has not been seen in a
browser, because creating an app does not trigger it on the test instance.

Apps are created before the objects. If an app cannot be created, it stays
staged with its copies, the changes aimed at it are reported as not
attempted, and everything else is applied. An app that was created is never
removed again by the page, even if copying into it partly failed: the failed
copies stay staged and can be applied again.

### Settings in the panel

The panel lists the settings set in the object itself: those in its
`[<name>]` stanza in its app's `default` and `local` files, or in the owner's
folder for a private object, each marked `default`, `local` or `private`.
Settings it only inherits, from `[default]` stanzas and `etc/system/default`,
are left out; **Show all N settings, including inherited defaults** lists
everything splunkd reports for it.

Like the precedence tab, this reads the configuration files, so it needs the
`admin_all_objects` capability; without it the panel lists every setting, as
splunkd reports them, and nothing can be edited. It applies to objects kept
as a stanza: reports and alerts, search macros, event types, tags, field
transformations, lookup definitions, workflow actions, time ranges, data
models, KV store collections and alert actions. A props-based object (field
extraction, field alias, calculated field, automatic lookup, source type
renaming) is a single line of a stanza that other objects share, so it shows
and edits that one line only. Dashboards, navigation menus and prebuilt
panels are XML files whose settings are all their own, and are better edited
in Splunk's own editors; lookup table files are not settings at all.

**Filter settings** searches the names and values of the settings. With text
in it, every matching setting is listed, including settings the object only
inherits, each labelled `inherited`. Each value is in a code block with a
**Copy** button, drawn when the block is hovered or has keyboard focus (and
read out as "Copied"). There is no Copy for a masked secret or a value that is
shown shortened (values over 4000 characters are cut).

A setting set in more than one place (default and local, or local and the
owner's private folder) has **Show default value**, which lists the value it
hides.

#### Editing settings

**Edit** on one of the object's own settings, or **Add a setting**, stages the
change like any other: the setting is outlined, with the old value (struck
through) and the new one, and nothing is written until **Apply**. The × on the
object's `settings changed (N)` badge, or **Discard this change**, drops it.

- The change is written to the object's own local configuration: the
  `local` folder of its app (created when the app had no such file), the
  owner's private folder for a private object, or `etc/system/local` for an
  object in `etc/system`. Settings in `default` are never touched; an edit of
  one writes a local setting that overrides it, and that local setting then
  stays when the default changes. The object keeps its sharing, owner and
  roles (observed on 10.6.1 for every kind below).
- The write goes to splunkd's `configs/conf-<file>/<stanza>` endpoint, which
  writes just the keys posted. The object kind's own endpoint was not used:
  on 10.6.1 it refuses a partial edit (a macro needs its `definition` and
  `args` again, a transformation its `REGEX`), and one of them dropped a
  field alias that was not posted.
- Add a setting from the names splunkd reports for that kind of object (an
  `Add a setting` box with the list, plus the patterns it reports, such as
  `dispatch.*` for reports). A name outside them is refused. Splunkd lists no
  settings for tags and alert actions (it reports other keys than the file's),
  so for those the name is free text. A props-based object adds nothing: it
  is the one line.
- Needs `admin_all_objects` and write access to the object. Secrets (names
  such as `password` or `token`) are masked on the page and cannot be edited
  here.
- A value may run over several lines (searches and macros do). A value with
  a line that looks like `[stanza]` or `key = value` did not create a second
  stanza or key on 10.6.1: splunkd stored it as one value, which read back
  unchanged. Control characters other than newline and tab are refused.
- If a setting changed in the file after the page loaded it, the edit is
  refused ("changed since the page loaded") and nothing is written.
- Splunkd can answer success and write nothing (seen for props and tags
  when copying), so after each write the file is read back, and a setting that
  did not arrive is reported as an error.
- Settings are written first; if a move or a permission change on the same
  object then fails, the page says that the settings were changed.

#### Why local settings cannot be deleted

No REST call removes one setting from a file while keeping the default
(observed on 10.6.1, with the settings read back from the files):

- `DELETE .../properties/<file>/<stanza>/<key>` answers HTTP 400 "Key deletion
  is not supported", for an object that ships a default and for a local-only one;
- `DELETE .../configs/conf-<file>/<stanza>` removes the whole local-only
  object, and for an object that ships in `default` is refused ("cannot be
  deleted in config");
- posting an empty value writes `key =` into local, an empty override, and
  posting the default value back keeps the key in local, so neither is a
  delete.

Writing files directly is not possible on Splunk Cloud, so the page has no
delete for a setting. To remove a local setting, edit the `local` file, or use
Splunk's own editor where it offers one. The settings added or changed here
are the ones that remain.

### Copying objects

A copy is a second object with the same name, settings, owner, sharing and
read and write roles, in another app. The original is not changed. A copy is
refused when the other app already has an object of that type and name (one
that lives in that app, not one shared with it from elsewhere).

A copy is made by creating the object again through splunkd with the
original's settings. These types cannot be copied:

- field extractions, field aliases, calculated fields, automatic lookups,
  source type renaming and tags: splunkd does not accept them back through
  their own endpoints, and its configuration endpoints merge them across
  apps, so a copy could not be written reliably;
- lookup table files, which need Splunk's upload staging folder;
- navigation menus, which belong to their app. Nothing is written until **Apply**. Leaving the page
with staged changes asks first.

### Objects in an app's default folder

An object that ships in an app's `default/` folder shows a lock and the
`default` badge. Splunk cannot move or delete such an object, so the page
cannot either. (Splunk still lists move and delete actions for a report in
a default folder, then refuses them; the page goes by Splunk's `removable`
flag instead. Should Splunk refuse a move anyway, the page stages a copy in
its place and asks you to apply again.) It can be copied to another app (dragging it there stages a
copy), and its permissions can still be changed. Whether an object is locked comes from Splunk itself
for each object, not from a list kept by this app.

Lookup table files are not split into default and local folders, and Splunk
lets them be moved and deleted.

### How changes are applied

- Each object is re-read just before it is changed. If it is no longer where
  the page saw it (someone moved, renamed or deleted it meanwhile), it is not
  touched, the page says so, and a reload shows where it is now.
- A move keeps the object's owner and sharing. A private object stays private
  to its owner.
- When one object is moved and re-permissioned, the move happens first and
  the permissions are set in the new app. If the move works but the
  permissions are refused, the page says so and keeps the permission change
  staged to retry.
- Not atomic across objects. Every object is attempted; any that Splunk
  refuses are listed with its reason and stay staged, while the others are
  applied.

## Configuration precedence

The **Configuration precedence** tab of the App management page (or
`app_management#precedence`) answers "which app's setting wins?". Pick a
configuration file, such as `props.conf`. The tab lists each stanza that has a
setting with different values in different places, and for each such setting
every place it is set, highest priority first. For a file that is not read
at search time, the first is marked **in effect** and the others are marked
**overridden** and struck through.

Like `splunk btool <conf> list --debug`, it reads the `.conf` files of every
app's `default` and `local` folders and of `etc/system`. It does not use the
REST API, because splunkd returns only the merged result there and cannot say
which app or folder set a value. The order is Splunk's global one:

1. `etc/system/local`
2. each app's `local` folder, apps in ASCII order of their directory names
   (uppercase before lowercase)
3. each app's `default` folder, in the same order
4. `etc/system/default`

Settings used at search time (field extractions, lookups, event types and the
like) are resolved per app instead: the app a search runs in, and each
object's sharing, decide which value applies. The tab shows the global order
only. For files read at search time (`props`, `transforms`, `macros`,
`eventtypes`, `tags`, `savedsearches` and others) it says so above the list,
and labels the values **first in global order** and **later in global
order**, with none struck through, rather than claiming one is in effect
everywhere. The explanation of the order is under **How the order works**.

| Control | What it does |
| --- | --- |
| Configuration file | Which `.conf` file to show. `passwords.conf` is never read. |
| **Filter stanzas** | Shows only stanzas whose name contains the text. |
| App list | Shows only stanzas that app sets something in. |
| **Include stanzas without conflicts** | Lists every stanza, not just those with conflicting values. |
| **Show N more settings set in one place only** | In a stanza, also lists the settings only one file sets. |

A setting set to the same value in two places is marked **same value**: it is
overridden, but nothing changes. Passwords, keys and tokens (`pass4SymmKey`,
`sslPassword` and the like) are marked **secret, hidden**: the tab shows where
they are set, never their values. Secrets are recognised by the setting's
name (ending in `password`, `pass4SymmKey`, `secret`, `token`, `_key` and
similar), so a secret inside an ordinary-looking value, such as a webhook URL,
is shown to the administrator viewing the tab.

The tab is read-only. It needs the `admin_all_objects` capability (which
`admin` and `sc_admin` hold), because reading the files bypasses Splunk's
per-object permissions.

## Permissions and security

The app never elevates. Every read and write is made to splunkd with the
session of the user who is logged in, so Splunk applies that user's own
capabilities:

- Saving needs `edit_roles` or `edit_roles_grantable` (what `sc_admin` holds on
  Splunk Cloud). Without either, the page is read-only.
- With `edit_roles_grantable`, Splunk limits which roles and values the user
  may grant, exactly as it does in Settings. Refusals are reported per role.
- The app is visible to `admin` and `sc_admin` by default. To open it to
  another role, change the app's read permission in **Apps > Manage Apps**.

On the App management page, what you can move, re-permission or delete is
what Splunk lets your account do in **Settings > Knowledge**. Anything it
refuses is listed with Splunk's reason. Creating or cloning an app needs the
`admin_all_objects` or `edit_local_apps` capability (the two Splunk names when
it refuses a create); an account with neither gets HTTP 403 and no buttons. The
page sends only the app's ID, label, visibility, description, author and
version, with the `barebones` template. It never sends the settings with which
Splunk installs an app from a file or a URL, and the endpoint refuses a request
that carries them.

Role edits, object moves, copies, permission changes, settings edits (the
names of the settings, never their values) and deletions, and app creations
are logged to
`$SPLUNK_HOME/var/log/splunk/easyadmin.log`, with the user, the role or
object, and what was written:

```
index=_internal source=*easyadmin.log
```

## REST endpoints

Each page is backed by one endpoint, which can also be scripted.

### Role management

```
GET  /services/easyadmin/roles
POST /services/easyadmin/roles
```

`GET` returns `roles`, `can_edit`, `user_roles` and `tabs`. A checkbox tab
(`"type": "matrix"`) has `fields`, `columns` and, per role and attribute,
`explicit` entries and an `effective` map of other items to the reason. A
settings tab (`"type": "settings"`) has `fields` (with a `kind` of `int`,
`text` or `list`) and, per role and attribute, `value` and `imported`.

`POST` takes a JSON body (or a form field `changes` holding the same list):

```json
{"changes": [
  {"role": "analyst", "field": "srchIndexesAllowed", "item": "web", "grant": true},
  {"role": "analyst", "field": "capabilities", "item": "schedule_search", "grant": false},
  {"role": "analyst", "field": "srchJobsQuota", "value": "6", "previous": "3"}
]}
```

`previous` is the value the change was based on. The response has one result
per role with `status` of `updated`, `unchanged` or `error`, plus `updated`,
`unchanged` and `failed` counts. At most 5000 changes per request.

### Configuration precedence

```
GET /services/easyadmin/conf
GET /services/easyadmin/conf?conf=props
GET /services/easyadmin/conf?conf=props&all=1
```

Needs `admin_all_objects`. Without `conf` it returns `confs`, the names of
the `.conf` files found. With `conf` it returns `order` (the folders that
have that file, highest priority first) and `stanzas`: each with its
`conflicts` count, the `apps` that set something in it, and `settings`, plus
`search_time` when the file is read per app at search time. Each
setting has `conflict`, `overridden`, `secret` and `sources` (`app`, `layer`,
`value`, `effective`), highest priority first. Only stanzas with a conflict
are returned unless `all=1`.

### App management

```
GET  /services/easyadmin/apps
GET  /services/easyadmin/apps?type=macro&ns=nobody&app=search&name=my_macro
POST /services/easyadmin/apps
```

`GET` returns `types`, `apps` (with `label`, `builtin` and `target`, whether
objects can be moved into it), `objects`, `roles`, `users` and `warnings`
(object types your account cannot list). Each object has `type`, `name`,
`app`, `ns` (the namespace it lives in: its owner for a private object,
`nobody` otherwise), `owner`, `sharing`, `read`, `write`, `movable`,
`copyable`, `removable` and `can_change_perms`. With `type`, `ns`, `app` and `name`, it
returns that one object with its `settings` (all, as splunkd reports them) and,
for callers with `admin_all_objects`, `explicit`: the settings set in its own
files, each with `name`, `value`, `layer` (`default`, `local` or `user`),
`truncated`, `secret` and `overrides` (the values it hides, lowest layer
first). It also has `editable`, `edit_layer` (`local` or `user`, where an edit
lands) and `edit_note` (why it is not editable: `kind`, `capability` or
`write`), `addable` (setting names splunkd lists that the object does not
set), `addable_patterns` (the patterns it reports) and `free_text`.

`GET` also returns `can_create_apps` (whether your account holds
`admin_all_objects` or `edit_local_apps`), and each app has `description`
and `author`.

`POST` takes one entry per object, addressed where the page saw it:

```json
{"changes": [
  {"type": "macro", "ns": "nobody", "app": "search", "name": "my_macro", "move_to": "my_app"},
  {"type": "savedsearch", "ns": "nobody", "app": "search", "name": "Errors",
   "acl": {"sharing": "global", "owner": "nobody", "read": ["*"], "write": ["admin"]}},
  {"type": "view", "ns": "alice", "app": "search", "name": "old_dashboard", "delete": true}
]}
```

`copy_to` (an app name) creates a copy there instead of moving; it cannot be
combined with `move_to` or `delete`. `settings` is a list (at most 200) of
`{"name", "value", "previous"}`, where `previous` is the value the caller read
(`null` for a setting the object did not set) and an edit is refused when the
file has another; it can go with `move_to`, `copy_to` and `acl`, not with
`delete`, and its names and values are validated (no `=`, `[`, `#`, `eai:` or
secret names, values up to 65536 characters, control characters other than
newline and tab refused). Each result also has `settings_applied`. `acl` always carries `sharing` and `owner`; `read` and `write` are ignored for
`"sharing": "user"`. An empty `write` list leaves no write roles. The response
has one result per object with `status` of `applied` or `error`, its
`message`, and `moved_to` when it was moved, plus `applied` and `failed`
counts. At most 2000 objects per request.

To create apps, add an `apps` list (at most 20) beside `changes`; `changes`
may then be empty:

```json
{"apps": [{"name": "my_app", "label": "My App", "visible": true,
           "description": "Optional", "author": "Optional", "version": "1.0.0"}],
 "changes": [{"type": "macro", "ns": "nobody", "app": "search", "name": "m", "copy_to": "my_app"}]}
```

Only those six keys are accepted (`version` defaults to `1.0.0`, `visible` to
`true`); anything else, such as `template` or `filename`, is refused with HTTP
400, as are an ID or label that breaks the rules above and an ID that exists
(ignoring case). A caller without the capabilities gets 403. Apps are created
first. The response gains `apps` (one `name`, `status` and `message` per app,
counted in `applied` and `failed`) and `restart_required`, read from splunkd
once everything has run. A change whose `move_to` or `copy_to` names an app that
was not created is not attempted and is reported as an error.

## Limitations

- Only what the role editor can change (see [The tabs](#the-tabs)). For
  the other attributes, such as `srchIndexesDisallowed` or the KV store deny
  lists, edit `authorize.conf`.
- The Providers tab takes provider names as text; it does not list the
  federated providers defined on the instance or check that a name is a
  transparent-mode provider, as the editor does.
- The index list is what the search head knows. In a distributed deployment
  whose indexes are defined only on indexers, add columns by name.
- Roles cannot be created or deleted here; use **Settings > Roles**.
- App management lists the knowledge object types above. Inputs, indexes and
  search commands are not listed.
- Objects in an app's `default/` folder cannot be moved or deleted (see
  [Objects in an app's default folder](#objects-in-an-apps-default-folder));
  copy them instead.
- Props-based objects (field extractions, aliases, calculated fields,
  automatic lookups, source type renaming), tags, lookup table files and
  navigation menus cannot be copied.
- A local setting cannot be deleted (see
  [Why local settings cannot be deleted](#why-local-settings-cannot-be-deleted)),
  and dashboards, navigation menus, prebuilt panels and lookup table files
  are not edited setting by setting.
- Editing settings has been tried on Splunk Enterprise 10.6.1 only. It uses
  splunkd's `configs` REST endpoint and never writes files itself, but it has
  not been tried on Splunk Cloud Platform, nor on 9.3.
- The configuration precedence tab shows Splunk's global order. It does not
  model the per-app order used at search time, or settings in `etc/users`.
- A clone is partial: props-based objects, tags, lookup table files and
  navigation menus are left out (see
  [Creating and cloning apps](#creating-and-cloning-apps)). Apps cannot be
  deleted here: splunkd needs a restart to finish a delete, and this page
  never restarts Splunk.
- Creating and cloning apps use Splunk's `apps/local` endpoint. Splunk's REST
  reference says its application endpoints are not available on Splunk Cloud
  Platform, where apps are installed through **Manage Apps** or the Admin
  Config Service, so expect Splunk to refuse there (the page reports its
  reason for each app). This has not been tried on Cloud, nor on Splunk 9.3;
  it was observed on Splunk Enterprise 10.6.1 only.
- JSON export and import are not in this version yet.

## Compatibility

- Splunk Enterprise 9.3 or later, including 10.x, and Splunk Cloud Platform.
  9.3 is the floor because it is where Python 3.9 became the default
  interpreter. Tested on Splunk Enterprise 10.6.1 only. The tabs match the
  10.6.1 role editor; older versions' editors may offer fewer attributes.
- Runs on Python 3.9 and Python 3.13. `restmap.conf` declares both
  `python.version = python3` and `python.required = 3.9, 3.13`.
- Search head only. Uses the Python modules Splunk ships (`splunk.rest`,
  `splunk.persistconn`); nothing is vendored.
- Opens no outbound network connections and collects no data.

## Installation

Install the `.spl` through **Apps > Manage Apps > Install app from file** on
the search head. On a search head cluster, deploy it with the deployer. If a
page reports that its endpoint was not found, restart Splunk once. Upgrading
to 1.2.0 or 1.3.0 adds an endpoint, which also needs one restart.

## Author

[MaximumPigs](https://github.com/maximumpigs)

Licensed under Apache 2.0. See [LICENSE](LICENSE).
