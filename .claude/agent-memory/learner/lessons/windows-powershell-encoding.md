---
hits: 1
seen: [2026-09]
area: windows
level: hook
---
**Symptom:** Every em dash in a file on `main` became `a-hat, euro, right-quote`.

**Cause:** PowerShell `Get-Content` read UTF-8 with the ANSI codepage; 5.1's
`-Encoding utf8` writes a BOM. The terminal rendered both back looking fine.

**Fix:** Write files with the file tools or Python with an explicit encoding.

**Catch earlier:** Promoted to `.claude/rules/windows-environment.md`; the bash
guard denies `Set-Content`/`Out-File`/`Add-Content`, and the edit hook rejects
BOMs and mojibake.
