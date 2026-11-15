"""Live tests for fillcontinuous on a real Splunk instance.

The unit suite proves the algorithm; these prove the packaged command is
registered, runs under splunkd's Python, and returns what the README promises.
Input is synthesised with makeresults, so no index or seed data is needed.
"""

import pytest

APP = "fillcontinuous"

# 2026-01-01T00:00:00Z. Fixed so expected rows are exact.
T0 = 1767225600

# Three sparse rows, the README's example shape:
#   web01 @ T0, web02 @ T0, web01 @ T0+2h
# A complete 1h grid over two hosts and three buckets is six rows.
SPARSE = (
    "| makeresults count=3 "
    "| streamstats count as n "
    "| eval _time=%d + if(n==3, 7200, 0), host=if(n==2, \"web02\", \"web01\"), count=n*10 "
    "| table _time host count" % T0
)


def _grid(rows):
    """Map (epoch, host) -> row, with epoch as int. Fails on duplicates."""
    grid = {}
    for row in rows:
        key = (int(float(row["epoch"])), row["host"])
        assert key not in grid, "duplicate row for %s" % (key,)
        grid[key] = row
    return grid


def test_app_installed_at_repo_version(splunk, expected_version):
    """The deploy stage put the version from app.conf on the instance."""
    info = splunk.app_info(APP)
    assert info is not None, "%s is not installed on the target" % APP
    assert info.get("version") == expected_version(APP)


@pytest.mark.parametrize("command", ["fillcontinuous", "fillgaps"])
def test_fills_every_bucket_for_every_host(search, command):
    """Both the command and its alias produce the full host x bucket grid."""
    rows = search(SPARSE + " | %s span=1h by host | eval epoch=_time | table epoch host count" % command)
    grid = _grid(rows)

    expected_keys = {(T0 + h * 3600, host) for h in range(3) for host in ("web01", "web02")}
    assert set(grid) == expected_keys

    # Real rows keep their values; synthesised rows get the default fillvalue 0.
    assert grid[(T0, "web01")]["count"] == "10"
    assert grid[(T0, "web02")]["count"] == "20"
    assert grid[(T0 + 7200, "web01")]["count"] == "30"
    for key in expected_keys - {(T0, "web01"), (T0, "web02"), (T0 + 7200, "web01")}:
        assert grid[key]["count"] == "0", key


def test_marker_flags_only_synthesised_rows(search):
    """marker=<field> is 1 on manufactured rows and 0 on real ones."""
    rows = search(SPARSE + " | fillcontinuous span=1h marker=was_filled by host"
                           " | eval epoch=_time | table epoch host count was_filled")
    flags = {key: row["was_filled"] for key, row in _grid(rows).items()}
    real = {(T0, "web01"), (T0, "web02"), (T0 + 7200, "web01")}
    assert {k for k, v in flags.items() if v == "0"} == real
    assert sum(1 for v in flags.values() if v == "1") == 3


def test_real_rows_keep_internal_fields_when_a_filled_row_comes_first(search):
    """_raw and a user _ field survive when a synthesised row is written first.

    host b at T0 and host a at T0+2h: the first row out is the synthesised
    (T0, a). splunklib fixes the output columns from the first record, so the
    command must register every field name up front.
    """
    rows = search(
        "| makeresults count=2 | streamstats count as n "
        "| eval _time=%d + if(n==2, 7200, 0), host=if(n==1, \"b\", \"a\"), "
        "_raw=\"event \".n, _extra=\"x\".n "
        "| fields - n "
        "| fillcontinuous span=1h by host "
        "| eval epoch=_time, raw=_raw, extra=_extra "
        "| table epoch host raw extra" % T0
    )
    grid = _grid(rows)
    assert len(grid) == 6

    assert grid[(T0, "b")]["raw"] == "event 1"
    assert grid[(T0, "b")]["extra"] == "x1"
    assert grid[(T0 + 7200, "a")]["raw"] == "event 2"
    assert grid[(T0 + 7200, "a")]["extra"] == "x2"

    for key in set(grid) - {(T0, "b"), (T0 + 7200, "a")}:
        assert not grid[key].get("raw"), key
        assert not grid[key].get("extra"), key


def test_internal_fields_survive_a_multi_chunk_result(search):
    """150,000 rows (several input chunks) with a synthesised row first.

    Series aaa has a row only at T0+1h, so (T0, aaa) is synthesised and sorts
    first. Every other host has two rows, one in each hour, except h75000, which
    has T0 only, so (T0+1h, h75000) is the second synthesised row. 150,000 real
    rows plus 2 synthesised ones make 150,002.
    """
    rows = search(
        "| makeresults count=50000 | eval k=mvrange(0,3) | mvexpand k "
        "| streamstats count as n "
        "| eval _time=%d + 3600*(n%%2), host=if(n==1, \"aaa\", \"h\".floor(n/2)), "
        "_raw=\"event \".n, _extra=\"x\".n "
        "| fields - n k "
        "| fillcontinuous span=1h by host "
        "| eval raw=_raw, extra=_extra "
        "| stats count count(raw) as with_raw count(extra) as with_extra" % T0
    )
    assert len(rows) == 1
    # Pre-fix on the dev target: with_raw=0 and with_extra=0.
    assert rows[0]["count"] == "150002"
    assert rows[0]["with_raw"] == "150000"
    assert rows[0]["with_extra"] == "150000"
