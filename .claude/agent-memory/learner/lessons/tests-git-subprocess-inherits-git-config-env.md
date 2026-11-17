---
hits: 2
seen: [2026-11-17, 2026-11-17]
area: python
level: rule
---
**Symptom:** `splk dev easyadmin` unit stage failed twice (07:46 and 07:47) with
`tests.test_splk_loop::test_main_roadmap_items_reads_the_committed_file_not_the_working_copy:
CalledProcessError: ['git', '-c', 'user.name=t', ..., 'init', '-q', '-b', 'main'] returned non-zero exit status 128`.
Nothing in the diff touched it; the unmodified branch code failed too. It went
green (928 passed, 07:49) only after the session's `GIT_CONFIG_*` variables
were unset. The loop-review step reported the same. Second hit: the same test
failed in `splk dev fillcontinuous` (unit, 13:25:36, 1 failed, 932 passed) and
went green at 13:27:41 after the test was fixed.
**Cause:** any test that spawns `git` inherits the caller's environment. The
unattended loop session exports `GIT_CONFIG_COUNT` with empty
`GIT_CONFIG_KEY_n` values (the loop's credential-helper blanking, see
`loop.step_environment`). Observed with a scratch repo: empty
`GIT_CONFIG_KEY_0` makes git print `error: empty config key` /
`fatal: unable to parse command-line config` and exit 128, while
`KEY_0=credential.helper` with an empty value exits 0. So unit tests pass in an
interactive shell and fail inside the loop, and `check=True` hides git's stderr.
A second route to the same failure: an earlier test's monkeypatch undo of an
empty `GIT_CONFIG_VALUE_0` deletes it on Windows while `GIT_CONFIG_COUNT` and
`KEY_0` stay, so git fails with "missing config value GIT_CONFIG_VALUE_0"
(per the comment in the fix). The environment is shared state across tests.
**Fix:** `tests/test_splk_loop.py` now `monkeypatch.delenv`s `GIT_CONFIG_COUNT`,
`KEY_0` and `VALUE_0` before the git calls (fillcontinuous 1.1.3 branch). Rule
added to `.claude/rules/python.md`.
**Catch earlier:** the rule. Still open: other `subprocess.run(["git"...` in
`tests/` (only this test is fixed), and capturing stderr into the failure
message.
