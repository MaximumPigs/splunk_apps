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
- Without a 3.9 interpreter, check grammar with
  `ast.parse(source, filename=path, feature_version=(3, 9))`. The edit hook does
  this for app, script, tool and hook code. It cannot catch a stdlib call added
  after 3.9: only running on 3.9 (CI) proves that.

## Vendored splunklib

- Change it only with `python scripts/vendor_splunklib.py <app>`, which verifies
  PyPI's SHA-256 and should reproduce the committed tree byte for byte.
- `splunklib/ai/` is excluded on purpose: its `match` statements are the only
  3.10+ syntax in splunk-sdk 3.0.0, and nothing else imports it. Do not
  downgrade the SDK to "fix" 3.9; `check_python_sdk_version` wants 3.0.0+.
- On any SDK bump, re-run the 3.9 grammar check over the vendored tree and diff
  `search_command.py`, `eventing_command.py` and `internals.py` for changes to
  chunk handling and record writing.
