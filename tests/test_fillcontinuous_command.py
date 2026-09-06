"""Integration tests for the splunklib wrapper around the gap-filling core.

These exercise the parts the pure-core tests cannot reach: option defaults, the
by-clause parsing splunklib hands over as bare words, and the cross-chunk
buffering that a command needing the whole result set depends on.

They require the vendored splunklib under apps/fillcontinuous/lib/, which the
module under test puts on sys.path itself.
"""

import pytest

fillcontinuous = pytest.importorskip(
    "fillcontinuous",
    reason="vendored splunklib is missing; run scripts/vendor_splunklib.py",
)


@pytest.fixture
def command():
    """A command instance set up the way SearchCommand.process would."""
    instance = fillcontinuous.FillContinuousCommand()

    # process() calls options.reset() to apply declared defaults before parsing
    # arguments. These tests bypass process(), so they do it explicitly.
    instance.options.reset()

    # write_* go through the record writer, which only exists once process()
    # has run, so collect the messages instead.
    instance.messages = []
    instance.write_info = lambda m, *a: instance.messages.append(("INFO", m % a if a else m))
    instance.write_warning = lambda m, *a: instance.messages.append(("WARN", m % a if a else m))
    instance.write_error = lambda m, *a: instance.messages.append(("ERROR", m % a if a else m))

    return instance


def test_module_declares_an_eventing_command(command):
    # An eventing command receives the whole result set at the search head,
    # which is what gap filling needs. A streaming type would see fragments.
    assert command.configuration.type == "events"


def test_option_defaults_are_applied(command):
    assert command.fillvalue == "0"
    assert command.maxbuckets == fillcontinuous.DEFAULT_MAX_BUCKETS
    assert command.marker is None
    assert command.span is None


def test_by_keyword_and_commas_are_stripped_from_the_field_list(command):
    # splunklib delivers `by host, sourcetype` as bare words, keeping the
    # keyword and whatever commas survived tokenising.
    command.fieldnames = ["by", "host,", "sourcetype"]
    assert command._resolve_group_fields() == ["host", "sourcetype"]


def test_fields_may_arrive_as_one_comma_joined_token(command):
    command.fieldnames = ["host,sourcetype"]
    assert command._resolve_group_fields() == ["host", "sourcetype"]


def test_by_option_and_bare_fields_are_merged_without_duplicates(command):
    command.by = ["host"]
    command.fieldnames = ["host", "sourcetype"]
    assert command._resolve_group_fields() == ["host", "sourcetype"]


def test_grouping_by_time_is_dropped_with_a_warning(command):
    command.fieldnames = ["_time", "host"]
    assert command._resolve_group_fields() == ["host"]
    assert any(level == "WARN" for level, _ in command.messages)


def test_prepare_rejects_a_calendar_span(command):
    command.fieldnames = ["host"]
    command.span = "1mon"

    # error_exit writes the message and terminates the command.
    with pytest.raises(SystemExit):
        command.prepare()


def test_prepare_accepts_a_fixed_width_span(command):
    command.fieldnames = ["host"]
    command.span = "1h"
    command.prepare()
    assert command._span_seconds == 3600.0


def test_transform_buffers_until_the_final_chunk(command):
    command.fieldnames = ["by", "host", "sourcetype"]
    command.span = "1h"
    command.prepare()

    first_chunk = [
        {"_time": "0", "host": "A", "sourcetype": "x", "count": "1"},
        {"_time": "0", "host": "B", "sourcetype": "y", "count": "2"},
    ]
    later_chunk = [
        {"_time": "7200", "host": "A", "sourcetype": "x", "count": "3"},
    ]

    # _execute_v2 sets _finished from each chunk's metadata before calling
    # transform. Anything emitted before the last chunk would be filled against
    # an incomplete picture of the data.
    command._finished = False
    assert list(command.transform(iter(first_chunk))) == []

    command._finished = True
    emitted = list(command.transform(iter(later_chunk)))

    # Three hourly buckets (0, 3600, 7200) across two series.
    assert len(emitted) == 6

    times = sorted({record["_time"] for record in emitted}, key=float)
    assert times == ["0", "3600", "7200"]

    gap = [r for r in emitted if r["_time"] == "3600" and r["host"] == "A"][0]
    assert gap == {"_time": "3600", "host": "A", "sourcetype": "x", "count": "0"}


def test_transform_treats_a_missing_finished_flag_as_final(command):
    # Under the v1 protocol _finished is never set. The command declares
    # chunked = true so that should not happen, but swallowing every row would
    # be a silent, baffling failure if it ever did.
    command.fieldnames = ["host"]
    command.span = "1h"
    command.prepare()

    rows = [{"_time": "0", "host": "A", "count": "1"}]
    assert len(list(command.transform(iter(rows)))) == 1


def test_transform_reports_a_bad_span_as_an_error_not_a_crash(command):
    command.fieldnames = ["host"]
    command.prepare()

    # A single bucket gives nothing to infer a span from.
    command._finished = True
    assert list(command.transform(iter([{"_time": "0", "host": "A"}]))) == []
    assert any(level == "ERROR" for level, _ in command.messages)


def test_transform_clears_its_buffer_between_runs(command):
    command.fieldnames = ["host"]
    command.span = "1h"
    command.prepare()

    command._finished = True
    list(command.transform(iter([{"_time": "0", "host": "A", "count": "1"}])))
    assert command._buffered == []
