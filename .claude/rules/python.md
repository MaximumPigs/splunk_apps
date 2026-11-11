---
paths:
  - "**/*.py"
---

# Python rules

- Use `logging`, never `print`, except for a CLI's intended stdout output.
  - App search commands: `self.logger` from splunklib.
  - `tools/splk`: `splk.logs.get_logger("<module>")`; secrets are masked there.
  - Hooks: `_common.get_logger`; hooks must never write logs to stdout/stderr.
- Comment the *why*: constraints, Splunk quirks, AppInspect checks a line exists for.
- Code under `apps/*/bin/`, `scripts/`, `tools/` and `.claude/hooks/` must run on
  Python 3.9: no `match`, no `X | None`, no `tomllib` without a fallback.
  CI byte-compiles app scripts on 3.9 to enforce this.
- Keep pure logic out of splunklib-dependent modules so it is unit-testable
  without Splunk (`<app>_core.py` pattern).
- Prefix helper modules with the app id; `bin/` directories share one namespace.
- No new runtime dependencies inside an app without vendoring them into `lib/`.
