---
hits: 1
seen: [2026-11]
area: process
level: hook
---
**Symptom:** The squash commit for PR #9 on `main` ended with
`Co-authored-by: Claude <noreply@anthropic.com>`, although every commit
message on the branch was clean.

**Cause:** The agent's environment committed as an AI identity. GitHub's
squash merge appends a `Co-authored-by` line for each commit author other than
the person merging, so the author alone breaks the owner's rule.

**Fix:** Commit as the owner's identity (their GitHub noreply address). The
trailer already on `main` can only be removed by a force push, which is the
owner's call.

**Catch earlier:** The bash guard denies `git commit` while the resolved author
(`--author`, `GIT_AUTHOR_*`, `-c user.*`, git config) is an AI identity, and
any commit command carrying a `Co-Authored-By` trailer. Tested in
`tests/test_agent_hooks.py`.
