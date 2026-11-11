---
hits: 1
seen: [2026-11-11]
area: splk
level: lesson
---
**Symptom:** `splk dev fillcontinuous` went red in the unit stage on Windows:
`tests.test_splk_core::test_build_uses_repo_packager: ValueError: path is on
mount 'C:', start on mount 'D:'`.

**Cause:** `os.path.relpath(package, REPO_ROOT)` raises on Windows when the two
paths are on different drives. pytest's `tmp_path` was on C:, the repo on D:.
Linux CI cannot hit this.

**Fix:** `splk.paths.display()` falls back to the absolute path; regression
test `test_build_outside_repo_drive` simulates the cross-drive error.

**Catch earlier:** any `relpath` used only for display goes through
`paths.display()`. The developer runs Windows with the repo on D:, so treat
drive letters as real.
