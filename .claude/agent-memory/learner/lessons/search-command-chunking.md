---
hits: 1
seen: [2026-09]
area: fillcontinuous
level: rule
---
**Symptom:** A buffering command would only have processed the first chunk of
a large result set; three-row tests passed.

**Cause:** `transform()` is called once per protocol chunk;
`SearchCommand._execute_v2` sets `self._finished` before each call. SDK
docstrings implied it sees the whole set.

**Fix:** Keep buffering while `_finished is False`; treat `None`
(protocol v1) as final.

**Catch earlier:** Promoted to `.claude/rules/search-commands.md` and the
multi-chunk recipe in `write-live-test` (tens of thousands of rows).
