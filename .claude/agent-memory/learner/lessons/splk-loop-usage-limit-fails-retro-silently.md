---
hits: 1
seen: [2026-11-18]
area: splk
level: lesson
---
**Symptom:** easyadmin run log, 21:57 to 00:12: six `FAIL easyadmin loop-retro
You've hit your 5-hour limit ... resets 1:10am (Australia/Sydney)` entries
(`rate_limit`), one `loop-notify` ("retrying every 20 min"). The PR work was
already green; only the retro step could not run, so lessons for the change
waited about three hours.
**Cause:** the retro runs last, after the dev stages and reviews have spent
the model quota. A usage limit is not a failure of the change, but it is
logged as `FAIL`, which the Stop hook and a reader treat like a red stage.
**Fix:** none yet (candidate): log a rate limit as a distinct status (waiting,
not FAIL) with the reset time once, not once per retry; or run the retro
before the long review steps.
**Catch earlier:** a unit test for the loop's rate-limit branch that asserts
one notify and no FAIL per retry. Related:
`splk-loop-step-ok-exit-empty-output-logs-fail.md` (misleading loop log lines).
