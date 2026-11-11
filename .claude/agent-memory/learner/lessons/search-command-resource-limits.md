---
hits: 1
seen: [2026-09]
area: fillcontinuous
level: rule
---
**Symptom:** Security review found four ways one search could degrade a shared
search head: 401 rows over 400 series became 80,400 rows; `maxbuckets` could be
raised to 1e9; `float()` accepted `inf`/`nan`/`1e400`; vendored code unverified.

**Cause:** Only intermediates were bounded; validators had no maximum;
numeric parsing did not check finiteness.

**Fix:** Bound output products; `validators.Integer(minimum=1, maximum=<default>)`;
`math.isfinite`; SHA-256 check in `vendor_splunklib.py`.

**Catch earlier:** Promoted to `.claude/rules/search-commands.md`.
