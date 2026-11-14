---
hits: 1
seen: [2026-11-12]
area: splunkd
level: pattern
---
**Symptom:** easyadmin: after the `update_role` fix, live stayed red with the
old error for about 5 minutes. Runs at 06:26, 06:27 and 06:28 still failed
`test_bulk_update_grants_and_revokes_in_one_submit` and
`test_revoking_the_last_index_empties_the_list` (`assert 0 == 1`); the 06:26
run came right after a green `deploy` ("Installed easyadmin 1.0.0 on local").

**Cause:** any `restmap.conf` handler with `scripttype = persist` is affected.
splunkd keeps the handler's Python process alive and does not reload its code
on app reinstall or `apps/local/_reload`. So `splk deploy` was green, but the
old `bin/` code kept serving requests until the process idled out (the new
code was running by 06:34).

**Fix:** no code change. We waited for the idle timeout.
`splk deploy --restart` (which asks the person) would have applied it at once.

**Catch earlier:** after changing `bin/` behind a persist handler, restart or
wait. Then check the app's log or `index=_internal` to confirm which code is
running before you debug a fix that seems not to work. Candidate check:
`splk deploy` warns when `bin/` changed and `restmap.conf` has `scripttype = persist`.

**Pattern:** the working recipe is in playbook `rest-endpoint-behind-page`.
