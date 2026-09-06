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

"""The fillcontinuous custom search command.

A thin splunklib wrapper: all of the gap-filling logic lives in
fillcontinuous_core, which imports nothing from splunklib so it can be unit
tested without Splunk.

Must remain valid on Python 3.9 as well as 3.13 - see python.required in
default/commands.conf. No match statements, no "X | Y" annotations.
"""

import os
import sys

# The vendored SDK ships in the app's lib/ directory. Splunk does not provide
# splunklib to apps, so this path has to be set up before splunklib is imported.
sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib")
)

from splunklib.searchcommands import (  # noqa: E402  (must follow the sys.path setup)
    Configuration,
    EventingCommand,
    Option,
    dispatch,
    validators,
)

from fillcontinuous_core import (  # noqa: E402
    DEFAULT_MAX_BUCKETS,
    DEFAULT_MAX_ROWS,
    FillContinuousError,
    fill,
    parse_span,
)


@Configuration()
class FillContinuousCommand(EventingCommand):
    """Adds a row for every missing combination of time bucket and group values.

    ##Syntax

    .. code-block::
        fillcontinuous [span=<span>] [fillvalue=<string>] [marker=<field>]
                       [start=<epoch>] [end=<epoch>] [maxbuckets=<int>]
                       [by] <field>, ...

    ##Description

    `timechart` zero-fills gaps only for a single split-by field.
    `makecontinuous` fills along one dimension and knows nothing of group-by
    fields, so on the output of `stats by _time, a, b` it silently inserts a
    single valueless row per missing bucket instead of one row per series. This
    command fills those gaps keyed on the whole tuple of group-by fields.

    ##Example

    .. code-block::
        index=web | bin _time span=1h | stats count by _time, host, sourcetype
            | fillcontinuous span=1h by host, sourcetype
    """

    span = Option(
        doc="""**Syntax:** **span=***<span>*
        **Description:** Bucket width, using fixed-width units only (ms, cs, ds,
        s, m for minutes, h, d, w). Inferred from the most common gap between
        buckets when omitted.""",
        require=False,
    )

    fillvalue = Option(
        doc="""**Syntax:** **fillvalue=***<string>*
        **Description:** Value given to every aggregate field on a synthesised
        row. Defaults to 0.""",
        require=False,
        default="0",
    )

    marker = Option(
        doc="""**Syntax:** **marker=***<field>*
        **Description:** Name of a field to add, set to 1 on synthesised rows
        and 0 on real ones.""",
        require=False,
        validate=validators.Fieldname(),
    )

    start = Option(
        doc="""**Syntax:** **start=***<epoch>*
        **Description:** Epoch seconds. Extends the grid backwards, for leading
        buckets that contain no events at all.""",
        require=False,
        validate=validators.Float(),
    )

    end = Option(
        doc="""**Syntax:** **end=***<epoch>*
        **Description:** Epoch seconds. Extends the grid forwards.""",
        require=False,
        validate=validators.Float(),
    )

    # Both ceilings are capped at their default, so a search can lower them but
    # never raise them. Without a maximum, maxbuckets=1000000000 would switch
    # the protection off entirely, which on a shared search head lets one search
    # exhaust memory for everyone.
    maxbuckets = Option(
        doc="""**Syntax:** **maxbuckets=***<int>*
        **Description:** Ceiling on the number of time buckets, guarding against
        a mistaken span producing an unbounded grid. Defaults to, and cannot
        exceed, 100000.""",
        require=False,
        default=DEFAULT_MAX_BUCKETS,
        validate=validators.Integer(minimum=1, maximum=DEFAULT_MAX_BUCKETS),
    )

    maxrows = Option(
        doc="""**Syntax:** **maxrows=***<int>*
        **Description:** Ceiling on the rows produced, which is buckets
        multiplied by series. Guards against a high-cardinality group-by
        amplifying a small result set. Defaults to, and cannot exceed,
        1000000.""",
        require=False,
        default=DEFAULT_MAX_ROWS,
        validate=validators.Integer(minimum=1, maximum=DEFAULT_MAX_ROWS),
    )

    by = Option(
        doc="""**Syntax:** **by=***<field-list>*
        **Description:** Comma-separated group-by fields. The bare form,
        `fillcontinuous span=1h by host, sourcetype`, is equivalent.""",
        require=False,
        validate=validators.List(validators.Fieldname()),
    )

    def __init__(self):
        super(FillContinuousCommand, self).__init__()
        # transform() is called once per protocol chunk, but the bucket grid can
        # only be worked out once every row has been seen, so rows accumulate
        # here and are emitted on the final chunk.
        self._buffered = []
        self._span_seconds = None
        self._group_fields = []

    def _fail(self, message):
        """Report a fatal, user-facing error and stop.

        Goes through write_error rather than error_exit so the text can be
        passed as a format argument. splunklib renders messages with
        str.format, so text interpolated into the template - a span the user
        typed, say - would raise on any brace it contained.
        """
        self.write_error("{}", message)
        self.logger.error("fillcontinuous aborted: %s", message)
        sys.exit(1)

    def prepare(self):
        """Validate options during getinfo, before any data flows."""
        self._group_fields = self._resolve_group_fields()

        if not self._group_fields:
            self._fail(
                "fillcontinuous needs at least one group-by field, for example: "
                "fillcontinuous span=1h by host, sourcetype"
            )

        if self.span is not None:
            try:
                self._span_seconds = parse_span(self.span)
            except FillContinuousError as error:
                self._fail(str(error))

    def transform(self, records):
        self._buffered.extend(records)

        # _finished is set from each chunk's metadata before transform runs. It
        # is None under the v1 protocol, which this command never uses because
        # commands.conf sets chunked = true; treat that as "go" rather than
        # silently swallowing every row.
        if getattr(self, "_finished", None) is False:
            return

        try:
            result = fill(
                self._buffered,
                self._group_fields,
                span=self._span_seconds,
                fillvalue=self.fillvalue,
                range_start=self.start,
                range_end=self.end,
                marker_field=self.marker,
                max_buckets=self.maxbuckets,
                max_rows=self.maxrows,
            )
        except FillContinuousError as error:
            self.write_error("{}", str(error))
            return
        finally:
            self._buffered = []

        # Placeholders are {}, not %s: splunklib renders these with str.format.
        if result.skipped_count:
            self.write_warning(
                "fillcontinuous passed through {} row(s) with no numeric _time; "
                "run bin or stats before this command so results are bucketed.",
                result.skipped_count,
            )

        if result.bucket_count:
            self.write_info(
                "fillcontinuous added {} row(s) across {} bucket(s) and {} series.",
                result.filled_count,
                result.bucket_count,
                result.series_count,
            )

        for record in result.records:
            yield record

    def _resolve_group_fields(self):
        """Collect group-by fields from the by= option and the bare field list."""
        names = []

        def add(token):
            for part in str(token).split(","):
                part = part.strip()
                if part and part not in names:
                    names.append(part)

        if self.by:
            for token in self.by:
                add(token)

        tokens = list(self.fieldnames or [])
        # SPL reads better with the `by` keyword, but the SDK hands it over as
        # just another bare word, so drop a leading one.
        if tokens and tokens[0].strip().lower() == "by":
            tokens = tokens[1:]
        for token in tokens:
            add(token)

        # Grouping by _time would make every row its own series and fill
        # nothing, which is a confusing no-op rather than an obvious error.
        if "_time" in names:
            names.remove("_time")
            self.write_warning(
                "fillcontinuous ignored _time in the group-by list; it is always "
                "the bucket axis."
            )

        return names


dispatch(FillContinuousCommand, sys.argv, sys.stdin, sys.stdout, __name__)
