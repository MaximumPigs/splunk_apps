# MaximumPigs Easy Admin App

App ID `easyadmin`. An administration page for Splunk Enterprise and Splunk
Cloud Platform that makes bulk changes to settings quick and visible.

Its page, **Role management**, shows every role's configuration in one place,
split into tabs. Every tab lists the roles down the side. Change as many cells
as you like, on as many tabs as you like, then save them all at once.

## The problem

Splunk's own role editor works one role at a time. Answering "which roles can
search this index?" or "who holds this capability?" means opening every role,
and granting a new index to ten roles means ten edit-and-save round trips.
Nothing shows the whole picture.

## The tabs

| Tab | Columns | Role attributes |
| --- | --- | --- |
| **Indexes** | every index, one checkbox each | `srchIndexesAllowed`, `srchIndexesDefault`, `srchIndexesDisallowed`, `deleteIndexesAllowed` |
| **Capabilities** | every capability Splunk defines, one checkbox each | `capabilities` |
| **Inheritance** | every role, one checkbox each | `imported_roles`, `grantable_roles` |
| **Search limits** | one field per setting | `srchJobsQuota`, `rtSrchJobsQuota`, `cumulativeSrchJobsQuota`, `cumulativeRTSrchJobsQuota`, `queuedSearchQuota`, `srchDiskQuota`, `srchTimeWin`, `srchTimeEarliest`, `srchMinScheduleInterval`, `srchAllowAdvancedCron`, `srchFilter`, `defaultApp` |
| **Federated and KV store** | one field per setting | `federatedProviders`, `srchFederatedProvidersAllowed`, `srchFederatedProvidersDefault`, `fieldFilterExemption`, and the `kvstore_create`, `kvstore_update` and `kvstore_delete` deny lists |

Between them they cover every role attribute Splunk lets you write, except the
per-pattern `srchMinScheduleInterval.<pattern>` family. Each column header
shows the attribute's name as well as its label, so you can look it up in
`authorize.conf`.

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
numbers, since Splunk uses `-1` in some (a stock `user` role has
`srchTimeWin = -1`). The advanced cron setting is a checkbox (on is `1`).

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
- A malformed request is rejected whole and changes nothing.
- **Field filter exemptions can only be added.** Splunk's roles API appends
  whatever is written to `fieldFilterExemption` and offers no way to remove
  an entry, so the app writes only new entries and refuses a save that
  removes one, saying which entries and writing nothing on that role.

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

Role edits made through the app are logged to
`$SPLUNK_HOME/var/log/splunk/easyadmin.log`, with the user, the role and the
attributes written:

```
index=_internal source=*easyadmin.log
```

## REST endpoint

The page is backed by one endpoint, which can also be scripted:

```
GET  /services/easyadmin/roles
POST /services/easyadmin/roles
```

`GET` returns `roles`, `can_edit`, `user_roles` and `tabs`. A checkbox tab
(`"type": "matrix"`) has `fields`, `columns` and, per role and attribute,
`explicit` entries and an `effective` map of other items to the reason. A
settings tab (`"type": "settings"`) has `fields` (with a `kind` of `int`,
`flag`, `text` or `list`) and, per role and attribute, `value` and `imported`.

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

## Limitations

- **Indexes events can be deleted from** (`deleteIndexesAllowed`) can only be
  set on a role that itself holds the `delete_by_keyword` capability; on
  other roles Splunk refuses the save (HTTP 403), and the page reports it.
- On Splunk Enterprise 10.6.1 with no federated providers defined, Splunk
  refuses an administrator's write to **Federated providers**
  (`federatedProviders`) with HTTP 403; the page reports it. Other
  federated settings save normally.
- Field filter exemptions cannot be removed here (see above).

- The index list is what the search head knows. In a distributed deployment
  whose indexes are defined only on indexers, add columns by name.
- Roles cannot be created or deleted here; use **Settings > Roles**.

## Compatibility

- Splunk Enterprise 9.3 or later, including 10.x, and Splunk Cloud Platform.
  9.3 is the floor because it is where Python 3.9 became the default
  interpreter. Tested on Splunk Enterprise 10.6.1 only. The tabs list the role
  attributes 10.6.1 accepts; some, such as the KV store deny lists, may not
  exist on older versions.
- Runs on Python 3.9 and Python 3.13. `restmap.conf` declares both
  `python.version = python3` and `python.required = 3.9, 3.13`.
- Search head only. Uses the Python modules Splunk ships (`splunk.rest`,
  `splunk.persistconn`); nothing is vendored.
- Opens no outbound network connections and collects no data.

## Installation

Install the `.spl` through **Apps > Manage Apps > Install app from file** on
the search head. On a search head cluster, deploy it with the deployer. If the
page reports that its endpoint was not found, restart Splunk once.

## Author

[MaximumPigs](https://github.com/maximumpigs)

Licensed under Apache 2.0. See [LICENSE](LICENSE).
