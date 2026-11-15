---
hits: 1
seen: [2026-11-15]
area: splk
level: lesson
---
**Symptom:** fillcontinuous loop item: the implement step left ROADMAP.md with duplicated sections; the review step found it and restored the file from main with only the Done row added (step record 20261115-213301-review).
**Cause:** ROADMAP.md was edited more than once in a step (item status plus Done table) without re-reading the result; the damage is invisible to `splk dev`, which does not check it.
**Fix:** review restored `main`'s ROADMAP.md and re-applied one Done row.
**Catch earlier:** after editing ROADMAP.md run `git diff --stat main -- ROADMAP.md` and read the diff: it should only touch the item's status and the Done table. Make one small Edit per change, never a rewrite.
