---
confirmed: 1
seen: [2026-11-15]
apps: [repo-hooks]
---
# Probe a hook from a Python file, not the shell

**Use when:** changing or reviewing a deny rule in `.claude/hooks/` (for
example `guard_bash.py`) and you need to see what it allows or denies.

**Recipe:**

1. Write a scratch Python file (scratchpad directory, not the repo) that
   imports the hook module and calls `guard_bash.decide(cmd, environ={})` for
   each candidate command string. Run it with `python <file>`.
2. Print the verdict per string. Include the deny corpus (prefixes, quotes,
   wrappers, suffixes, partial ref paths) and the legitimate commands that
   must pass.
3. Move every string that matters into `tests/test_agent_hooks.py` as a test.
   Run the hook tests.

**Why this way:** typing the probe as a shell command makes the guard judge
the probe itself. During the PR #24 review the guard denied the reviewer's own
probe script because the script text contained the denied strings. Calling
`decide()` bypasses the shell, so nothing is executed and nothing is refused.
Test strings live in the test file, so they are reviewed like code. Heredoc
Python is also unreliable here
(`lessons/process-heredoc-python-edits.md`).
Pair with `lessons/security-guard-regex-narrowing-reopens-bypasses.md`: probe
both directions.

**Verify:** the hook test suite passes (174 tests on PR #24) and a re-review
finds no unreviewed bypass spelling.

**Reference:** `.claude/hooks/guard_bash.py`, `tests/test_agent_hooks.py`.
