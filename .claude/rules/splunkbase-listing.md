---
paths:
  - "splunkbase/**"
  - "apps/**/app.manifest"
  - "apps/**/default/app.conf"
---

# Splunkbase naming and listing copy

- Display name pattern (dev.splunk.com, enforced by Splunkbase):
  `[DEPRECATED|ARCHIVED] (Company | Brand | Author) [solution] (App | Add-on | Connector) [for 3rd-party technology]`.
  Start with the author brand `MaximumPigs`; "Add-on" when the app ships no
  views; the `for <technology>` suffix only when it interoperates with a
  third-party product. Example: `MaximumPigs fillcontinuous Add-on`.
- The app **id** and directory are not constrained by this: keep them short and
  lowercase.
- The same name lives in three places that must match exactly: `app.conf [ui] label`,
  `app.manifest info.title`, and the listing's APP NAME. Change all three in one commit.
- `splunkbase/<app>/listing.md` stays **outside `apps/`** so it can never be
  packaged into a `.spl`. Do not move it.
- Listing files are **ASCII only** (nothing above U+007F, so no em dashes or
  smart quotes): the text is pasted into a third-party form. The edit hook
  enforces this.
- Markdown only in DETAILS, INSTALLATION, TROUBLESHOOTING; APP NAME, SUMMARY and
  SHORT DESCRIPTION are plain text. Tag SPL examples as ```` ```spl ````.
- Field limits are the reverse of what the names suggest: **Summary 3000**
  characters (own tab, explains the problem); **Short description 380**
  (beside the title and on the app card, must stand alone). Splunkbase's own
  guidance for each field sits above a dashed rule in the listing: keep it.
- Compatible Splunk versions go on the submission form as well as in the text;
  the form gates installs. Current floor: **Splunk 9.3**.
- No claim in a listing that has not been observed on a live instance. Settle
  it with `splk search` first.
- AppInspect has no icon or screenshot checks; an icon helps but is optional.
