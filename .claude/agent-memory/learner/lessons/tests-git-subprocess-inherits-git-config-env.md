---
hits: 1
seen: [2026-11-17]
area: python
level: lesson
---
**Symptom:** `splk dev easyadmin` unit stage failed twice (07:46 and 07:47) with
`tests.test_splk_loop::test_main_roadmap_items_reads_the_committed_file_not_the_working_copy:
CalledProcessError: ['git', '-c', 'user.name=t', ..., 'init', '-q', '-b', 'main'] returned non-zero exit status 128`.
Nothing in the diff touched it; the unmodified branch code failed too. It went
green (928 passed, 07:49) only after the session's `GIT_CONFIG_*` variables
were unset. The loop-review step reported the same.
**Cause:** any test that spawns `git` inherits the caller's environment. The
unattended loop session exports `GIT_CONFIG_COUNT` with empty
`GIT_CONFIG_KEY_n` values (the loop's credential-helper blanking, see
`loop.step_environment`). Observed with a scratch repo: empty
`GIT_CONFIG_KEY_0` makes git print `error: empty config key` /
`fatal: unable to parse command-line config` and exit 128, while
`KEY_0=credential.helper` with an empty value exits 0. So unit tests pass in an
interactive shell and fail inside the loop, and `check=True` hides git's stderr.
**Fix:** none committed yet; the run was made green by unsetting the variables.
**Catch earlier:** a test helper that runs git in a temp repo should
`monkeypatch.delenv` every `GIT_CONFIG_*` (and set `GIT_CONFIG_GLOBAL`/`SYSTEM`
to the null device) and use `capture_output` stderr in the failure message.
Check other `subprocess.run(["git"...` in `tests/` for the same gap. Promote
to a rule in `.claude/rules/python.md` on a second hit.
