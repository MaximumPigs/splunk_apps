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
Platform that makes bulk changes to settings quick and visible. Its Role
management page shows the configuration of every role in one place, split into
tabs, and lets you change any number of settings in a single save.

The situation it addresses is a familiar one for anyone who administers roles.
Splunk's role editor works one role at a time. Finding out which roles can
search a given index, or which roles hold a given capability, means opening
each role in turn, and granting a new index to ten roles means ten separate
edit-and-save round trips. Nothing shows the whole picture, so access tends to
be granted by copying whatever a similar role has, and reviewed rarely.

Role management lays the whole picture out as grids, with the roles down the
side. The Indexes tab has a checkbox for every index, covering the indexes a
role can search, searches by default, can never search and can delete from.
The Capabilities tab has a checkbox for every capability Splunk defines. The
Inheritance tab shows which roles each role imports and which it can grant.
Two further tabs hold every other role setting - search quotas, time windows,
search filter, default app, federated providers and KV store deny lists - as
editable fields. Change as many cells as you need, on as many tabs as you
need, and submit them together.

The grids are honest about what they show. A tick means the item is listed on
the role itself. Where a role has an item some other way - through a role it
imports, through a chain of imported roles, or through an index wildcard such
as * - the cell is shaded and says why, so an empty checkbox is never mistaken
for no access. Entries that do not match a known index, capability or role
appear as their own columns, so every entry on every role can be seen and
removed.

Saving is careful. Each role is read again immediately before it is written.
Checkbox changes alter only the items you changed, so an item a colleague added
since you opened the page is kept, and a setting is written only if it still
has the value you started from. Every role is reported individually, and any
that Splunk refuses stay marked as unsaved with the reason.

The app adds no privileges of its own. Every read and write is made as the user
who is logged in, so Splunk enforces that user's own capabilities exactly as it
does in Settings, and a user who cannot edit roles sees the page read-only.
Each change is written to a log on the search head, with the user, the role and
the settings written.

It runs on the search head only, collects no data, and needs no configuration.


===============================================================================
SHORT DESCRIPTION  (plain text, max 380 characters)
===============================================================================

Form guidance: "Provide a short overview of your app to display near the title
of the app listing and on the app card. If left empty, Splunkbase displays your
Summary instead." Must stand alone beside the title.

-------------------------------------------------------------------------------

Manage every Splunk role from one page. Tabs show all roles against every
index, capability and inherited role as checkboxes, and every other role
setting as editable fields. Change as many as you need and save them all at
once. Runs with the logged-in user's own permissions.


===============================================================================
DETAILS  (Markdown)
===============================================================================

**Easy Admin** is an administration page for Splunk. Its **Role management**
page shows every role's configuration in one place, split into tabs, and lets
you change any number of settings in one save.

### The tabs

Every tab lists the roles down the side.

| Tab | Shows |
| --- | --- |
| **Indexes** | A checkbox per index for `srchIndexesAllowed`, `srchIndexesDefault`, `srchIndexesDisallowed` and `deleteIndexesAllowed`. |
| **Capabilities** | A checkbox per capability Splunk defines. |
| **Inheritance** | A checkbox per role for `imported_roles` and `grantable_roles`. |
| **Search limits** | Fields for the search quotas, `srchTimeWin`, `srchTimeEarliest`, `srchMinScheduleInterval`, `srchAllowAdvancedCron`, `srchFilter` and `defaultApp`. |
| **Federated and KV store** | Fields for the federated provider lists, `fieldFilterExemption` and the KV store deny lists. |

Each column shows the `authorize.conf` attribute name beside its label. A tab
with unsaved changes shows how many on its label.

### Using the page

Open **Easy Admin > Role management**.

| Control | What it does |
| --- | --- |
| **Show** | On a tab with several attributes, switches between them. Unsaved changes on all of them are kept. |
| **Filter** | Narrows the columns (checkbox tabs) or the roles (settings tabs) to names containing the text. |
| **Add a column by name** | Adds a column for a name no role holds yet, such as an index wildcard or an index that exists only on your indexers. |
| **Save N change(s)** | Submits every pending change, on every tab, in one request, after a confirmation. |
| **Discard changes** | Drops all pending changes. |
| **Reload** | Fetches the current state again. Pending changes are kept. |

The app follows the light or dark theme chosen in your Splunk account
preferences.

The confirmation warns you when a save changes a role you hold yourself.

### Reading a checkbox

- **Ticked** - the item is listed on the role itself. This is the only thing a
  save changes.
- **Shaded** - the role already has the item without listing it, through an
  imported role, a chain of imported roles, or an index wildcard. Hover for the
  reason. Unticking cannot remove inherited access; change the role it comes
  from.
- **Outlined** - an unsaved change.

### Columns that are not known items

| Badge | Meaning |
| --- | --- |
| `wildcard` | An index pattern such as `*` or `_*`. As in Splunk itself, a pattern only matches internal indexes when it starts with an underscore. |
| `not known here` | A name with no matching index, capability or role on this instance. Common when indexes are defined only on the indexers, or after something is deleted. |
| `added here` | A column you added yourself; it disappears on reload unless you save a tick in it. |

### How a save is applied

- **Checkbox changes are deltas.** Each role is re-read immediately before it
  is written and only the items you changed are altered.
- **Settings are checked first.** A setting is written only if the role still
  has the value the page loaded; otherwise nothing on that role is written and
  the page says which setting changed.
- **One write per role**, however many tabs the changes were on.
- **Not atomic across roles.** Every role is attempted; any that Splunk refuses
  are listed with its reason and stay marked as unsaved.
- **Effective immediately**, as with any role edit.
- A malformed request is rejected whole and changes nothing.

### Permissions and security

The app never elevates. Every read and write is made with the session of the
user who is logged in, so Splunk applies that user's own capabilities.

- Saving needs `edit_roles` or `edit_roles_grantable` (what `sc_admin` holds on
  Splunk Cloud Platform). Without either, the page is read-only.
- The app is visible to `admin` and `sc_admin` by default.
- Every role edit is logged with the user, the role and the settings written:

```spl
index=_internal source=*easyadmin.log
```

### Limitations

- The index list is what the search head knows. Where indexes are defined only
  on indexers, add columns by name.
- Roles cannot be created or deleted here.

### Compatibility

- Splunk Enterprise 9.3 or later, including 10.x, and Splunk Cloud Platform.
  Tested on Splunk Enterprise 10.6.1; some role attributes, such as the KV
  store deny lists, may not exist on older versions.
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

Log in as an administrator and open **Easy Admin > Role management**. Each tab
should list your roles down the side.

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

**"Changed elsewhere since the page loaded"**

Someone changed that setting on the role after you opened the page. Nothing on
that role was written. Reload, check the new value, and make your change again.

**A cell is unticked but the role still has the item**

The cell is shaded: the item comes from an imported role or an index wildcard,
not from an entry on the role itself. Hover over the cell to see which.

**A capability shows as shaded rather than ticked**

Splunk reports a capability a role also gets from an imported role under the
imported role only. The role has the capability either way.

**An index is missing from the list**

The list is what the search head knows. If your indexes are defined only on the
indexers, type the name into "Add a column by name" to add its column.

**Getting more detail**

Errors and every role edit are written to
`$SPLUNK_HOME/var/log/splunk/easyadmin.log`, which is indexed into `_internal`.
