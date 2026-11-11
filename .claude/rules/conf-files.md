---
paths:
  - "apps/**/*.conf"
  - "apps/**/*.meta"
  - "apps/**/app.manifest"
---

# Splunk .conf and metadata rules

- Only `default/` and `metadata/default.meta`. Never create `local/` or
  `local.meta`: AppInspect fails a Cloud package that contains them.
- `app.conf`:
  - `[launcher] version` and `[id] version` must match; bump both (and
    `app.manifest`) together.
  - `[id] name` must equal the app's directory name.
  - `[install] is_configured = true` is a **hard AppInspect failure**; keep
    `false` unless the app really has a setup page.
  - Never set `check_for_updates = false`. Splunkbase rejects it ("must not be
    disabled"); the resulting `check_for_updates_disabled` warning is expected
    and permanent. Only the full, untagged AppInspect run sees that check.
  - `[launcher] author = MaximumPigs`; author URL `https://github.com/maximumpigs`.
- `[ui] label`, `app.manifest info.title` and the Splunkbase listing name
  change together (see the Splunkbase rule).
- `default.meta`: any `write` list that grants `admin` must also grant
  `sc_admin`. The `admin` role does not exist for Cloud customers, and
  `check_kos_are_accessible` fails without it.
- `commands.conf` Python settings, both declared:

  ```ini
  python.version = python3        # read by Splunk 10.0 and 10.1
  python.required = 3.9, 3.13     # read by Splunk 10.2+, picks the highest available
  ```

  Supported floor is **Splunk 9.3** (first with Python 3.9 by default). 9.0 to
  9.2 run 3.7 whatever the app declares. Widen the claim only by adding
  3.7/3.8 to CI and fixing what surfaces, never by rewording.
- One key per line, `key = value`, no duplicate keys in a stanza (Splunk keeps
  only the last, silently). LF endings.
- Comment non-obvious settings with the reason, as existing files do.
- After a conf change, `splk dev <app>`. `commands.conf` changes need a restart;
  ask the person before `--restart`.
