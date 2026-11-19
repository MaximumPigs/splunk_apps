---
hits: 2
seen: [2026-11-18, 2026-11-19]
area: splk
level: lesson
---
**Symptom:** easyadmin run log, 21:57 to 00:12: six `FAIL easyadmin loop-retro
You've hit your 5-hour limit ... resets 1:10am (Australia/Sydney)` entries
(`rate_limit`), one `loop-notify` ("retrying every 20 min"). The PR work was
already green; only the retro step could not run, so lessons for the change
waited about three hours.
**Second hit (2026-11-19):** easyadmin 1.8.0, seven `FAIL loop-review`
(`You've hit your 5-hour limit ... resets 11:30am`, `rate_limit`, sonnet) from
07:54 to 11:10, one `loop-notify`. The review step, not the retro, hit it, so
the cause is any long model step after the dev stages, and the stall was about
4.5 hours. Review then passed at 12:26 with no code problem. Promote: make
`loop.py` log the limit once as waiting (with the reset time) and not as FAIL;
until then, read these FAILs as a pause, not a red stage.
**Cause:** the retro runs last, after the dev stages and reviews have spent
the model quota. A usage limit is not a failure of the change, but it is
logged as `FAIL`, which the Stop hook and a reader treat like a red stage.
**Fix:** none yet (candidate): log a rate limit as a distinct status (waiting,
not FAIL) with the reset time once, not once per retry; or run the retro
before the long review steps.
**Catch earlier:** a unit test for the loop's rate-limit branch that asserts
one notify and no FAIL per retry. Related:
`splk-loop-step-ok-exit-empty-output-logs-fail.md` (misleading loop log lines).
