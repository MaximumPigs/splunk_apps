---
hits: 4
seen: [2026-09, 2026-11-13]
area: docs
level: rule
---
**Symptom:** Three published claims were wrong: `makecontinuous` "rejects
duplicate `_time` values" (in four files), the listing's "false drops to zero"
on charts, and "Splunk 9.x compatible".

2026-11-13: easyadmin's README and Splunkbase listing said the app "follows
the light or dark theme chosen in your Splunk account preferences" after only
adding `supported_themes` to `app.conf`. The owner found it still light, after
a restart too.

**Cause:** Each was asserted from a forum post, intuition or wording, never
observed. Live, `makecontinuous` silently returns an incomplete result; gap vs
zero rendering is decided by the panel's null handling, not the data; 9.0 to
9.2 run Python 3.7, which nothing had run.

**Fix:** Corrected the text; narrowed compatibility to Splunk 9.3+. The
theme claim was rewritten once the `?theme=` reload was confirmed working by
the owner in a browser.

**Catch earlier:** Promoted to `CLAUDE.md` ("never assert behaviour you have
not observed") and `write-live-test`. Settle claims with `splk search` first.
The rule held for SPL but not for UI behaviour, which `splk` could not
observe then. It can now: playbook pattern `verify-in-browser` (`splk shot`,
`tests/ui/`). Write UI docs only after a screenshot or UI test shows it working.
