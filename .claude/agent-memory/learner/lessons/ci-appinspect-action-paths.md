---
hits: 1
seen: [2026-09]
area: ci
level: rule
---
**Symptom:** Risk of a silent clean pass or a confusing upload failure in the
AppInspect workflows.

**Cause:** `appinspect-cli-action` wants the package file (given a directory it
scans the first entry); `appinspect-api-action` wants a directory (it appends
`ls` output). The action description said the opposite of its entrypoint.

**Fix:** CI passes the file to the CLI action and a one-package directory to
the API action; both expect files exist and stay empty.

**Catch earlier:** Promoted to `.claude/rules/ci-and-release.md`. Read the
entrypoint, not the description.
