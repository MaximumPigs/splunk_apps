---
hits: 1
seen: [2026-09]
area: extractnv
level: rule
---
**Symptom:** Fields added only to some records vanished from results, while
the command's own counts were correct.

**Cause:** `RecordWriterV2._write_record` fixes a chunk's columns from the
first record's keys plus `custom_fields`; later new names are dropped from the
wire. Same-shape test data hid it.

**Fix:** Buffer the chunk, register every field name in
`self._record_writer.custom_fields` first, then yield.

**Catch earlier:** Promoted to `.claude/rules/search-commands.md`; live tests
use heterogeneous rows and assert via downstream `| table`. Reproduced live with
ten events of three shapes.
