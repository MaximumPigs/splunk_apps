---
hits: 3
seen: [2026-11-14, 2026-11-14, 2026-11-15]
area: process
level: rule
---
**Symptom:** easyadmin 1.4.0 session (reported by the agent): two edits made
with Python embedded in a Bash heredoc failed, once on a `'\u0000'` inside
the heredoc and once on quoting. Writing the same edit script to a file in
the scratchpad and running it worked every time. Third hit (2026-11-15,
1.4.0 follow-up): an escaped `\n` in an assertion fix was altered by the
heredoc, after the `dev-loop` note existed.

**Cause:** a heredoc passes through the shell's quoting and escape handling
before Python sees it: escapes such as `\u0000`, `$`, backticks and nested
quotes change or break the script. Any multi-line edit script, in any app,
is exposed.

**Fix:** write the edit script to a scratch file (Write tool), then run
`python <file>`; or use the Edit tool for exact replacements.

**Catch earlier:** the `dev-loop` note did not stop the third hit (that
skill is not always loaded), so it is now a line in
`.claude/rules/windows-environment.md`, which loads every session. If it
recurs, a bash-guard check that warns on `python - <<` with backslashes in
the body is the next step (a hook change, so ask the person).
