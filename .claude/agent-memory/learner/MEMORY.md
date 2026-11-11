# Lesson index

One line per lesson, most hits first. Details in `lessons/`. Maintained by the
`learner` agent through the `retro` skill; reviewed in PRs.

| Hits | Level | Lesson |
| --- | --- | --- |
| 1 | rule | [AppInspect must run untagged](lessons/appinspect-full-check-set.md): a cloud-only run missed `check_for_updates_disabled`; Splunkbase rejected the package. |
| 1 | lesson | [relpath fails across Windows drives](lessons/splk-windows-cross-drive-relpath.md): repo on D:, temp on C:; use `splk.paths.display()` for display paths. |
| 1 | lesson | [Persist REST handlers keep old code after deploy](lessons/splk-persist-handler-stale-code.md): `scripttype=persist` ignores reinstall/_reload; restart or wait. |
| 1 | lesson | [simpleRequest postargs must be a dict](lessons/python-simplerequest-postargs-dict.md): list of pairs fails on `.items()`; use `{k: [v1, v2]}`, `""` clears. |
| 1 | lesson | [splunkd sorts role index lists](lessons/splunkd-role-index-lists-sorted.md): compare `srchIndexes*` as sets in live tests. |
