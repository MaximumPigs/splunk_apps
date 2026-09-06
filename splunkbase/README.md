# Splunkbase listing copy

One directory per app, holding the text used on its Splunkbase listing page.
Kept in version control so the published description can be reviewed, diffed and
corrected like everything else — a listing that drifts from the app is its own
kind of bug.

```
splunkbase/<app>/listing.md      the five Splunkbase form fields
```

Each `listing.md` is divided by banner headers matching the fields on the
Splunkbase upload form, so each section copies straight across:

| Section | Splunkbase field |
| --- | --- |
| SUMMARY | Summary |
| SHORT DESCRIPTION | Short Description |
| DETAILS | Details |
| INSTALLATION | Installation |
| TROUBLESHOOTING | Troubleshooting |

Plain text rather than Markdown: Splunkbase renders these fields
inconsistently, and text with spaced headings survives either way.

## ASCII only

Listing files must contain no characters above U+007F. Use `-` rather than an
em dash, and straight quotes.

This is not fussiness. The text is pasted into a third-party web form, so it
survives at least one encoding round-trip outside our control. The first
version of the `fillcontinuous` listing was written through a PowerShell
pipeline that read UTF-8 as CP1252, and every em dash arrived as `a-hat, euro,
right-quote` - eight of them - plus a byte-order mark at the start of the file.

To check a file before committing it:

```bash
python -c "import sys;d=open(sys.argv[1],'rb').read();bad=[(i,b) for i,b in enumerate(d) if b>127];print('non-ASCII bytes:',bad[:10] or 'none');print('BOM:',d[:3]==b'\xef\xbb\xbf')" splunkbase/<app>/listing.md
```

Write these files with an editor or a tool that does UTF-8 properly. Windows
PowerShell 5.1 is a poor choice for both halves of the job: `-Encoding utf8`
always emits a BOM, and `Get-Content` defaults to the system ANSI codepage.

## This never ships inside an app

The directory sits at the repository root, outside `apps/`, on purpose.
`scripts/package_app.py` walks `apps/<app>/` and nothing else, so listing copy
cannot end up inside a `.spl` however the packager changes. Do not move this
under an app directory to keep it "closer" to the code — that trades a
structural guarantee for a rule someone has to remember.

## Keeping it honest

When app behaviour changes, update the listing in the same pull request. The
`Details` and `Troubleshooting` sections quote real error messages and describe
observed behaviour, so they go stale the moment either changes.

Claims about what other Splunk commands do belong here only if they have been
tested against a real instance. An earlier version of the `fillcontinuous`
listing repeated a forum post's claim that `makecontinuous` errors on duplicate
`_time` values; it does not — it silently returns an incomplete result, which is
both worse and a better argument for the app.
