---
hits: 1
seen: [2026-11-14]
area: security
level: pattern
---
**Symptom:** easyadmin 1.3.0 precedence view, which shows `.conf` values to
admins and masks secrets by attribute name. The first `SECRET_RE` matched
anywhere in the name: it hid non-secrets (`pass4SymmKey_minLength`,
`invalidateSessionTokensOnLogout`) and missed `privKey`, `*_key`, `pwd` and
`scriptSecureArguments`. `splunk-security-review` at 20:32:38 (LOW,
`easyadmin_conf_core.py:58`, "misses common secret names") and 20:45:31 (LOW,
"misses authentication.conf scriptSecureArguments"). Its INFO at 20:32:38:
`CONF_NAME_RE` used `$`, which accepts `'props\n'`.

**Cause:** an unanchored substring regex over setting names is both too wide
(settings *about* a secret) and too narrow (secret names that do not contain
the usual words). Python's `$` also matches before a trailing newline. Any
masking or allow-list by name in any app has these traps.

**Fix:** `SECRET_RE` anchored at the end of the name with `\Z`, widened
suffixes (`pwd`, `priv_?key`, `_key`...), plus the exact-name list
`SECRET_NAMES`; `CONF_NAME_RE` ends in `\Z`
(`apps/easyadmin/bin/easyadmin_conf_core.py`, unit tests in
`tests/test_easyadmin_conf_core.py`). Review at 20:45:31 had no finding
above LOW.

**Catch earlier:** playbook `conf-precedence-from-files` (hardening list).
Unit-test both directions: names that must be masked and look-alikes that
must not.

**Pattern:** `conf-precedence-from-files`.
