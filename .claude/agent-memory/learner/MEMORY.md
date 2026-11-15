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
| 4 | rule | [Persist REST handlers keep old code after deploy](lessons/splunkd-persist-handler-stale-code.md): requests reset the idle timer; never poll, wait ~7 min idle, run once. `dev-loop`. |
| 3 | rule | [Heredoc Python edits broke](lessons/process-heredoc-python-edits.md): escapes and quoting; scratch file + `python <file>`. Rule `windows-environment`. |
| 2 | rule | [Splunk Web caches static files by app build](lessons/conf-app-build-static-cache.md): bump `[install] build` per deploy that changes `appserver/static`. Rule `ui-ux`. |
| 2 | rule | [Evidence before theory](lessons/process-evidence-before-theory.md): stale secret, assumed role-editor modal; open the FAILED.png/log/timestamps first. |
| 2 | rule | [UI `has_text` is a substring match](lessons/splk-ui-has-text-is-substring.md): "default", "pass4SymmKey" matched too much; `:text-is()` on the name. Rule `ui-ux`. |
| 1 | pattern | [Links are not enough: check acl.removable](lessons/splunkd-links-not-enough-check-acl-removable.md): default saved searches keep move links; owner hit the refusal. |
| 1 | lesson | [Asserted an unseen REST key](lessons/tests-assert-only-observed-rest-keys.md): guessed `iseval`; assert only keys seen in a real response. |
| 1 | pattern | [Namespace GET returns any visible object](lessons/splunkd-namespace-get-returns-visible-objects.md): check `acl.app` before acting (`get_in_app`). Playbook `splunkd-knowledge-objects-rest`. |
| 1 | pattern | [Props and tags cannot be copied by REST](lessons/splunkd-props-tags-copy-unreliable.md): merged views, 409s, writes that never land. |
| 1 | lesson | [Shell cannot read Splunk etc/](lessons/splk-shell-cannot-read-splunk-etc.md): "permission denied" proves nothing; read through splunkd. |
| 1 | pattern | [One persist handler class per script](lessons/splunkd-persist-one-handler-class-per-script.md): a second subclass, even imported, 500s every endpoint in it. Playbook `rest-endpoint-behind-page`. |
| 1 | skill | [Token auth lags a restart](lessons/splk-token-auth-lags-restart.md): 401 for ~30 s after `--restart`; rerun `splk doctor`. `dev-loop`. |
| 2 | pattern | [Creating/deleting apps needs a restart](lessons/splunkd-app-create-delete-needs-restart.md): live tests move objects between `search` and `launcher`. Playbook `splunkd-knowledge-objects-rest`. |
| 1 | pattern | [Filter hid the drop target](lessons/ux-filter-hides-drop-target.md): filters narrow items, never target containers. Playbook `custom-page-classic-js`. |
| 1 | skill | [Untested panel control shipped a Major](lessons/ux-every-control-needs-a-ui-test.md): every control gets its own UI test. `write-ui-test`. |
| 1 | lesson | [etc/system/default lacks some confs](lessons/conf-system-default-not-every-file.md): no `macros.conf` on 10.6.1; any precedence layer can be absent. |
| 1 | lesson | [`splk shot` cannot open a #hash](lessons/splk-shot-hash-url.md): `#` quoted to `%23`; use a UI test. Candidate `--hash` option. |
| 1 | pattern | [Label changed, styling did not](lessons/ux-label-meaning-needs-matching-style.md): two UX Majors; change badges/strikethrough with words. Playbook `custom-page-classic-js`. |
| 1 | pattern | [Secret-name regex unanchored](lessons/security-secret-name-match-anchored.md): over- and under-masked; suffix `\Z` + exact names. Playbook `conf-precedence-from-files`. |
| 1 | rule | [AppInspect must run untagged](lessons/appinspect-full-check-set.md): a cloud-only run missed `check_for_updates_disabled`; Splunkbase rejected the package. |
| 1 | skill | [UI test raced a save's re-render](lessons/splk-ui-test-wait-for-busy-not-message.md): wait for the busy indicator to detach, not the message. `write-ui-test`. |
| 1 | skill | [Tri-state checkbox ignored uncheck()](lessons/splk-ui-tristate-checkbox-click.md): indeterminate is unchecked; use `click()`. `write-ui-test`. |
| 1 | skill | [Second SplunkWeb in a UI test](lessons/splk-ui-one-playwright-per-session.md): Playwright sync refuses; use `web.new_user_page(user, pw)`. `write-ui-test`. |
| 1 | lesson | [relpath fails across Windows drives](lessons/splk-windows-cross-drive-relpath.md): repo on D:, temp on C:; use `splk.paths.display()` for display paths. |
| 1 | pattern | [simpleRequest postargs must be a dict](lessons/python-simplerequest-postargs-dict.md): list of pairs fails on `.items()`; use `{k: [v1, v2]}`, `""` clears. Playbook `rest-endpoint-behind-page`. |
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
| 1 | lesson | [Branch tracking main pushed by editor Sync](lessons/git-branch-tracking-main-editor-push.md): use `checkout --no-track`; ruleset is the real guard. Candidate rule. |
| 1 | lesson | [Unattended agent escape routes](lessons/security-unattended-agent-escape-routes.md): spelling variants, inherited env, own comments read as owner. Test variants. |
| 2 | lesson | [Skill `!` preamble needs allowlist](lessons/splk-skill-preamble-needs-allowlist.md): cannot prompt; reload after permission change. |
| 1 | pattern | [Probe guards before designing on them](lessons/process-probe-guards-before-designing-on-them.md): `.agent/` write denied. Playbook `observe-tool-behaviour-first`. |
| 1 | lesson | [PowerShell mangled JSON argument](lessons/windows-powershell-json-arguments.md): spawn from Python with an arg list. |
| 1 | pattern | [Narrowing a guard regex reopened bypasses](lessons/security-guard-regex-narrowing-reopens-bypasses.md): `+main`, quotes, `bash -c`, `~0` slipped; test the deny corpus first, boundaries = what a ref cannot contain. Playbook `probe-a-hook-with-decide`. |
| 1 | hook | [AI commit author became a co-author trailer](lessons/git-ai-commit-author.md): squash merge credits every commit author; the bash guard checks the author. |
| 1 | hook | [PowerShell corrupted UTF-8](lessons/windows-powershell-encoding.md): never write repo files with PowerShell. |
