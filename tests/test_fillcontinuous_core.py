"""Unit tests for the fillcontinuous gap-filling logic.

These exercise the pure core only, so they run without Splunk or splunklib.
"""

import pytest

from fillcontinuous_core import (
    DEFAULT_MAX_BUCKETS,
    FillContinuousError,
    build_grid,
    fill,
    infer_span,
    parse_span,
)

HOUR = 3600.0


# ---------------------------------------------------------------------------
# parse_span
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("30s", 30.0),
    ("30", 30.0),
    ("5m", 300.0),
    ("5min", 300.0),
    ("5minutes", 300.0),
    ("1h", 3600.0),
    ("2hr", 7200.0),
    ("1d", 86400.0),
    ("1w", 604800.0),
    ("100ms", 0.1),
    ("  1H  ", 3600.0),
])
def test_parse_span_accepts_fixed_width_units(text, expected):
    assert parse_span(text) == expected


def test_parse_span_reads_bare_m_as_minutes_not_months():
    assert parse_span("1m") == 60.0


@pytest.mark.parametrize("text", ["1mon", "3month", "1q", "2quarters", "1y", "5years"])
def test_parse_span_rejects_calendar_units(text):
    with pytest.raises(FillContinuousError) as excinfo:
        parse_span(text)
    assert "calendar unit" in str(excinfo.value)


@pytest.mark.parametrize("text", ["", "abc", "1x", "h", "-5m", "1.2.3h"])
def test_parse_span_rejects_unparseable_input(text):
    with pytest.raises(FillContinuousError):
        parse_span(text)


def test_parse_span_rejects_zero():
    with pytest.raises(FillContinuousError):
        parse_span("0s")


def test_parse_span_requires_a_value():
    with pytest.raises(FillContinuousError):
        parse_span(None)


# ---------------------------------------------------------------------------
# infer_span
# ---------------------------------------------------------------------------

def test_infer_span_picks_the_most_common_gap():
    # Three 100s gaps and one 500s gap: the common cadence wins.
    assert infer_span([0, 100, 200, 300, 800]) == 100


def test_infer_span_breaks_ties_toward_the_smaller_span():
    # One 100s gap and one 200s gap; under-filling would be the worse error.
    assert infer_span([0, 100, 300]) == 100


def test_infer_span_needs_two_distinct_times():
    assert infer_span([500]) is None
    assert infer_span([500, 500, 500]) is None
    assert infer_span([]) is None


# ---------------------------------------------------------------------------
# build_grid
# ---------------------------------------------------------------------------

def test_build_grid_fills_interior_gaps():
    assert build_grid([0, 300], 100) == [0, 100, 200, 300]


def test_build_grid_leaves_contiguous_times_alone():
    assert build_grid([0, 100, 200], 100) == [0, 100, 200]


def test_build_grid_deduplicates_and_orders_input():
    assert build_grid([200, 0, 200, 100], 100) == [0, 100, 200]


def test_build_grid_preserves_irregular_real_boundaries():
    # A daylight-saving day is 23 hours, not 24. Both real timestamps must
    # survive untouched, and no bogus bucket may be wedged between them.
    day = 86400.0
    times = [0, day, day + 23 * HOUR]
    assert build_grid(times, day) == times


def test_build_grid_fills_partial_gaps_without_overshooting():
    # A 250s gap at span 100 fits two synthetic buckets; the third would land
    # on or past the real timestamp, so it is not emitted.
    assert build_grid([0, 250], 100) == [0, 100, 200, 250]


def test_build_grid_extends_backwards_to_range_start():
    assert build_grid([300], 100, range_start=0) == [0, 100, 200, 300]


def test_build_grid_extends_forwards_to_range_end():
    assert build_grid([0], 100, range_end=300) == [0, 100, 200, 300]


def test_build_grid_ignores_a_range_inside_the_observed_data():
    assert build_grid([0, 100], 100, range_start=50, range_end=75) == [0, 100]


def test_build_grid_returns_empty_for_no_times():
    assert build_grid([], 100) == []


def test_build_grid_enforces_max_buckets():
    with pytest.raises(FillContinuousError) as excinfo:
        build_grid([0, 10000], 1, max_buckets=100)
    assert "maxbuckets" in str(excinfo.value)


def test_build_grid_tolerates_float_spans():
    grid = build_grid([0, 0.3], 0.1)
    assert len(grid) == 4
    assert grid[0] == 0
    assert grid[-1] == 0.3


# ---------------------------------------------------------------------------
# fill
# ---------------------------------------------------------------------------

def _record(moment, host, sourcetype, count):
    return {
        "_time": str(moment),
        "host": host,
        "sourcetype": sourcetype,
        "count": str(count),
    }


def test_fill_completes_every_series_in_every_bucket():
    records = [
        _record(100, "A", "x", 1),
        _record(100, "B", "y", 2),
        _record(300, "A", "x", 3),
    ]
    result = fill(records, ["host", "sourcetype"], span=100)

    assert result.bucket_count == 3          # 100, 200, 300
    assert result.series_count == 2          # (A,x) and (B,y)
    assert result.filled_count == 3          # (A,x)@200, (B,y)@200, (B,y)@300
    assert len(result.records) == 6          # 3 buckets x 2 series


def test_fill_preserves_original_rows_untouched():
    original = _record(100, "A", "x", 7)
    result = fill([original, _record(300, "A", "x", 9)], ["host"], span=100)

    survivors = [r for r in result.records if r["count"] == "7"]
    assert survivors == [{"_time": "100", "host": "A", "sourcetype": "x", "count": "7"}]


def test_fill_uses_the_fill_value_for_aggregate_fields():
    records = [_record(100, "A", "x", 1), _record(300, "A", "x", 3)]
    result = fill(records, ["host", "sourcetype"], span=100)

    gap = [r for r in result.records if r["_time"] == "200"][0]
    assert gap == {"_time": "200", "host": "A", "sourcetype": "x", "count": "0"}


def test_fill_honours_a_custom_fill_value():
    records = [_record(100, "A", "x", 1), _record(300, "A", "x", 3)]
    result = fill(records, ["host"], span=100, fillvalue="N/A")

    gap = [r for r in result.records if r["_time"] == "200"][0]
    assert gap["count"] == "N/A"


def test_fill_orders_output_by_time_then_series():
    records = [
        _record(300, "B", "y", 1),
        _record(100, "A", "x", 1),
    ]
    result = fill(records, ["host", "sourcetype"], span=100)

    seen = [(r["_time"], r["host"]) for r in result.records]
    assert seen == [
        ("100", "A"), ("100", "B"),
        ("200", "A"), ("200", "B"),
        ("300", "A"), ("300", "B"),
    ]


def test_fill_marks_synthesised_rows_when_asked():
    records = [_record(100, "A", "x", 1), _record(300, "A", "x", 3)]
    result = fill(records, ["host"], span=100, marker_field="was_filled")

    by_time = {r["_time"]: r for r in result.records}
    assert by_time["100"]["was_filled"] == "0"
    assert by_time["200"]["was_filled"] == "1"
    assert by_time["300"]["was_filled"] == "0"


def test_fill_infers_the_span_when_it_is_omitted():
    records = [
        _record(0, "A", "x", 1),
        _record(100, "A", "x", 1),
        _record(400, "A", "x", 1),
    ]
    result = fill(records, ["host"])

    assert result.span == 100
    assert result.filled_count == 2          # 200 and 300


def test_fill_refuses_to_guess_a_span_from_one_bucket():
    with pytest.raises(FillContinuousError) as excinfo:
        fill([_record(100, "A", "x", 1)], ["host"])
    assert "span" in str(excinfo.value)


def test_fill_passes_through_rows_without_a_usable_time():
    records = [
        _record(100, "A", "x", 1),
        _record(300, "A", "x", 3),
        {"host": "A", "note": "no timestamp"},
        {"_time": "not-a-number", "host": "A"},
    ]
    result = fill(records, ["host"], span=100)

    assert result.skipped_count == 2
    assert {"host": "A", "note": "no timestamp"} in result.records
    assert len(result.records) == 3 + 2      # 3 buckets, plus the 2 passed through


def test_fill_returns_only_passthrough_when_nothing_is_timestamped():
    orphan = {"host": "A"}
    result = fill([orphan], ["host"], span=100)

    assert result.records == [orphan]
    assert result.bucket_count == 0
    assert result.filled_count == 0


def test_fill_keeps_an_absent_group_field_absent():
    records = [
        {"_time": "100", "host": "A", "count": "1"},
        {"_time": "300", "host": "A", "count": "3"},
    ]
    result = fill(records, ["host", "sourcetype"], span=100)

    gap = [r for r in result.records if r["_time"] == "200"][0]
    assert "sourcetype" not in gap


def test_fill_treats_distinct_group_values_as_distinct_series():
    records = [
        _record(100, "A", "x", 1),
        _record(100, "A", "y", 1),
    ]
    result = fill(records, ["host", "sourcetype"], span=100)

    assert result.series_count == 2
    assert result.filled_count == 0          # one bucket, both series present


def test_fill_sets_span_on_synthesised_rows_when_the_input_carries_it():
    records = [
        {"_time": "100", "_span": "100", "host": "A", "count": "1"},
        {"_time": "300", "_span": "100", "host": "A", "count": "3"},
    ]
    result = fill(records, ["host"], span=100)

    gap = [r for r in result.records if r["_time"] == "200"][0]
    assert gap["_span"] == "100"


def test_fill_omits_other_internal_fields_from_synthesised_rows():
    records = [
        {"_time": "100", "_raw": "something", "host": "A", "count": "1"},
        {"_time": "300", "_raw": "something", "host": "A", "count": "3"},
    ]
    result = fill(records, ["host"], span=100)

    gap = [r for r in result.records if r["_time"] == "200"][0]
    assert "_raw" not in gap


def test_fill_keeps_duplicate_rows_rather_than_dropping_them():
    duplicate = _record(100, "A", "x", 1)
    result = fill([duplicate, dict(duplicate)], ["host"], span=100)

    assert len([r for r in result.records if r["_time"] == "100"]) == 2


def test_fill_collects_value_fields_from_every_row():
    # The second row introduces a field the first does not have; a synthesised
    # row must still carry it, or the result set has ragged columns.
    records = [
        {"_time": "100", "host": "A", "count": "1"},
        {"_time": "300", "host": "A", "count": "3", "bytes": "512"},
    ]
    result = fill(records, ["host"], span=100)

    gap = [r for r in result.records if r["_time"] == "200"][0]
    assert gap["count"] == "0"
    assert gap["bytes"] == "0"


def test_fill_extends_to_an_explicit_range():
    records = [_record(200, "A", "x", 1)]
    result = fill(records, ["host"], span=100, range_start=0, range_end=400)

    times = sorted({r["_time"] for r in result.records}, key=float)
    assert times == ["0", "100", "200", "300", "400"]


def test_fill_respects_the_bucket_ceiling():
    records = [_record(0, "A", "x", 1), _record(1000000, "A", "x", 1)]
    with pytest.raises(FillContinuousError):
        fill(records, ["host"], span=1, max_buckets=1000)


def test_fill_default_bucket_ceiling_is_exposed():
    assert DEFAULT_MAX_BUCKETS > 0


def test_fill_treats_none_options_as_defaults():
    # An unset search-command option arrives as None rather than being omitted,
    # and must not blow up with a bare TypeError deep in the grid builder.
    records = [_record(100, "A", "x", 1), _record(300, "A", "x", 3)]
    result = fill(records, ["host"], span=100, fillvalue=None, max_buckets=None)

    gap = [r for r in result.records if r["_time"] == "200"][0]
    assert gap["count"] == "0"


def test_build_grid_treats_none_max_buckets_as_the_default():
    assert build_grid([0, 300], 100, max_buckets=None) == [0, 100, 200, 300]


# ---------------------------------------------------------------------------
# resource limits
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("value", ["inf", "-inf", "nan", "1e400", "Infinity"])
def test_fill_rejects_non_finite_timestamps(value):
    # An infinite timestamp makes the gap to the next bucket infinite, so the
    # grid builder spins until the bucket guard trips; nan compares false
    # against everything and would become a bucket of its own. Both are treated
    # as unparseable, so the row passes through rather than being dropped.
    records = [
        _record(100, "A", "x", 1),
        _record(200, "A", "x", 2),
        {"_time": value, "host": "A", "sourcetype": "x", "count": "9"},
    ]
    result = fill(records, ["host"], span=100)

    assert result.skipped_count == 1
    assert result.bucket_count == 2


def test_fill_caps_the_row_product_not_just_the_bucket_count():
    # 400 series over 201 buckets is 80400 rows from 401 inputs. The grid alone
    # is far inside its limit, so bounding buckets does not bound the output.
    records = [
        {"_time": "0", "host": "h%d" % index, "count": "1"} for index in range(400)
    ]
    records.append({"_time": str(200 * 3600), "host": "h0", "count": "1"})

    with pytest.raises(FillContinuousError) as excinfo:
        fill(records, ["host"], span=3600.0, max_rows=10000)

    message = str(excinfo.value)
    assert "80400 rows" in message
    assert "400 series" in message


def test_fill_allows_a_product_within_the_row_limit():
    records = [
        {"_time": "0", "host": "h%d" % index, "count": "1"} for index in range(4)
    ]
    records.append({"_time": "300", "host": "h0", "count": "1"})

    result = fill(records, ["host"], span=100.0, max_rows=1000)
    assert len(result.records) == 4 * 4      # 4 buckets x 4 series


def test_fill_treats_none_max_rows_as_the_default():
    records = [_record(100, "A", "x", 1), _record(300, "A", "x", 3)]
    assert fill(records, ["host"], span=100, max_rows=None).bucket_count == 3
