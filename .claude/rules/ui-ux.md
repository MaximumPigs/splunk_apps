---
paths:
  - "apps/**/appserver/**"
  - "apps/**/data/ui/**"
  - "tests/ui/**"
---

# Pages in Splunk Web

- Build to the `splunk-ux` standard: both themes, loading, empty and error
  states, labelled controls, keyboard use, British sentence-case wording.
- Every view gets the `splk ux` audit (last stage of `splk dev`). Give each
  view a `ready` selector and a `scope` (the app's root element) in
  `tests/ui/<app>/ux.toml`. A waiver needs a reason that is outside the app's
  control; never waive to get green.
- Open the screenshots in `build/reports/ux/<app>/` before saying a page
  looks right, then run `splunk-ux-review`. Ask the person only for
  judgement the standard does not settle, with the screenshots attached.
- Bump `[install] build` in `app.conf` for **every deploy** that changes
  `appserver/static/` after the current build was served, not once per
  release: Splunk Web serves cached files for a build number it has seen.
- A new or renamed view needs its `ux.toml` section updated: a section for a
  view that no longer exists fails the audit on purpose.
