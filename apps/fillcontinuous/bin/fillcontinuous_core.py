# coding=utf-8
#
# Copyright 2026 MaximumPigs - https://github.com/maximumpigs
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not
# use this file except in compliance with the License. You may obtain a copy of
# the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under
# the License.

"""Gap filling for time-binned Splunk results, independent of splunklib.

``timechart`` and ``makecontinuous`` both densify a sparse time series, but only
across a single split-by field. With more than one group-by field the same
``_time`` legitimately recurs once per field combination, and ``makecontinuous``
rejects that input as having duplicate ``_time`` values. This module does the
same job keyed on the whole tuple of group-by fields.

The bucket grid is anchored on the timestamps actually present in the data:
synthetic buckets are only inserted *between* consecutive observed times, never
computed from a fabricated origin. That keeps generated rows aligned with
whatever binning produced the input, including day and week boundaries that are
not a constant number of seconds apart across a daylight-saving transition.

Nothing here imports splunklib, so the logic is unit testable without a Splunk
install or the vendored SDK on sys.path.
"""

import collections
import re

__all__ = [
    "DEFAULT_MAX_BUCKETS",
    "FillContinuousError",
    "FillResult",
    "build_grid",
    "fill",
    "infer_span",
    "parse_span",
]

# A grid this large is nearly always a mistaken span rather than an intended
# search, and the row count is this multiplied by the number of series.
DEFAULT_MAX_BUCKETS = 100000

_SPAN_PATTERN = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*([a-zA-Z]*)\s*$")

# Fixed-width units only. Splunk reads a bare "m" as minutes and "mon" as
# months, so the two must not be conflated.
_UNIT_SECONDS = {
    "": 1,
    "ms": 0.001,
    "cs": 0.01,
    "ds": 0.1,
    "s": 1, "sec": 1, "secs": 1, "second": 1, "seconds": 1,
    "m": 60, "min": 60, "mins": 60, "minute": 60, "minutes": 60,
    "h": 3600, "hr": 3600, "hrs": 3600, "hour": 3600, "hours": 3600,
    "d": 86400, "day": 86400, "days": 86400,
    "w": 604800, "week": 604800, "weeks": 604800,
}

# Rejected rather than approximated: a month and a year have no constant length,
# so stepping them as a fixed number of seconds would drift out of alignment
# with Splunk's own calendar binning and silently produce wrong buckets.
# Dimensionless slack for a bucket count, as opposed to the tolerance used when
# comparing timestamps. Keeps an exact multiple such as 300/100 from flooring to
# 2 because the division landed on 2.9999999996.
_QUOTIENT_EPSILON = 1e-9

_CALENDAR_UNITS = frozenset([
    "mon", "month", "months",
    "q", "qtr", "qtrs", "quarter", "quarters",
    "y", "yr", "yrs", "year", "years",
])

FillResult = collections.namedtuple(
    "FillResult",
    ["records", "span", "bucket_count", "series_count", "filled_count", "skipped_count"],
)


class FillContinuousError(ValueError):
    """A user-facing configuration or input error, safe to show in SPL."""


def parse_span(text):
    """Return ``text`` as a span in seconds.

    Raises FillContinuousError for calendar units and unparseable input.
    """
    if text is None:
        raise FillContinuousError("A span is required but none was given.")

    match = _SPAN_PATTERN.match(str(text))
    if match is None:
        raise FillContinuousError(
            "Could not read span '%s'. Use a number followed by a unit, "
            "for example 30s, 5m, 1h or 1d." % (text,)
        )

    magnitude, unit = match.group(1), match.group(2).lower()

    if unit in _CALENDAR_UNITS:
        raise FillContinuousError(
            "Span '%s' uses a calendar unit. fillcontinuous supports fixed-width "
            "spans only (ms, cs, ds, s, m, h, d, w), because months, quarters and "
            "years have no constant length and stepping them as seconds would "
            "misalign the generated buckets against Splunk's calendar binning." % (text,)
        )

    if unit not in _UNIT_SECONDS:
        raise FillContinuousError(
            "Unknown span unit '%s' in '%s'. Supported units are ms, cs, ds, s, "
            "m (minutes), h, d and w." % (unit, text)
        )

    seconds = float(magnitude) * _UNIT_SECONDS[unit]
    if seconds <= 0:
        raise FillContinuousError("Span '%s' must be greater than zero." % (text,))
    return seconds


def infer_span(times):
    """Guess the bucket width from the gaps between distinct timestamps.

    Returns the most common positive difference, or None when there are fewer
    than two distinct timestamps to compare.
    """
    ordered = sorted(set(times))
    if len(ordered) < 2:
        return None

    counts = {}
    for earlier, later in zip(ordered, ordered[1:]):
        delta = round(later - earlier, 6)
        if delta > 0:
            counts[delta] = counts.get(delta, 0) + 1

    if not counts:
        return None

    # Most frequent difference wins. Ties break toward the smaller span so that
    # data with many long gaps is still filled at the finer resolution.
    return max(counts.items(), key=lambda item: (item[1], -item[0]))[0]


def build_grid(times, span, range_start=None, range_end=None,
               max_buckets=DEFAULT_MAX_BUCKETS):
    """Return the ordered bucket timestamps covering ``times``.

    Every observed timestamp is preserved exactly. Synthetic buckets are added
    into interior gaps, and beyond the observed range only as far as
    ``range_start`` and ``range_end`` ask for.
    """
    ordered = sorted(set(times))
    if not ordered:
        return []

    if max_buckets is None:
        max_buckets = DEFAULT_MAX_BUCKETS

    # Floating point spans (sub-second, or a fractional inferred span) make
    # exact comparison unsafe; everything within this slack counts as equal.
    tolerance = span * 1e-6
    grid = []

    def guard():
        if len(grid) > max_buckets:
            raise FillContinuousError(
                "Filling this range at span=%s would need more than %d time "
                "buckets. Widen the span, narrow the time range, or raise "
                "maxbuckets." % (_format_number(span), max_buckets)
            )

    first, last = ordered[0], ordered[-1]

    if range_start is not None and range_start < first - tolerance:
        # How many whole spans fit between range_start and the first real
        # bucket. range() stays lazy, so a wildly distant range_start trips the
        # bucket guard rather than allocating.
        steps = int((first - range_start) / span + _QUOTIENT_EPSILON)
        for step in range(steps, 0, -1):
            grid.append(first - step * span)
            guard()

    grid.append(first)
    for earlier, later in zip(ordered, ordered[1:]):
        step = 1
        # Multiply from the anchor rather than accumulating, so a long run of
        # synthetic buckets cannot drift by repeated float addition.
        while earlier + step * span < later - tolerance:
            grid.append(earlier + step * span)
            guard()
            step += 1
        grid.append(later)
        guard()

    if range_end is not None and range_end > last + tolerance:
        step = 1
        while last + step * span <= range_end + tolerance:
            grid.append(last + step * span)
            guard()
            step += 1

    return grid


def fill(records, group_fields, span=None, fillvalue="0", range_start=None,
         range_end=None, marker_field=None, max_buckets=DEFAULT_MAX_BUCKETS):
    """Densify ``records`` so every series has a row in every time bucket.

    ``records`` is any iterable of mappings, as delivered by a search command.
    ``group_fields`` names the fields whose combined values identify a series.
    Records without a numeric ``_time`` are passed through untouched rather than
    dropped, so nothing is silently lost.
    """
    if span is not None and span <= 0:
        raise FillContinuousError("Span must be greater than zero.")

    # Callers may hand through unset command options rather than omitting the
    # argument, so None means "use the default" rather than being an error.
    if fillvalue is None:
        fillvalue = "0"
    if max_buckets is None:
        max_buckets = DEFAULT_MAX_BUCKETS

    originals = []
    passthrough = []
    observed_times = set()
    occupied = set()
    series_order = []
    series_seen = set()
    value_fields = []
    value_seen = set()
    span_field_present = False

    group_fields = list(group_fields)
    group_lookup = set(group_fields)

    for record in records:
        moment = _to_epoch(record.get("_time"))
        if moment is None:
            passthrough.append(record)
            continue

        key = tuple(record.get(field) for field in group_fields)
        if key not in series_seen:
            series_seen.add(key)
            series_order.append(key)

        observed_times.add(moment)
        occupied.add((key, _quantise(moment)))
        originals.append((moment, key, record))

        for field in record:
            if field == "_span":
                span_field_present = True
            elif field == "_time" or field in group_lookup:
                continue
            elif field.startswith("_"):
                # Other internal fields carry no meaningful zero, so they are
                # left off synthetic rows rather than invented.
                continue
            elif field not in value_seen:
                value_seen.add(field)
                value_fields.append(field)

    if not originals:
        return FillResult(list(passthrough), span, 0, 0, 0, len(passthrough))

    if span is None:
        span = infer_span(observed_times)
        if span is None:
            raise FillContinuousError(
                "Cannot infer a span from a single time bucket. Pass span "
                "explicitly, for example: fillcontinuous span=1h by host"
            )

    grid = build_grid(
        observed_times, span, range_start=range_start, range_end=range_end,
        max_buckets=max_buckets,
    )

    span_text = _format_number(span)
    output = []

    for moment, key, record in originals:
        if marker_field:
            record = dict(record)
            record[marker_field] = "0"
        output.append((moment, _sortable(key), record))

    filled_count = 0
    for key in series_order:
        for bucket in grid:
            if (key, _quantise(bucket)) in occupied:
                continue
            synthetic = {"_time": _format_time(bucket)}
            for field, value in zip(group_fields, key):
                # A field that was absent on the real rows stays absent, rather
                # than being invented as an empty string.
                if value is not None:
                    synthetic[field] = value
            for field in value_fields:
                synthetic[field] = fillvalue
            if span_field_present:
                synthetic["_span"] = span_text
            if marker_field:
                synthetic[marker_field] = "1"
            output.append((bucket, _sortable(key), synthetic))
            filled_count += 1

    # Matches the ordering of `stats by _time, ...`, which is what the input
    # almost always is, so the command does not reshuffle a caller's results.
    output.sort(key=lambda item: (item[0], item[1]))

    ordered_records = [item[2] for item in output]
    ordered_records.extend(passthrough)

    return FillResult(
        records=ordered_records,
        span=span,
        bucket_count=len(grid),
        series_count=len(series_order),
        filled_count=filled_count,
        skipped_count=len(passthrough),
    )


def _to_epoch(value):
    """Return ``value`` as a float epoch, or None when it is not numeric."""
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _quantise(moment):
    """Bucket identity key, rounded so float noise cannot split one bucket."""
    return round(moment, 6)


def _sortable(key):
    """Sort key for a series tuple, since None and str do not compare."""
    return tuple("" if value is None else str(value) for value in key)


def _format_time(moment):
    """Render an epoch the way Splunk writes ``_time``."""
    return _format_number(moment)


def _format_number(value):
    if float(value).is_integer():
        return str(int(value))
    return repr(round(float(value), 6))
