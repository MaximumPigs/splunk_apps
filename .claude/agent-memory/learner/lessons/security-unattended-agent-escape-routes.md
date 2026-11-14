---
hits: 1
seen: [2026-11-15]
area: security
level: lesson
---
**Symptom:** The first `splunk-security-review` of `splk loop` found that
unattended steps could push or merge as the owner through spellings the guard
missed: `git -C . push`, bare `git push`, `gh -R x pr merge`, `gh.exe`,
`gh api .../merge`, a gh alias. Steps also inherited `.env` secrets (splk's
`load_env_file` puts them in `os.environ`), and the loop's own PR comment,
posted under the owner's login, would read back as owner feedback.
**Cause:** Deny lists matched one spelling of a command, and the child process
inherited the parent's whole environment and credentials. Identity-based
trust (author == owner) cannot tell the agent from the person when both use
the owner's login.
**Fix:** `SPLK_LOOP=1` selects stricter hook rules; steps run with a scrubbed
environment, git credential helper disabled, and an optional read-only GH
token; the loop's comments carry a marker and are ignored as feedback.
Verified with a real headless step in the exact step environment: hooks saw
`SPLK_LOOP=1`, the token was absent, push, merge and hook edits were denied.
**Catch earlier:** For any unattended or spawned agent, start from an
allowlist environment, and test guards against variants (`-C`, `-R`, `.exe`,
`api`, aliases), not one spelling. Mark machine-written comments.
