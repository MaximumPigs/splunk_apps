---
paths:
  - "apps/**/*.conf"
  - "apps/**/*.meta"
  - "apps/**/app.manifest"
---

# Splunk .conf and metadata rules

- Only `default/` and `metadata/default.meta`. Never create `local/` or
  `local.meta`: AppInspect fails a Cloud package that contains them.
- `app.conf`: `[launcher] version` and `[id] version` must match; bump both
  together. `[ui] label`, `app.manifest` `info.title` and the Splunkbase listing
  change together.
- Never set `check_for_updates = false`. Splunkbase rejects it, and only the full
  (untagged) AppInspect run catches it.
- `is_configured = false` unless the app really has a setup page.
- One key per line, `key = value`, no duplicate keys in a stanza (Splunk keeps
  only the last, silently). LF endings.
- Comment non-obvious settings with the reason, as existing files do.
- After a conf change, `splk dev <app>`; if deploy reports a restart is needed,
  ask the person before `--restart`.
