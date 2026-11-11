---
hits: 1
seen: [2026-09]
area: python
level: rule
---
**Symptom:** splunk-sdk 3.0.0 declares `requires_python >= 3.13`, which looked
fatal for Splunk's 3.9 runtime.

**Cause:** Metadata, not code: the only 3.10+ syntax is four `match`
statements in `splunklib/ai/`, which nothing else imports.

**Fix:** Vendor 3.0.0 without `ai/`; keeps `check_python_sdk_version` happy and
3.9 working.

**Catch earlier:** Promoted to `.claude/rules/python.md`. On any SDK bump,
re-run the 3.9 grammar check and diff the chunk-handling modules.
