---
hits: 2
seen: [2026-11-12, 2026-11-14]
area: conf
level: rule
---
**Symptom:** easyadmin, twice.
- 2026-11-12: after changing `appserver/static/*.js` and `*.css`, a green
  `splk dev` deployed the new package, but Splunk Web still served the old
  page, even after a browser hard refresh. No `splk` stage failed; the person
  found it while checking the page by hand.
- 2026-11-14 (1.1.0): `[install] build` was bumped to 8 once for the release.
  Build 8 was deployed and served, then `easyadmin_roles.js` changed again and
  was redeployed as build 8. The UI stage failed at 17:07:
  `test_easyadmin_edit_ui::test_imported_value_is_shown_under_a_setting:
  assert 'comma-separated' not in 'Each field ...'` (the old legend text).
  Bumping to 9 and redeploying turned it green at 17:09.

**Cause:** Splunk Web caches an app's `appserver/static` files on its own
side, keyed on `[install] build` in `default/app.conf`. Once a build number
has been served, any later package with the same number serves the cached
files. The bump is per deploy that changes static files, not per release or
per PR. A hard refresh does not help and `[launcher]` version does not matter.
Applies to every app that ships dashboard JS/CSS or custom page assets.

**Fix:** raised `build` (1 to 2, later 8 to 9) in
`apps/easyadmin/default/app.conf` and redeployed; no restart needed.
`/<locale>/_bump` in Splunk Web as an admin also clears the cache.

**Catch earlier:** promoted to `.claude/rules/ui-ux.md` and
`.claude/skills/dev-loop/SKILL.md` ("Reading failures": stale code).
Candidate check (not built): `splk deploy` records the build number and a hash
of `appserver/static/` per app in `.agent/`, and fails when the hash changed
but the build number did not.

**Pattern:** the working recipe is in playbook `custom-page-classic-js`.
