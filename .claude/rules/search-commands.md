---
paths:
  - "apps/**/bin/**/*.py"
  - "apps/**/commands.conf"
  - "apps/**/searchbnf.conf"
  - "tests/test_*_command.py"
---

# Custom search commands (splunklib)

Each point below cost a real defect. Read the SDK source in `apps/<app>/lib/splunklib/`
before relying on any docstring.

## Chunking

- `transform()` / `stream()` is called **once per protocol chunk**, not once per
  search. `SearchCommand._execute_v2` sets `self._finished` from the chunk's
  metadata before calling it. A command that needs every row must buffer:

  ```python
  def transform(self, records):
      self._buffered.extend(records)
      if getattr(self, "_finished", None) is False:
          return                  # more chunks coming
      ...                         # compute over self._buffered, then yield
  ```

  Treat `None` as final: protocol v1 never sets it. Always `chunked = true`.
- Use `EventingCommand` (`type = events`) when the whole result set is needed
  at the search head; `StreamingCommand` sees fragments.
- **A chunk's output columns are fixed by the first record written.**
  `RecordWriterV2._write_record` takes `_fieldnames` once per chunk from the
  first record's keys plus `custom_fields`. A field added only to later records
  is silently dropped from the wire. Register every field name the chunk will
  produce (`self._record_writer.custom_fields.update(...)`) **before** yielding
  the first record. `custom_fields` persists across chunks, so the exposure is
  the chunk where a name first appears.

## Messages

- `write_info` / `write_warning` / `write_error` render with **`str.format`**,
  not `%`: `self.write_info("added {} row(s)", n)`.
- Never concatenate user text into the template; a `{` in it raises inside the
  renderer. Use `self.write_error("{}", str(error))`. `error_exit()` has the same
  flaw: write the error with `"{}"`, log it, then `sys.exit(1)`.

## Options and arguments

- Validate in `prepare()`, which runs after argument parsing.
- `options.reset()` applies declared defaults and `process()` calls it. Tests that
  bypass `process()` must call it, or every default reads `None`.
- Bare words land in `self.fieldnames`, including the literal `by` and stray
  commas. Strip a leading `by`; split each token on commas.
- Option values are literal strings: `fillvalue="null"` writes the text `null`.
- Fail loudly: a malformed option aborts the search with a readable message.

## Resource limits (shared search heads)

- Bound the **output**, not just intermediates: check products such as
  `buckets x series` before materialising.
- Every resource option uses `validators.Integer(minimum=1, maximum=<default>)`.
  A ceiling the caller can raise is not a ceiling.
- `float()` accepts `inf`, `nan` and overflows `"1e400"` silently: reject
  non-finite values with `math.isfinite`.
- No `eval`/`exec`, `subprocess`, file or network I/O, or deserialisation in a
  search command without the person agreeing to it first.

## Testing

- Pure logic in `bin/<app>_core.py` (no splunklib import), unit-tested.
- A test double of an SDK call must copy the SDK's real semantics (open the
  source). A `%`-rendering stub once passed a test while the real command
  emitted a literal `%d` to users.
- Live tests must cover the **multi-chunk** path (tens of thousands of rows) and,
  for commands with per-record fields, **heterogeneous** rows whose field sets
  differ, asserting through a downstream `table`, not the command's own summary.
- A changed `.py` needs no restart (splunkd spawns the script per search);
  `commands.conf` changes do.
