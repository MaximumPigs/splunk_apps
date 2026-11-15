---
hits: 1
seen: [2026-11-16]
area: conf
level: test
---
**Symptom:** easyadmin 1.6.2, `splk dev` inspect stage red at 07:49:33:
`check_version_is_valid_semver: 1.6.2 specified in version in the [id] stanza
of default\app.conf does not match other versions specified in the app.`
The agent had bumped `app.conf` but not `app.manifest`; the unit stage was
green, so the mismatch only showed after the build.
**Cause:** the version lives in three places (`[launcher]`, `[id]`,
`app.manifest info.id.version`) and the rule in `conf-files.md` was a prose
reminder only. Applies to every app.
**Fix:** `app.manifest` set to 1.6.2; inspect green at 07:50:14.
**Catch earlier:** `tests/test_app_versions.py` (new, parametrised over every
app, passes today) fails in the unit stage when any of the three differ.
