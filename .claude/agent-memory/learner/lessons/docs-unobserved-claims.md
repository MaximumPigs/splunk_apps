---
hits: 3
seen: [2026-09]
area: docs
level: rule
---
**Symptom:** Three published claims were wrong: `makecontinuous` "rejects
duplicate `_time` values" (in four files), the listing's "false drops to zero"
on charts, and "Splunk 9.x compatible".

**Cause:** Each was asserted from a forum post, intuition or wording, never
observed. Live, `makecontinuous` silently returns an incomplete result; gap vs
zero rendering is decided by the panel's null handling, not the data; 9.0 to
9.2 run Python 3.7, which nothing had run.

**Fix:** Corrected the text; narrowed compatibility to Splunk 9.3+.

**Catch earlier:** Promoted to `CLAUDE.md` ("never assert behaviour you have
not observed") and `write-live-test`. Settle claims with `splk search` first.
