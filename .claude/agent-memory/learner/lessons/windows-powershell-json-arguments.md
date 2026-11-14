---
hits: 1
seen: [2026-11-15]
area: windows
level: lesson
---
**Symptom:** A JSON string passed as `claude -p --json-schema <json>` from
PowerShell arrived mangled (quotes re-tokenised).
**Cause:** PowerShell 5.1 rewrites embedded double quotes when invoking native
programs.
**Fix:** Call from Python `subprocess` with an argument list (as
`tools/splk/loop.py` does); no shell quoting involved.
**Catch earlier:** Same family as `windows-powershell-encoding.md` and
`process-heredoc-python-edits.md`: pass structured arguments from Python, not
through a shell.
