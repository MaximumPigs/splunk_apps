---
hits: 1
seen: [2026-09]
area: process
level: lesson
---
**Symptom:** AppInspect API job failed; a rate-limit theory was asserted.

**Cause:** A stale stored secret. The tell (job started before the secret was
saved) was already in hand and under-weighted.

**Fix:** Re-saved the secret; re-ran.

**Catch earlier:** Check mechanical causes and timestamps before theorising;
say how confident a diagnosis is, and own it explicitly when wrong. Noted in
`CLAUDE.md` and `.claude/rules/ci-and-release.md`.
