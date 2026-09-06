# fillcontinuous - Splunkbase listing

Copy each section below into the matching field on the Splunkbase upload form.
See ../README.md for the field mapping and why this lives outside apps/.

Deliberately ASCII only. This text gets pasted into a third-party web form, and
non-ASCII punctuation is one encoding round-trip away from turning into
mojibake. Keep it that way: use "-" rather than an em dash, and straight quotes.

Last reviewed against app version 1.1.1.

===============================================================================
APP NAME
===============================================================================

MaximumPigs fillcontinuous Add-on

This exact string must also appear as [ui] label in default/app.conf and as
info.title in app.manifest. Splunkbase requires the listing name to correspond
to the label shown in the Splunk user interface.

It follows the required Splunkbase pattern:

    (Company | Brand | Author) [solution name] (App | Add-on | Connector)

so the author comes first, not the solution, and the Add-on suffix is
mandatory. "Add-on" rather than "App" because this ships no views. There is no
"for <technology>" suffix, since that form is only for interoperating with a
third-party product.

Note this is the display name, not the app ID. The ID and directory name stay
"fillcontinuous".


===============================================================================
SUMMARY
===============================================================================

Fills missing time buckets across any number of group-by fields - the gap
filling that timechart and makecontinuous cannot do.


===============================================================================
SHORT DESCRIPTION
===============================================================================

Adds a row for every missing combination of time bucket and group-by values,
turning a sparse "stats count by _time, host, sourcetype" into a complete grid
with 0, or a value you choose, in the gaps. Every series stays continuous, so
charts stop showing false drops to zero and averages stop being computed over
only the buckets that happen to exist.

It does this across any number of group-by fields at once: timechart zero-fills
only a single split-by field, and makecontinuous fills one dimension while
ignoring group-by fields entirely.


===============================================================================
DETAILS
===============================================================================

THE PROBLEM

timechart gives you gap filling for free, but only across one split-by field,
because it pivots that field into one column per value:

    index=web | timechart span=1h count by host

Add a second dimension and that stops working. The usual fallback produces a
sparse table, where rows simply do not exist for buckets in which nothing
happened:

    index=web
    | bin _time span=1h
    | stats count by _time, host, sourcetype

makecontinuous is the built-in for densifying a series, but it cannot help
here either. It fills along a single dimension and has no concept of group-by
fields, so it does not know that one timestamp should now produce one row per
group.

The dangerous part is that it does not complain. Given those three sparse rows,
"| makecontinuous _time span=1h" returns:

    _time         host     count
    1767225600    web01    5
    1767225600    web02    3
    1767229200    (none)   (none)
    1767232800    web01    7

It inserted one row for the missing hour, belonging to no host, rather than one
row for each of the two hosts, and web02 is still missing its 1767232800 bucket
entirely. Four rows where the answer is six. Chart that and you get a phantom
hostless series alongside a gap that only half closed.

The other common workaround, concatenating fields into one synthetic series
with eval and feeding that to timechart, does work, but it collapses the fields
into a string you then have to pull apart again, and it runs into timechart's
series limits.


THE COMMAND

    index=web
    | bin _time span=1h
    | stats count by _time, host, sourcetype
    | fillcontinuous span=1h by host, sourcetype

Every combination of time bucket and observed host/sourcetype pair now has a
row. Missing ones get count=0.

"fillgaps" is registered as an alias, so "| fillgaps span=1h by host,
sourcetype" does exactly the same thing.


SYNTAX

    fillcontinuous [span=<span>] [fillvalue=<string>] [marker=<field>]
                   [start=<epoch>] [end=<epoch>]
                   [maxbuckets=<int>] [maxrows=<int>]
                   [by] <field>, ...

    span        Bucket width. Fixed-width units only: ms, cs, ds, s,
                m (minutes), h, d, w. When omitted, the most common gap
                between buckets is used.
    fillvalue   Value given to every aggregate field on a synthesised row.
                Defaults to 0.
    marker      Name of a field to add, set to 1 on synthesised rows and 0 on
                real ones. Useful for auditing what the command added.
    start, end  Epoch seconds. Extend the grid beyond the observed data, for
                leading or trailing buckets containing no events at all.
    maxbuckets  Ceiling on the number of time buckets. Default and maximum
                100000.
    maxrows     Ceiling on rows produced, which is buckets multiplied by
                series. Default and maximum 1000000.

The "by" keyword is optional, and field lists may be separated by commas or
spaces.


WHAT COUNTS AS A SERIES

Only combinations that appear at least once in the results are filled, matching
timechart's behaviour of creating a column only for values it actually saw. A
host/sourcetype pair that never occurs is not invented, so the output does not
expand into the full cross product of every field's distinct values.


HOW THE BUCKET GRID IS BUILT

The grid is anchored on the timestamps actually present in your results.
Synthetic buckets are only inserted between consecutive observed times, never
computed from a fabricated origin.

This matters more than it sounds. Splunk bins d and w spans in the server's
local timezone, so the day containing a daylight-saving transition is 23 or 25
hours long, not 24. A grid generated by stepping 86400 seconds from a start
time would drift an hour out after that transition and stop lining up with the
real rows, duplicating some buckets and orphaning others. Anchoring on observed
timestamps avoids the problem entirely: real rows are never moved, and the gaps
either side of an irregular boundary are still filled.

Calendar spans (1mon, 1q, 1y) are rejected with a clear error rather than
approximated as a fixed number of seconds, for the same reason. Use bin for
calendar binning and fill at a fixed span, or aggregate after filling.


EXAMPLES

Flag which rows were manufactured, inferring the span:

    index=web
    | bin _time span=5m
    | stats sum(bytes) as bytes by _time, host, status
    | fillcontinuous marker=was_filled by host, status

Fill with something other than zero, for a gauge where zero would be a lie:

    ... | fillcontinuous span=1m fillvalue="" by host, metric_name

Cover the whole search window, including leading and trailing buckets in which
nothing at all was logged:

    index=web
    | bin _time span=1h
    | stats count by _time, host, sourcetype
    | fillcontinuous span=1h start=1767225600 end=1767312000 by host, sourcetype


BEHAVIOUR WORTH KNOWING

- Rows without a numeric _time are passed through unchanged, not dropped, and
  the command warns how many. Nothing is silently lost.
- Duplicate rows are preserved. The command never deduplicates real data; it
  only adds rows where a (series, bucket) pair is absent.
- A group-by field absent on the real rows stays absent on synthesised ones,
  rather than being invented as an empty string.
- Aggregate fields are collected across all rows, so a field appearing on only
  some rows still gets a fill value everywhere and the result set has
  consistent columns.
- _span is carried through when the input has it. Other internal fields are
  omitted from synthesised rows, since there is no meaningful zero for them.
- Output is ordered by _time, then by the group-by values, matching the
  ordering of the "stats by _time, ..." that almost always precedes it.


RESOURCE LIMITS

Output is buckets multiplied by series, and the series count comes from your
data, so bounding the grid alone does not bound the result: a few hundred rows
spread over a few hundred high-cardinality values amplifies into millions. The
command checks the product before materialising anything and refuses with a
message naming both factors.

Both ceilings are capped at their defaults and can only be lowered, so a single
search cannot disable the protection on a shared search head.


COMPATIBILITY

- Splunk Enterprise 9.x and 10.x, and Splunk Cloud Platform.
- Runs on Python 3.9 (Splunk's LTS runtime and the fallback on 10.2+) and on
  Python 3.13 (the opt-in runtime from 10.2). commands.conf declares both
  python.version and python.required accordingly.
- Search head only. The app collects no data, opens no network connections,
  reads and writes no files, and never accesses the session key.
- Licensed under Apache 2.0.


===============================================================================
INSTALLATION
===============================================================================

Install on search heads only. No indexer or forwarder installation is needed,
and no configuration is required after install.

SPLUNK CLOUD

Install from Splunkbase through the Splunk Cloud UI, or request installation
through Splunk Support if self-service install is not enabled for your stack.

SPLUNK ENTERPRISE, SINGLE SEARCH HEAD

1. In Splunk Web, go to Apps > Manage Apps > Install app from file.
2. Upload the .spl file and click Upload.
3. Restart Splunk when prompted. The restart is required before a new custom
   search command is registered.

Alternatively, unpack the archive into $SPLUNK_HOME/etc/apps/ and restart:

    tar -xvzf fillcontinuous-<version>.spl -C $SPLUNK_HOME/etc/apps/
    $SPLUNK_HOME/bin/splunk restart

SEARCH HEAD CLUSTER

Deploy through the deployer in the usual way:

1. Place the unpacked app in $SPLUNK_HOME/etc/shcluster/apps/ on the deployer.
2. Run:

       $SPLUNK_HOME/bin/splunk apply shcluster-bundle -target <member-uri>

VERIFYING THE INSTALL

Run this search. It needs no indexed data and should return exactly six rows,
three time buckets across two series, with count=0 in the three filled ones:

    | makeresults count=3
    | streamstats count as row
    | eval _time=case(row=1,1767225600, row=2,1767225600, row=3,1767232800),
           host=case(row=1,"web01", row=2,"web02", row=3,"web01"),
           sourcetype="access",
           count=case(row=1,5, row=2,3, row=3,7)
    | fields _time host sourcetype count
    | fillcontinuous span=1h by host, sourcetype

UPGRADING

Install the new version over the old one and restart. There are no saved
searches, lookups or configuration to migrate.


===============================================================================
TROUBLESHOOTING
===============================================================================

"Unknown search command 'fillcontinuous'"

  The command has not been registered. Restart Splunk, which is required after
  installing an app that adds a custom search command. On a search head
  cluster, confirm the bundle was applied to every member. Also check the app
  is enabled under Apps > Manage Apps.

Nothing is filled, and the result looks identical to the input

  The span was probably inferred larger than you expected. Span inference needs
  at least three distinct timestamps: with only two, the single observed gap
  becomes the span and there is nothing to fill. Pass span explicitly.

  Also confirm the results really are sparse. If a series has a row in every
  bucket already, there is nothing to add.

"fillcontinuous needs at least one group-by field"

  The command was run without a by clause. It fills per series, so it needs to
  know which fields identify a series:

      | fillcontinuous span=1h by host, sourcetype

"Span '1mon' uses a calendar unit"

  Calendar spans are rejected rather than approximated, because months,
  quarters and years have no constant length and stepping them as seconds
  would misalign the buckets against Splunk's own calendar binning. Use a
  fixed-width span (s, m, h, d, w), or bin by the calendar unit first and fill
  at a fixed span.

"Could not read span '...'"

  The span was not a number followed by a supported unit. Valid examples:
  30s, 5m, 1h, 12h, 1d, 1w.

"Filling N bucket(s) across M series would produce X rows, over the ... limit"

  The result would be too large to build in memory. The message names both
  factors, so you can see which one is the problem. Widen the span, narrow the
  time range, or group by fewer or lower-cardinality fields. Grouping by a
  high-cardinality field such as an IP address at a fine span is the usual
  cause. maxrows can be lowered but not raised.

"Filling this range at span=... would need more than N time buckets"

  The time range divided by the span is too large. This almost always means
  the span is smaller than intended.

"fillcontinuous passed through N row(s) with no numeric _time"

  Some rows had a _time that was missing, empty, non-numeric, or infinite.
  Those rows are passed through untouched rather than dropped. Run bin or
  stats before the command so results are bucketed, and check for an eval that
  reformatted _time into a string.

Results are correct but the chart still shows gaps

  Charting commands often need the results in a specific shape. After filling,
  pivot for display, for example with xyseries, or concatenate the group-by
  fields into a single series field for timechart-style rendering.

The command is not available from another app

  It is exported system-wide by default, so this usually indicates the export
  was changed locally. Check metadata/local.meta on the search head.

Errors mentioning Python or the interpreter

  The app requires Python 3 and declares support for 3.9 and 3.13. On Splunk
  10.2 and later the platform selects the highest available. If your
  deployment pins an unusual Python configuration, check
  $SPLUNK_HOME/var/log/splunk/splunkd.log for ChunkedExternProcessor errors.

Getting more detail

  Search command errors appear in the job inspector and in
  $SPLUNK_HOME/var/log/splunk/splunkd.log. The command writes an INFO message
  on every successful run stating how many rows it added, across how many
  buckets and series, which is a quick way to confirm it did what you expected.
