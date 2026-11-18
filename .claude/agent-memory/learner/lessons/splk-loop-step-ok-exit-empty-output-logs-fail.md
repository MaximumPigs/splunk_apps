---
hits: 2
seen: [2026-11-18, 2026-11-18]
area: splk
level: lesson
---
**Symptom:** easyadmin run log: `FAIL easyadmin loop-implement ok / ok / sonnet`.
A red stage whose message is the word "ok". The step file
`.agent/loop/steps/20261118-052720-implement.json` shows `kind: ok`,
`exit: 0`, `detail: ""` and `output: {}`: the headless step exited cleanly but
returned no `structured_output`, so `output.get("status") == "done"` was false.
The loop carried on to the build and dev stages, which went green, so the FAIL
was never explained. Why `structured_output` was empty was not established.
**Second hit (easyadmin 1.7.2, 21:44):** `FAIL easyadmin loop-review ok / ok /
sonnet`, same shape, on the review step. Hits 2: promote by making the fix in
`tools/splk/loop.py` (log `no structured_output` / `status=<value>`) with a
unit test; it is still unmade.
**Cause:** `tools/splk/loop.py` (`runlog.record("loop", ...)`) logs
`output.get("summary") or detail or kind` and puts `[kind, model]` in the extra
fields. With no summary and no detail, the message falls back to `kind`, which
is "ok" for a step that failed the `status == "done"` test. The log hides the
real reason (missing or non-done status) behind a word that reads as success.
**Fix:** none yet (candidate): when `ok` is false and `kind == "ok"`, log
`no structured_output` or `status=<value>` as the message, and keep `kind` as
an extra field.
**Catch earlier:** a unit test in `loop_core`/`loop.py` tests for a step that
exits 0 with `{}` output and asserts the message names the missing status.
Pattern `observe-tool-behaviour-first` (structured_output keys).
