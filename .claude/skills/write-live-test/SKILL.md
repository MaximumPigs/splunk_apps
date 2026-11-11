---
name: write-live-test
description: Write a live test that runs SPL on the real Splunk target and asserts on results. Use when adding or changing a search command, macro, saved search, eventtype, field extraction, props/transforms, or dashboard search.
argument-hint: "[app-id] [what to test]"
---

# Write a live test

Live tests live in `tests/live/<app>/test_<app>_<topic>_live.py` and run with
`splk test --live <app>` (or as the last stage of `splk dev <app>`). They are
skipped in plain `pytest` and in CI.

## Fixtures (from `tests/live/conftest.py`)

| Fixture | Use |
| --- | --- |
| `search(spl, earliest, latest)` | Run SPL, get rows (list of dicts, all values are strings). |
| `seed(events, sourcetype)` | Index raw events into the test index; returns a unique `source` marker. |
| `splunk` | The REST client (`app_info`, `oneshot`, ...). |
| `target` | Target config, including `target.test_index`. |
| `expected_version(app)` | Version from `app.conf`. |

## Choose the input

- **Pure search logic** (commands, macros, eval): synthesise input with
  `| makeresults` + `eval`. No index needed, fully deterministic. See
  `tests/live/fillcontinuous/` for the pattern.
- **Extractions and sourcetypes** (props/transforms): `seed()` real raw events
  with the app's sourcetype, then search `index=<test_index> source="<marker>"`.
  Index-time behaviour only applies to events indexed after the deploy.

## Paths a small test cannot reach

- **Multi-chunk**: commands see one protocol chunk per call. Generate tens of
  thousands of rows (`| makeresults count=50000 | streamstats count as n | eval ...`),
  punch a known hole, then assert `total_rows`, `dc()` of each dimension and a
  summed measure. A three-row test passes a broken buffering implementation.
- **Heterogeneous rows**: for commands that add different fields per record,
  mix event shapes in one search and assert through a downstream `| table`,
  not the command's own message. Same-shape data hides dropped columns.
- **Messages**: assert on the text users see (`str.format` rendering), since a
  `%`-style template passes silently in a stub.

## Rules

- Never assert or document behaviour you have not observed on the target.
  Check a claim (e.g. how a built-in command treats duplicates) with
  `splk search` first, then encode the observed result as a test.
- Fixed timestamps and literal expected values. No "greater than zero" asserts.
- Convert `_time` with `| eval epoch=_time` before `table`; JSON results
  format `_time` as a string.
- One behaviour per test; the docstring says what the README promises.
- Each test must fail if the feature is removed. Check that by breaking it once.
- Log nothing secret; the `search` fixture already logs the SPL.
- Searches run as oneshot jobs, which return Splunk's error messages. Do not
  switch to `search/jobs/export`: it returns 200 with an empty body on failure.

## Example (seeded extraction)

```python
def test_status_extracted(seed, search, target):
    """props.conf extracts status from acme:web access lines."""
    marker = seed(['10.0.0.1 - - [01/Jan/2026:00:00:00 +0000] "GET / HTTP/1.1" 404 12'],
                  sourcetype="acme:web")
    rows = search('search index=%s source="%s" | table status' % (target.test_index, marker),
                  earliest="0", latest="+1d")
    assert rows == [{"status": "404"}]
```
