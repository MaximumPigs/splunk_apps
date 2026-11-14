---
hits: 1
seen: [2026-11-15]
area: process
level: lesson
---
**Symptom:** `splk loop` hand-off files were designed under `.agent/`
without reading `guard_files.py`. A cheap headless Haiku probe showed the
Write denied before anything depended on it.
**Cause:** Designing on an unchecked assumption about what the guard allows.
**Fix:** A narrow `.agent/loop/handoff/` exception; supervisor inputs live in
the protected `inbox/`.
**Catch earlier:** Before building on a permission or guard, run a one-line
probe under the real environment (or read the guard source). Cost: seconds.
Same family as [[docs-unobserved-claims]].
