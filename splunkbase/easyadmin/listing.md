# easyadmin - Splunkbase listing

Copy each section below into the matching field on the Splunkbase upload form.
See ../README.md for the field mapping and why this lives outside apps/.

## Rules for editing this file

**ASCII only.** No characters above U+007F. Use "-" not an em dash, and
straight quotes. This text is pasted into a third-party web form, so it
survives at least one encoding round-trip outside our control.

**Mind the character limits.** The submission form caps SUMMARY at 3000
characters and SHORT DESCRIPTION at 380.

**Markdown in the long fields only.** APP NAME is a short plain-text field;
markup there would appear literally. DETAILS, INSTALLATION and TROUBLESHOOTING
take Markdown. SUMMARY and SHORT DESCRIPTION are kept to plain prose.

Keep angle brackets inside fenced code blocks, where they are literal. Tag
search examples as ```spl; leave anything else untagged.

Last reviewed against app version 1.0.0.


===============================================================================
APP NAME  (plain text)
===============================================================================

MaximumPigs Easy Admin App

This exact string must also appear as [ui] label in default/app.conf and as
info.title in app.manifest. Splunkbase requires the listing name to correspond
to the label shown in the Splunk user interface.

It follows the required Splunkbase pattern:

    (Company | Brand | Author) [solution name] (App | Add-on | Connector)

"App" rather than "Add-on" because this ships views.

This is the display name, not the app ID. The ID and directory stay
"easyadmin".


===============================================================================
SUMMARY  (plain text, max 3000 characters)
===============================================================================

Form guidance: "Explain the purpose of the app and clearly indicate the problem
or situation the app addresses. Splunkbase displays this content as the Summary
tab in your app listing."

-------------------------------------------------------------------------------

Easy Admin is an administration page for Splunk Enterprise and Splunk Cloud
Platform that makes bulk changes to settings quick and visible. Its first page,
Index permissions, shows which indexes every role can search in a single table
and lets you change any number of them in one save.

The situation it addresses is a familiar one for anyone who administers roles.
Splunk's role editor works one role at a time. Finding out which roles can
search a given index means opening each role in turn, and granting a new index
to ten roles means ten separate edit-and-save round trips. Nothing shows the
whole picture, so access tends to be granted by copying whatever a similar role
has, and reviewed rarely.

Index permissions lays the whole picture out as a grid: one row per role, one
column per index, one checkbox per cell. Tick and untick as many cells as you
need, across as many roles as you need, and submit them together. The same grid
covers both the indexes a role is allowed to search and the indexes it searches
by default.

The grid is honest about what it shows. A tick means the index is listed on the
role itself. Where a role reaches an index some other way - through a role it
imports, or through a wildcard such as * - the cell is shaded and says why, so
an empty checkbox is never mistaken for no access. Wildcards and names that no
longer match an index appear as their own columns, so every entry on every role
can be seen and removed.

Saving is careful. Each role is read again immediately before it is written and
only the cells you changed are altered, so a change a colleague made since you
opened the page is not overwritten. Every role is reported individually, and
any that Splunk refuses stay marked as unsaved with the reason.

The app adds no privileges of its own. Every read and write is made as the user
who is logged in, so Splunk enforces that user's own capabilities exactly as it
does in Settings, and a user who cannot edit roles sees the page read-only.
Each change is written to a log on the search head, with the user, the role and
the indexes granted and revoked.

It runs on the search head only, collects no data, and needs no configuration.


===============================================================================
SHORT DESCRIPTION  (plain text, max 380 characters)
===============================================================================

Form guidance: "Provide a short overview of your app to display near the title
of the app listing and on the app card. If left empty, Splunkbase displays your
Summary instead." Must stand alone beside the title.

-------------------------------------------------------------------------------

An admin page that shows which indexes every role can search in one table, with
a checkbox for each role and index. Change as many as you need and save them
all at once. Runs with the logged-in user's own permissions.


===============================================================================
DETAILS  (Markdown)
===============================================================================

**Easy Admin** is an administration page for Splunk. Its first page, **Index
permissions**, shows which indexes every role can search in one table and lets
you change any number of them in one save.

### Using the page

Open **Easy Admin > Index permissions**. Each row is a role, each column is an
index, and each cell is a checkbox.

| Control | What it does |
| --- | --- |
| **Show** | Switches between *Searchable indexes* (`srchIndexesAllowed`) and *Indexes searched by default* (`srchIndexesDefault`). Unsaved changes on both are kept. |
| **Filter indexes** | Narrows the index columns to names containing the text. |
| **Add index or wildcard** | Adds a column for a name no role holds yet, such as a wildcard or an index that exists only on your indexers. |
| **Save N change(s)** | Submits every pending change in one request, after a confirmation. |
| **Discard changes** | Drops all pending changes. |
| **Reload** | Fetches the current state again. Pending changes are kept. |

### Reading a cell

- **Ticked** - the index is listed on the role itself. This is the only thing a
  save changes.
- **Shaded** - the role already reaches that index without listing it, through
  an imported role or a wildcard. Hover for the reason. Unticking cannot remove
  inherited access; change the role it comes from.
- **Outlined** - an unsaved change.

### Columns that are not indexes

| Badge | Meaning |
| --- | --- |
| `wildcard` | A pattern such as `*` or `_*`. As in Splunk itself, a pattern only matches internal indexes when it starts with an underscore. |
| `not on this search head` | A name that no index on this instance has. Common when indexes are defined only on the indexers, or after an index is deleted. |
| `added here` | A column you added yourself; it disappears on reload unless you save a tick in it. |

### How a save is applied

- **Changes are deltas.** Each role is re-read immediately before it is written
  and only the cells you changed are altered, so an edit made elsewhere since
  you loaded the page is not overwritten.
- **One write per role**, not per cell.
- **Not atomic across roles.** Splunk has no transaction spanning roles. Every
  role is attempted; any that Splunk refuses are listed with its reason and
  stay marked as unsaved, while the others are applied.
- **Effective immediately**, as with any role edit.
- A malformed request is rejected whole and changes nothing.

### Permissions and security

The app never elevates. Every read and write is made with the session of the
user who is logged in, so Splunk applies that user's own capabilities.

- Saving needs `edit_roles` or `edit_roles_grantable` (what `sc_admin` holds on
  Splunk Cloud Platform). Without either, the page is read-only.
- The app is visible to `admin` and `sc_admin` by default.
- Every role edit is logged with the user, the role and the indexes granted and
  revoked:

```spl
index=_internal source=*easyadmin.log
```

### Limitations

- Only `srchIndexesAllowed` and `srchIndexesDefault` are edited.
- The index list is what the search head knows. Where indexes are defined only
  on indexers, add columns by name.
- The grid uses its own light colour scheme in both light and dark themes.

### Compatibility

- Splunk Enterprise 9.3 or later, including 10.x, and Splunk Cloud Platform.
- Runs on Python 3.9 and Python 3.13.
- Search head only. No indexer or forwarder installation.
- Collects no data and opens no outbound network connections.


===============================================================================
INSTALLATION  (Markdown)
===============================================================================

Install the app on your search heads, using whichever method you normally use.
No indexer or forwarder installation is needed, and there is nothing to
configure afterwards.

### Verifying the install

Log in as an administrator and open **Easy Admin > Index permissions**. The
grid should list your roles down the side and your indexes across the top.

If the page reports that its endpoint was not found, restart Splunk once.

### Upgrading

Install the new version over the old one. There are no saved searches, lookups
or configuration to migrate.


===============================================================================
TROUBLESHOOTING  (Markdown)
===============================================================================

**The app is not in the Apps menu**

It is visible to the `admin` and `sc_admin` roles by default. To open it to
another role, change the app's read permission under Apps > Manage Apps.

**"The Easy Admin endpoint was not found"**

The app's REST endpoint is not registered yet. Restart Splunk once. On a search
head cluster, confirm the bundle reached every member.

**"Read-only: your account does not hold the edit_roles or
edit_roles_grantable capability"**

The page can be viewed but not saved. Ask an administrator for a role that can
edit roles.

**A role is listed as not updated after saving**

Splunk refused that role, and the message beside it is Splunk's own reason. The
usual cause is `edit_roles_grantable`, which limits a user to granting what
their own roles hold. The other roles in the same save were still applied.

**A cell is unticked but the role can still search the index**

The cell is shaded: access comes from an imported role or a wildcard, not from
an entry on the role itself. Hover over the cell to see which.

**An index is missing from the list**

The list is what the search head knows. If your indexes are defined only on the
indexers, type the name into "Add index or wildcard" to add its column.

**Getting more detail**

Errors and every role edit are written to
`$SPLUNK_HOME/var/log/splunk/easyadmin.log`, which is indexed into `_internal`.
