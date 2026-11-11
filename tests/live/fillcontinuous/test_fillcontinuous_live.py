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
