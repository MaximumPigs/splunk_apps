---
hits: 1
seen: [2026-09]
area: fillcontinuous
level: rule
---
**Symptom:** A live search showed users a literal `%d` in the command's info
message, although unit tests passed.

**Cause:** `RecordWriter.write_message` renders with `str.format`. The test's
stub rendered with `%`, so it reproduced the bug faithfully and passed.

**Fix:** Templates use `{}`; user text is passed as an argument
(`write_error("{}", text)`), never concatenated.

**Catch earlier:** Promoted to `.claude/rules/search-commands.md`: stubs copy
the SDK's real semantics; live tests assert on user-visible text.
