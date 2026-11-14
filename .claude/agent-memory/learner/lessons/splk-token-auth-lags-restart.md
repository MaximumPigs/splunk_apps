---
hits: 1
seen: [2026-11-14]
area: splk
level: skill
---
**Symptom:** easyadmin 1.2.0. `splk dev` at 17:37:03 stopped at deploy
("splunkd needs a restart (pass --restart)", the new endpoint needed
registering). After `splk deploy --restart` reported splunkd back (17:39:37),
the live run at 17:40:22 gave `92 errors in 7.68s`, every one in setup:
`Cannot reach local (https://127.0.0.1:8089 ...): GET /services/server/info
failed: HTTP 401 call not properly authenticated`. `splk doctor` passed after
about three tries 15 s apart (roughly 30 s).

**Cause:** after a restart splunkd answers on 8089 before it accepts token
authentication. `splk`'s restart wait checks reachability, not an
authenticated call, so it declares the target ready too early. Affects any app
and any stage run straight after `--restart`.

**Fix:** none in code. Waiting and rerunning `splk doctor` until it passed,
then rerunning the stage.

**Catch earlier:** added to `dev-loop` ("Reading failures", deploy row): a
401 straight after a restart is this, not a bad token. Candidate `splk`
improvement (not built; `tools/splk` was not changed): after a restart, poll
`/services/server/info` **with the token** until it returns 200 before
reporting splunkd back.
