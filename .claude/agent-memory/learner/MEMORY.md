# Lesson index

One line per lesson, most hits first. Details in `lessons/`. Maintained by the
`learner` agent through the `retro` skill; reviewed in PRs. Lessons dated
2026-09 were imported from the owner's handoff notes on `fillcontinuous`.

| Hits | Level | Lesson |
| --- | --- | --- |
| 3 | rule | [Unobserved claims shipped wrong](lessons/docs-unobserved-claims.md): makecontinuous, "drops to zero", "9.x compatible". Check with `splk search` before writing it. |
| 1 | rule | [AppInspect must run untagged](lessons/appinspect-full-check-set.md): a cloud-only run missed `check_for_updates_disabled`; Splunkbase rejected the package. |
| 1 | rule | [Messages use str.format](lessons/search-command-message-format.md): a `%` stub hid a literal `%d` shown to users. |
| 1 | rule | [transform() runs per chunk](lessons/search-command-chunking.md): buffer until `_finished`; test with tens of thousands of rows. |
| 1 | rule | [First record fixes a chunk's columns](lessons/search-command-first-record-fields.md): register field names before yielding; test heterogeneous rows. |
| 1 | rule | [Bound search-command resources](lessons/search-command-resource-limits.md): output products, capped validators, `math.isfinite`. |
| 1 | rule | [sc_admin beside admin](lessons/appinspect-sc-admin.md): `check_kos_are_accessible` on Cloud. |
| 1 | rule | [AppInspect actions take app_path oppositely](lessons/ci-appinspect-action-paths.md): CLI wants a file, API a directory. |
| 1 | rule | [SDK metadata overstated its Python floor](lessons/vendoring-sdk-python-metadata.md): vendor without `ai/`. |
| 1 | hook | [AI commit author became a co-author trailer](lessons/git-ai-commit-author.md): squash merge credits every commit author; the bash guard checks the author. |
| 1 | hook | [PowerShell corrupted UTF-8](lessons/windows-powershell-encoding.md): never write repo files with PowerShell. |
| 1 | lesson | [relpath fails across Windows drives](lessons/splk-windows-cross-drive-relpath.md): repo on D:, temp on C:; use `splk.paths.display()`. |
| 1 | lesson | [Stale secret, not rate limit](lessons/process-stale-secret-misdiagnosis.md): check mechanical causes and timestamps first. |
