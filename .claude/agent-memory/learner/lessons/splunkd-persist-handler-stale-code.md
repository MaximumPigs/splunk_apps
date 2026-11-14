---
hits: 4
seen: [2026-11-12, 2026-11-14, 2026-11-14, 2026-11-14]
area: splunkd
level: rule
---
**Symptom:** easyadmin, four sessions.
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
- 2026-11-14 (1.2.0, `bin/easyadmin_apps_core.py`), twice after green
  deploys: 17:54:36 `test_model_lists_apps_and_objects_with_what_splunkd_allows`
  still saw the old app order (sort by label was new), and 17:59:32
  `test_invalid_requests_are_rejected_before_splunkd` "DID NOT RAISE" (the
  new 400 for `..`). Each cleared in about 2 minutes (green 17:58:01 and
  18:03:02) with no code change. Asserting on something only the new code
  produces is what proved which code was serving.
- 2026-11-14 (1.4.0, copy feature): after the 22:43:02 deploy, a retry loop
  ran the live tests about every 2 minutes; nine runs from 22:43:34 to
  23:00:45 all failed `test_props_objects_and_tags_are_not_offered_for_copying`
  (`assert True is False`, old `TYPES`). After roughly 7 to 10 minutes with
  no requests, the first run at 23:10:28 passed (104 passed).

**Cause:** any `restmap.conf` handler with `scripttype = persist` is affected.
splunkd keeps the handler's Python process alive and does not reload its code
on app reinstall or `apps/local/_reload`. A change to `bin/` alone never posts
splunkd's "restart required" message, and `splk deploy --restart` restarts
**only** when that message exists (`tools/splk/stages.py` `deploy()`:
`if client.restart_required(): if restart and target.allow_restart: ...`).
So `--restart` is a no-op for a Python-only change. The 2026-11-12 entry of
this lesson claimed `--restart` "would have applied it at once"; that was
never observed and was wrong.

**Fix:** no code change. The only route that worked was the handler's
**idle** timeout. Correction (2026-11-14, 1.4.0): the timeout counts from the
last request, so every test run, `splk shot` or page load against the
endpoint resets it. Earlier hits looked like "2 to 10 minutes" because the
waits happened to be quiet; polling kept the old code alive for 18+ minutes.

**Catch earlier:** after changing `bin/` behind a persist handler, prove which
code is running before trusting any run: make a change only the new code
shows (a label, a message, or an assertion only new code passes) and check it
with `splk search` over the endpoint, `splk shot`, or the app's log. If the
old code is still serving, **stop sending requests to the endpoint**,
wait about 7 minutes idle, then run once; never poll or loop retries. Promoted to
`.claude/skills/dev-loop/SKILL.md` ("Reading failures": stale code).
Candidate tool fix (not built): a forced restart option in `splk deploy`
(still asking the person) that restarts even without `restart_required`, or a
warning when `bin/` changed and `restmap.conf` has `scripttype = persist`.

**Pattern:** the working recipe is in playbook `rest-endpoint-behind-page`.
