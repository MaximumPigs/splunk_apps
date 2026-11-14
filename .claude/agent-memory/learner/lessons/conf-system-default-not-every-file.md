---
hits: 1
seen: [2026-11-14]
area: conf
level: lesson
---
**Symptom:** easyadmin 1.3.0 (configuration precedence view). Live run at
2026-11-14T20:13:11:
`test_easyadmin_conf_live::test_clash_between_two_apps_is_reported_in_precedence_order`
failed with `ValueError: 'system/default' is not in list`. The test assumed
the endpoint's `order` always contains `system/default`.

**Cause:** `etc/system/default` does not ship every `.conf` file: on 10.6.1
there is no `macros.conf` there. The view's `order` lists only the layers
that actually have the file, which is correct. Any code or test that walks
the four precedence layers (system local, app locals, app defaults, system
default) must expect any layer, `etc/system/default` included, to be absent
for a given conf.

**Fix:** the test compares only the layers it created
(`launcher/local` before `search/local`), with a comment saying why
(`tests/live/easyadmin/test_easyadmin_conf_live.py`).

**Catch earlier:** before asserting that a file exists in a layer, check it
on the target (a live test listing the layers, or a one-line
`splk search "| rest /services/configs/conf-<name>"`). Noted in playbook
`conf-precedence-from-files`.
