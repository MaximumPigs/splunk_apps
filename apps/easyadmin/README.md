# MaximumPigs Easy Admin App

App ID `easyadmin`. An administration page for Splunk Enterprise and Splunk
Cloud Platform that makes bulk changes to settings quick and visible.

The first page, **Index permissions**, shows which indexes every role can
search in one table: one row per role, one column per index, one checkbox per
cell. Tick and untick as many cells as you like, then save them all at once.

## The problem

Splunk's own role editor works one role at a time. Answering "which roles can
search this index?" means opening every role, and granting a new index to ten
roles means ten edit-and-save round trips. Nothing shows the whole picture.

## Using the page

Open **Easy Admin > Index permissions**.

| Control | What it does |
| --- | --- |
| **Show** | Switches the grid between *Searchable indexes* (`srchIndexesAllowed`) and *Indexes searched by default* (`srchIndexesDefault`). Unsaved changes on both are kept. |
| **Filter indexes** | Narrows the index columns to names containing the text. |
| **Add index or wildcard** | Adds a column for a name no role holds yet, such as a wildcard (`web_*`) or an index that exists only on your indexers. |
| **Save N change(s)** | Submits every pending change in one request, after a confirmation. |
| **Discard changes** | Drops all pending changes. |
| **Reload** | Fetches the current state again. Pending changes are kept. |

### Reading a cell

- **Ticked** means the index is listed on the role itself. This is the only
  thing a save changes.
- **Shaded** means the role already reaches that index without listing it,
  either through an imported role or through a wildcard. Hover over the cell
  for the reason. An empty shaded cell is therefore *not* "no access", and
  unticking cannot remove inherited access: change the role it comes from.
- **Outlined** means an unsaved change.

### Columns that are not indexes

A role can hold entries that are not indexes on this search head. They are
shown as columns so that every entry on every role can be seen and removed:

| Badge | Meaning |
| --- | --- |
| `wildcard` | A pattern such as `*` or `_*`. As in Splunk itself, a pattern only matches internal indexes when it starts with an underscore. |
| `not on this search head` | A name no index on this instance has. Common when indexes are defined only on the indexers, or after an index is deleted. |
| `added here` | A column you added with **Add index or wildcard**; it disappears on reload unless you save a tick in it. |

## How a save is applied

- **Changes are deltas.** Each role is re-read immediately before it is
  written and only the cells you changed are altered, so an edit someone else
  made since you loaded the page is not overwritten.
- **One write per role**, not per cell.
- **Not atomic across roles.** Splunk has no transaction spanning roles. Every
  role is attempted; any that Splunk refuses are listed with its reason and
  stay marked as unsaved, while the others are applied.
- **Effective immediately**, as with any role edit, for every user holding the
  role.
- A malformed request is rejected whole and changes nothing.

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
indexes granted and revoked:

```
index=_internal source=*easyadmin.log
```

## REST endpoint

The page is backed by one endpoint, which can also be scripted:

```
GET  /services/easyadmin/index_permissions
POST /services/easyadmin/index_permissions
```

`GET` returns the roles, the index rows and, per role and attribute, the
`explicit` entries and an `effective` map of inherited or wildcard-matched rows
to the reason.

`POST` takes a JSON body (or a form field `changes` holding the same list):

```json
{"changes": [
  {"role": "analyst", "field": "srchIndexesAllowed", "index": "web", "grant": true},
  {"role": "analyst", "field": "srchIndexesAllowed", "index": "main", "grant": false}
]}
```

and returns one result per role with `status` of `updated`, `unchanged` or
`error`, plus `updated`, `unchanged` and `failed` counts. `field` must be
`srchIndexesAllowed` or `srchIndexesDefault`; at most 5000 changes per request.

## Limitations

- Only `srchIndexesAllowed` and `srchIndexesDefault` are edited. Other role
  attributes, including `srchIndexesDisallowed`, are not shown.
- The index list is what the search head knows. In a distributed deployment
  whose indexes are defined only on indexers, add columns by name.
- The grid uses its own light colour scheme in both the light and dark themes.

## Compatibility

- Splunk Enterprise 9.3 or later, including 10.x, and Splunk Cloud Platform.
  9.3 is the floor because it is where Python 3.9 became the default
  interpreter.
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
