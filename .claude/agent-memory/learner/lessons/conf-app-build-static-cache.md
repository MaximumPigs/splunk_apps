---
hits: 1
seen: [2026-11-12]
area: conf
level: pattern
---
**Symptom:** easyadmin: after changing `appserver/static/*.js` and `*.css`, a
green `splk dev` deployed the new package, but Splunk Web still served the old
page, even after a browser hard refresh. No `splk` stage failed; the person
found it while checking the page by hand.

**Cause:** Splunk Web caches an app's `appserver/static` files on its own
side, keyed on `[install] build` in `default/app.conf`. Reinstalling the app
with the same `build` serves the old cached files. A browser hard refresh
does not help, and a matching `[launcher]` version does not affect it. This
applies to every app that ships static files: dashboard JS and CSS, and
custom page assets.

**Fix:** raised `build` from 1 to 2 in `apps/easyadmin/default/app.conf`, with
a comment saying why, and redeployed. Ctrl+F5 then loaded the new page; no
restart was needed. Visiting `/<locale>/_bump` in Splunk Web as an admin also
clears the cache without a restart.

**Catch earlier:** increment `[install] build` in the same change as any edit
under `appserver/static/`. Candidate check: `splk build` warns when files under
`appserver/static/` changed against `main` and `build` did not.

**Pattern:** the working recipe is in playbook `custom-page-classic-js`.
