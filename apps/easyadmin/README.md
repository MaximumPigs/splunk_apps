# MaximumPigs Easy Admin App

App ID `easyadmin`. An administration page for Splunk Enterprise and Splunk
Cloud Platform that makes bulk changes to settings quick and visible.

It has two pages:

- **Role management** shows every role's configuration in one place, split
  into tabs. Every tab lists the roles down the side. Change as many cells as
  you like, on as many tabs as you like, then save them all at once.
- **App management** shows every app as a box holding its knowledge objects.
  Drag objects between apps, or select several and move, re-permission or
  delete them, then apply all the changes at once. See
  [App management](#app-management).

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
names every icon. An object shows its sharing (**Private**, **This app** or
**All apps**) and whether it is disabled.

Objects of these types are listed: reports and alerts, dashboards, navigation
menus, prebuilt panels, search macros, event types, tags, field extractions,
field aliases, calculated fields, automatic lookups, source type renaming,
field transformations, lookup definitions, lookup table files, workflow
actions, time ranges, data models, KV store collections and alert actions.
Private objects are listed under their app, for every user whose objects your
account can see. Objects in `$SPLUNK_HOME/etc/system` appear in a
**System (etc/system)** box, which cannot take objects.

Splunk's own apps (Search & Reporting, Home, the Monitoring Console and the
like) are hidden until you tick **Show Splunk's built-in apps**.

| Control | What it does |
| --- | --- |
| **Filter objects by name** and the type list | Narrow the objects in every box. Every app stays on show, so you can filter for an object and then drag it to any app. |
| Drag an object onto another app's box | Stages a move. Dragging a ticked object moves every ticked object. |
| Tick objects, then **Move to app...** and **Move** | Stages a move without dragging. |
| **Edit permissions** | Opens a panel to set sharing, owner, and read and write roles on every ticked object. Fields left unchanged keep each object's own value. |
| **Delete** | Stages the ticked objects for deletion. |
| Click an object's name | Opens a panel with its app, sharing, owner, read and write roles (all editable) and every one of its settings (read-only). |
| **Apply N changes** | Applies every staged change, after a confirmation that says how many objects are moved, re-permissioned and deleted. |
| **Discard changes** | Drops every staged change. |

A staged change is outlined and labelled on the object (`moving from search`,
`permissions changed`, `will be deleted`), and a moved object shows in the
box it is moving to. Nothing is written until **Apply**. Leaving the page
with staged changes asks first.

### Objects in an app's default folder

An object that ships in an app's `default/` folder shows a lock and the
`default` badge. Splunk cannot move or delete such an object, so the page
cannot either. Its permissions can still be changed. Whether an object is locked comes from Splunk itself
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
refuses is listed with Splunk's reason.

Role edits, and object moves, permission changes and deletions, are logged to
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
`removable` and `can_change_perms`. With `type`, `ns`, `app` and `name`, it
returns that one object with its `settings`.

`POST` takes one entry per object, addressed where the page saw it:

```json
{"changes": [
  {"type": "macro", "ns": "nobody", "app": "search", "name": "my_macro", "move_to": "my_app"},
  {"type": "savedsearch", "ns": "nobody", "app": "search", "name": "Errors",
   "acl": {"sharing": "global", "owner": "nobody", "read": ["*"], "write": ["admin"]}},
  {"type": "view", "ns": "alice", "app": "search", "name": "old_dashboard", "delete": true}
]}
```

`acl` always carries `sharing` and `owner`; `read` and `write` are ignored for
`"sharing": "user"`. An empty `write` list leaves no write roles. The response
has one result per object with `status` of `applied` or `error`, its
`message`, and `moved_to` when it was moved, plus `applied` and `failed`
counts. At most 2000 objects per request.

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
  [Objects in an app's default folder](#objects-in-an-apps-default-folder)).
- Creating and cloning apps, the configuration precedence view and JSON
  export and import are not in this version.

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
to 1.2.0 adds the App management endpoint, which also needs one restart.

## Author

[MaximumPigs](https://github.com/maximumpigs)

Licensed under Apache 2.0. See [LICENSE](LICENSE).
