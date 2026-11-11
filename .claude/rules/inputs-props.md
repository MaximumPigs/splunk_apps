---
paths:
  - "apps/**/props.conf"
  - "apps/**/transforms.conf"
  - "apps/**/inputs.conf"
  - "apps/**/indexes.conf"
  - "apps/**/README/*.spec"
---

# Inputs, props and transforms

- Every new sourcetype gets explicit line breaking and timestamping in
  props.conf (`LINE_BREAKER`, `SHOULD_LINEMERGE = false`, `TIME_PREFIX`,
  `TIME_FORMAT`, `MAX_TIMESTAMP_LOOKAHEAD`). Do not rely on Splunk's guessing.
- Search-time extractions (`EXTRACT-`, `REPORT-`, `FIELDALIAS-`, `EVAL-`) are
  live-tested: seed a known raw event into the target's test index and assert
  the extracted fields with `splk search` logic in `tests/live/<app>/`.
- Index-time settings (line breaking, timestamps, `TRANSFORMS-`) only apply to
  data indexed after deploy, and usually need a restart. Seed fresh events
  after the deploy, never assert on old data.
- `inputs.conf` in a Cloud app: no `[script://]` or `[monitor://]` pointing at
  absolute host paths; modular inputs go through `bin/` with a `README/inputs.conf.spec`.
- Ship inputs `disabled = 1` unless the app's purpose is that input.
- Never define indexes in an app meant for Splunk Cloud.
