# Lesson index

One line per lesson, most hits first. Details in `lessons/`. Maintained by the
`learner` agent through the `retro` skill; reviewed in PRs. Lessons dated
2026-09 were imported from the owner's handoff notes on `fillcontinuous`.

Lessons record what went wrong. What works (recipes for pages, REST
endpoints, themes, roles, search commands) lives in the `splunk-playbook`
skill. `level: pattern` means the lesson's fix now lives in a playbook
pattern; the lesson stays as the evidence and keeps counting hits.

| Hits | Level | Lesson |
| --- | --- | --- |
| 4 | rule | [Unobserved claims shipped wrong](lessons/docs-unobserved-claims.md): makecontinuous, "drops to zero", "9.x compatible", easyadmin dark mode. Check with `splk search`, or `splk shot` / UI tests for UI, before writing it. |
| 1 | rule | [AppInspect must run untagged](lessons/appinspect-full-check-set.md): a cloud-only run missed `check_for_updates_disabled`; Splunkbase rejected the package. |
| 1 | lesson | [relpath fails across Windows drives](lessons/splk-windows-cross-drive-relpath.md): repo on D:, temp on C:; use `splk.paths.display()` for display paths. |
| 1 | pattern | [Persist REST handlers keep old code after deploy](lessons/splunkd-persist-handler-stale-code.md): `scripttype=persist` ignores reinstall/_reload; restart or wait. Playbook `rest-endpoint-behind-page`. |
| 1 | pattern | [simpleRequest postargs must be a dict](lessons/python-simplerequest-postargs-dict.md): list of pairs fails on `.items()`; use `{k: [v1, v2]}`, `""` clears. Playbook `rest-endpoint-behind-page`. |
| 1 | pattern | [Splunk Web caches static files by app build](lessons/conf-app-build-static-cache.md): bump `[install] build` with any `appserver/static` change, or the old JS/CSS is served. Playbook `custom-page-classic-js`. |
| 1 | pattern | [splunkd JSON numbers vs `\| rest` strings](lessons/splunkd-json-numbers-vs-rest-search.md): REST JSON gives quotas as numbers; `\| rest` gives strings. Normalise at the boundary. Playbook `splunkd-roles-rest-api`. |
| 1 | pattern | [splunkd hides imported capabilities from a role's own list](lessons/splunkd-role-capabilities-reporting.md): new roles start with 5; compare `capabilities` + `imported_capabilities`. Playbook `splunkd-roles-rest-api`. |
| 1 | pattern | [Classic dashboards ignore the user's theme](lessons/splunkweb-classic-dashboard-theme.md): `supported_themes` is not enough; reload with `?theme=<user-prefs theme>`, loop-guarded. Recipe: playbook `follow-user-theme`. |
| 1 | pattern | [splunkd sorts role index lists](lessons/splunkd-role-index-lists-sorted.md): compare `srchIndexes*` as sets in live tests. Playbook `splunkd-roles-rest-api`. |
| 1 | rule | [Messages use str.format](lessons/search-command-message-format.md): a `%` stub hid a literal `%d` shown to users. |
| 1 | rule | [transform() runs per chunk](lessons/search-command-chunking.md): buffer until `_finished`; test with tens of thousands of rows. |
| 1 | rule | [First record fixes a chunk's columns](lessons/search-command-first-record-fields.md): register field names before yielding; test heterogeneous rows. |
| 1 | rule | [Bound search-command resources](lessons/search-command-resource-limits.md): output products, capped validators, `math.isfinite`. |
| 1 | rule | [sc_admin beside admin](lessons/appinspect-sc-admin.md): `check_kos_are_accessible` on Cloud. |
| 1 | rule | [AppInspect actions take app_path oppositely](lessons/ci-appinspect-action-paths.md): CLI wants a file, API a directory. |
| 1 | rule | [SDK metadata overstated its Python floor](lessons/vendoring-sdk-python-metadata.md): vendor without `ai/`. |
| 1 | hook | [AI commit author became a co-author trailer](lessons/git-ai-commit-author.md): squash merge credits every commit author; the bash guard checks the author. |
| 1 | hook | [PowerShell corrupted UTF-8](lessons/windows-powershell-encoding.md): never write repo files with PowerShell. |
| 1 | lesson | [Stale secret, not rate limit](lessons/process-stale-secret-misdiagnosis.md): check mechanical causes and timestamps first. |
