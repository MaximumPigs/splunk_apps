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
