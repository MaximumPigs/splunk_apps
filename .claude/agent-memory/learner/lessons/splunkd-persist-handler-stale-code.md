---
hits: 2
seen: [2026-11-12, 2026-11-14]
area: splunkd
level: rule
---
**Symptom:** easyadmin, twice.
- 2026-11-12: after the `update_role` fix, live stayed red with the old error
  for about 5 minutes. Runs at 06:26, 06:27 and 06:28 still failed
  `test_bulk_update_grants_and_revokes_in_one_submit` and
  `test_revoking_the_last_index_empties_the_list` (`assert 0 == 1`); the 06:26
  run came right after a green `deploy` ("Installed easyadmin 1.0.0 on local").
- 2026-11-14 (1.1.0, tab and label changes in `bin/easyadmin_core.py`): the
  first deploy of the changed Python served new code, but a later deploy kept
  serving the previous labels for minutes. The person approved
  `splk deploy --restart`, yet no restart happened: `splk.log` shows
  `GET /services/messages/restart_required -> 404`, so the deploy stage saw
  nothing to restart for.

**Cause:** any `restmap.conf` handler with `scripttype = persist` is affected.
splunkd keeps the handler's Python process alive and does not reload its code
on app reinstall or `apps/local/_reload`. A change to `bin/` alone never posts
splunkd's "restart required" message, and `splk deploy --restart` restarts
**only** when that message exists (`tools/splk/stages.py` `deploy()`:
`if client.restart_required(): if restart and target.allow_restart: ...`).
So `--restart` is a no-op for a Python-only change. The 2026-11-12 entry of
this lesson claimed `--restart` "would have applied it at once"; that was
never observed and was wrong.

**Fix:** no code change either time. The only route that worked was the
handler's idle timeout (new code running within about 5 to 10 minutes).

**Catch earlier:** after changing `bin/` behind a persist handler, prove which
code is running before trusting any run: make a change only the new code
shows (a label, a message, or an assertion only new code passes) and check it
with `splk search` over the endpoint, `splk shot`, or the app's log. If the
old code is still serving, wait; do not debug the fix. Promoted to
`.claude/skills/dev-loop/SKILL.md` ("Reading failures": stale code).
Candidate tool fix (not built): a forced restart option in `splk deploy`
(still asking the person) that restarts even without `restart_required`, or a
warning when `bin/` changed and `restmap.conf` has `scripttype = persist`.

**Pattern:** the working recipe is in playbook `rest-endpoint-behind-page`.
