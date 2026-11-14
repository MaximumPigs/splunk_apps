---
hits: 1
seen: [2026-11-15]
area: security
level: lesson
---
**Symptom:** the bash guard's push-to-main rule (`\bmain\b`) refused a
legitimate push because the branch was named `guard/no-branch-tracking-main`
(PR #24). Narrowing it to `(\s|:|\brefs/heads/)(main|master)(?=\s|$|[|;&])`
made `splk` run log `security FAIL branch 1 medium`: `+main`, quoted
`"main"` / `'HEAD:main'`, `bash -c "... main"`, `heads/main`, `main~0` and
`main)` were no longer denied, though the old rule caught them. Later
re-reviews found smaller gaps in the tracking rules (quoted start point,
`worktree add -b`, `checkout --track origin/main`, attached `-bx`).
**Cause:** the fix listed what may *surround* the token (an allow-list of
neighbours) and was checked in one direction only (the false positive went
away). Every spelling the old rule denied by accident was silently dropped.
**Fix:** boundaries that say what a ref name cannot contain:
`(?:(?<![\w./-])|(?<=refs/heads/)|(?<=heads/))(main|master)(?![\w/.-])`,
with each bypass spelling added as a test in `tests/test_agent_hooks.py`
(174 hook tests at the end).
**Catch earlier:** before narrowing any guard regex, write the corpus of deny
spellings as tests and see them pass on the old rule: refspec prefixes (`+`),
quotes, wrappers (`bash -c`), suffixes (`~0`, `^`), partial ref paths
(`heads/`, `remotes/origin/`), attached short options. Then narrow until the
false positive passes and the corpus still denies. Playbook:
`probe-a-hook-with-decide`.
