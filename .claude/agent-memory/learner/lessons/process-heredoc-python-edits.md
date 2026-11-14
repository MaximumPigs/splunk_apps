---
hits: 2
seen: [2026-11-14, 2026-11-14]
area: process
level: skill
---
**Symptom:** easyadmin 1.4.0 session (reported by the agent): two edits made
with Python embedded in a Bash heredoc failed, once on a `'\u0000'` inside
the heredoc and once on quoting. Writing the same edit script to a file in
the scratchpad and running it worked every time.

**Cause:** a heredoc passes through the shell's quoting and escape handling
before Python sees it: escapes such as `\u0000`, `$`, backticks and nested
quotes change or break the script. Any multi-line edit script, in any app,
is exposed.

**Fix:** write the edit script to a scratch file (Write tool), then run
`python <file>`; or use the Edit tool for exact replacements.

**Catch earlier:** note in `dev-loop` ("Editing files").
