---
paths:
  - "apps/**/bin/**/*.py"
  - "apps/**/appserver/**"
  - "apps/**/restmap.conf"
  - "apps/**/web.conf"
  - "apps/**/commands.conf"
  - "apps/**/inputs.conf"
  - "apps/**/*.meta"
  - "apps/**/data/ui/**"
---

# App security (prevention)

Write it safe the first time; the `splunk-security-review` skill checks it
after. Run that skill before finishing any change to these files.

- REST handlers: `requireAuthentication = true`, `passSystemAuth` off, and
  every splunkd call made with the caller's own session token, so splunkd
  enforces their capabilities. URL-quote every name in a path (`safe=""`).
- Validate input against allow-lists in `<app>_core.py` (field names, sizes,
  counts) where unit tests can cover the rejections.
- Page JS: data reaches the DOM only via `.text()`, `.val()` or `.attr()`;
  never `.html()`, `innerHTML` or string-built markup. POSTs send
  `X-Splunk-Form-Key`. Nothing changes state on GET.
- Never concatenate user or event data into SPL, `| rest` paths or shell
  commands.
- Secrets: `storage/passwords` in apps, never conf or source; never logged.
- `default.meta`: writes for `admin` and `sc_admin` only; `export = system`
  only when another app needs the object.
