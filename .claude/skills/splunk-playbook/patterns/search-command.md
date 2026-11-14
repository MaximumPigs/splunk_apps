---
confirmed: 1
seen: [2026-09]
apps: [fillcontinuous]
---
# Custom search command

**Use when:** adding an SPL command implemented in Python with splunklib.

**Recipe:**

1. Copy the shape of `apps/fillcontinuous/`: `bin/<command>.py` is a thin
   splunklib wrapper; `bin/<app>_core.py` holds the algorithm with no splunklib
   import and is unit-tested directly.
2. `default/commands.conf`: `chunked = true`, both `python.version = python3`
   and `python.required = 3.9, 3.13`. `default/searchbnf.conf` documents the
   syntax.
3. Vendor splunklib with `python scripts/vendor_splunklib.py <app>` (no `ai/`).
4. Follow `.claude/rules/search-commands.md` for chunking, first-record field
   names, messages and resource limits. It loads when you touch the files.

**Why this way:** the rule file lists the defects each point prevents. The
core/wrapper split is what makes the algorithm testable without Splunk.

**Verify:** unit tests over the core; a wrapper test in the style of
`tests/test_fillcontinuous_command.py`; live tests over `| makeresults` input,
including a multi-chunk case (tens of thousands of rows) and heterogeneous
rows (`write-live-test` skill).

**Reference:** `apps/fillcontinuous/`, `tests/test_fillcontinuous_*.py`,
`tests/live/fillcontinuous/`.
