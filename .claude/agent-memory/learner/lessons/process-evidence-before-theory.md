---
hits: 2
seen: [2026-09, 2026-11-14]
area: process
level: rule
---
**Symptom:** two diagnoses built on theory while the answer was already in hand.
- 2026-09: an AppInspect API job failed and a rate-limit theory was asserted.
  The tell (the job started before the secret was saved) was under-weighted.
- 2026-11-14, easyadmin: a temporary UI probe of Splunk Web's role editor
  assumed the editor was a modal `[role=dialog]` and failed waiting for it.
  The failure screenshot (`build/reports/ui/easyadmin/<test>-FAILED.png`)
  showed at once that on 10.6.1 the role name opens a full page,
  `/manager/launcher/authorization/roles/edit/<role>`, with `[role=tab]` tabs.

**Cause:** theorising before reading the evidence already produced: the
failure screenshot, the run's timestamps, the error text, `.agent/logs/splk.log`.

**Fix:** 2026-09: re-saved the stale secret and re-ran. 2026-11-14: rewrote
the probe for the full page; its findings are in playbook
`splunkd-roles-rest-api`.

**Catch earlier:** open the failure artefact first (the `-FAILED.png`, the
report, the log line, the timestamps), then form a theory; say how confident
a diagnosis is and own it when wrong. Promoted to the `dev-loop` skill's
"Reading failures" section; also in `.claude/rules/ci-and-release.md` (CI
secrets) and `CLAUDE.md` ("own a wrong diagnosis explicitly").
