# fillcontinuous - Splunkbase listing

Copy each section below into the matching field on the Splunkbase upload form.
See ../README.md for the field mapping and why this lives outside apps/.

## Two rules for editing this file

**ASCII only.** No characters above U+007F. Use "-" not an em dash, and
straight quotes. This text is pasted into a third-party web form, so it
survives at least one encoding round-trip outside our control.

**Markdown in the long fields only.** APP NAME, SUMMARY and SHORT DESCRIPTION
are short single-line fields pasted as plain text; markup there would appear
literally. DETAILS, INSTALLATION and TROUBLESHOOTING are long-form fields and
take Markdown.

Keep angle brackets inside fenced code blocks, where they are literal. In
prose, wrap them in backticks so no renderer mistakes them for a tag.

Last reviewed against app version 1.1.1.


===============================================================================
APP NAME  (plain text)
===============================================================================

MaximumPigs fillcontinuous Add-on

This exact string must also appear as [ui] label in default/app.conf and as
info.title in app.manifest. Splunkbase requires the listing name to correspond
to the label shown in the Splunk user interface.

It follows the required Splunkbase pattern:

    (Company | Brand | Author) [solution name] (App | Add-on | Connector)

so the author comes first, and the Add-on suffix is mandatory. "Add-on" rather
than "App" because this ships no views. No "for [technology]" suffix, since
that form is only for interoperating with a third-party product.

This is the display name, not the app ID. The ID and directory stay
"fillcontinuous".


===============================================================================
SUMMARY  (plain text)
===============================================================================

Fills missing time buckets across any number of group-by fields - the gap
filling that timechart and makecontinuous cannot do.


===============================================================================
SHORT DESCRIPTION  (plain text)
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
DETAILS  (Markdown)
===============================================================================

**fillcontinuous** makes sparse time-series results dense. It adds a row for
every combination of time bucket and group-by values that is missing, so every
series has a value in every bucket.

### The problem

`timechart` zero-fills gaps for you, but only across a single split-by field.
Add a second dimension and you fall back to `stats`, which returns nothing at
all for buckets where nothing happened:

```
index=web
| bin _time span=1h
| stats count by _time, host, sourcetype
```

Those absent rows become false drops to zero on a chart, and averages computed
over only the buckets that happen to exist.

> **makecontinuous does not solve this.** It fills along one dimension and has
> no concept of group-by fields, so it inserts a single valueless row per
> missing bucket instead of one row per series - and it does not warn you. On
> the example above it returns four rows where the answer is six, including one
> row belonging to no host at all.

### The solution

```
index=web
| bin _time span=1h
| stats count by _time, host, sourcetype
| fillcontinuous span=1h by host, sourcetype
```

Every combination of time bucket and observed host/sourcetype pair now has a
row, with `count=0` in the ones that were missing. `fillgaps` is registered as
an alias if you prefer the shorter name.

### Syntax

```
fillcontinuous [span=<span>] [fillvalue=<string>] [marker=<field>]
               [start=<epoch>] [end=<epoch>]
               [maxbuckets=<int>] [maxrows=<int>]
               [by] <field>, ...
```

| Option | Default | Description |
| --- | --- | --- |
| `span` | inferred | Bucket width. Fixed-width units only: ms, cs, ds, s, m (minutes), h, d, w. |
| `fillvalue` | `0` | Value given to every aggregate field on an added row. |
| `marker` | none | Field to add, set to 1 on added rows and 0 on real ones. Useful for auditing what the command did. |
| `start`, `end` | none | Epoch seconds. Extend the grid beyond the observed data, for leading or trailing buckets containing no events at all. |
| `maxbuckets` | `100000` | Ceiling on time buckets. Can be lowered, not raised. |
| `maxrows` | `1000000` | Ceiling on rows produced, which is buckets multiplied by series. Can be lowered, not raised. |

The `by` keyword is optional, and field lists may be separated by commas or
spaces.

### Examples

**Flag which rows were added, letting the span be inferred**

```
index=web
| bin _time span=5m
| stats sum(bytes) as bytes by _time, host, status
| fillcontinuous marker=was_filled by host, status
```

**Fill with something other than zero, where zero would be a lie**

```
... | fillcontinuous span=1m fillvalue="" by host, metric_name
```

**Cover the whole window, including buckets with no events at all**

```
index=web
| bin _time span=1h
| stats count by _time, host, sourcetype
| fillcontinuous span=1h start=1767225600 end=1767312000 by host, sourcetype
```

### How it works

- **Only combinations that actually occur are filled.** A host/sourcetype pair
  that never appears is not invented, so the output does not expand into the
  full cross product of every field's values. This matches how timechart
  creates a column only for values it saw.
- **The bucket grid is anchored on the timestamps in your results**, with
  synthetic buckets inserted only between consecutive observed times - never
  computed from a fabricated origin. Real rows are therefore never moved,
  duplicated or misaligned.
- **Daylight saving is handled by that anchoring.** Splunk bins d and w spans
  in the server's local timezone, so the day containing a transition is 23 or
  25 hours, not 24. Stepping a fixed 86400 seconds from a start time would
  drift out of alignment after it; anchoring on observed timestamps cannot.
- **Calendar spans are rejected, not approximated.** `1mon`, `1q` and `1y`
  raise a clear error, because months and years have no constant length and
  stepping them as seconds would silently misalign the buckets.
- **Output is ordered by _time, then by the group-by values**, matching the
  ordering of the `stats by _time, ...` that almost always precedes it.

### Things worth knowing

- Rows without a usable numeric `_time` are passed through unchanged, not
  dropped, and the command tells you how many. Nothing is silently lost.
- Duplicate rows are preserved. Real data is never deduplicated; rows are only
  added where a series has no row in a bucket.
- A group-by field absent from the real rows stays absent on added rows, rather
  than being invented as an empty string.
- Aggregate fields are collected across all rows, so a field present on only
  some rows still gets a fill value everywhere and the columns stay consistent.
- Every successful run reports how many rows it added, across how many buckets
  and series.

### Resource limits

Output is buckets multiplied by series, and the series count comes from your
data - so a few hundred rows spread over a few hundred high-cardinality values
amplifies into millions. The command checks that product before building
anything and refuses with a message naming both factors. Both ceilings can be
lowered but never raised, so one search cannot disable the protection on a
shared search head.

### Compatibility

- Splunk Enterprise 9.x and 10.x, and Splunk Cloud Platform.
- Runs on Python 3.9 and Python 3.13.
- Search head only. No indexer or forwarder installation, and no configuration.
- Collects no data, opens no network connections, reads and writes no files.
- Licensed under Apache 2.0.


===============================================================================
INSTALLATION  (Markdown)
===============================================================================

Install on **search heads only**. No indexer or forwarder installation is
needed, and there is nothing to configure afterwards.

### Splunk Cloud

Install from Splunkbase through the Splunk Cloud UI, or request installation
through Splunk Support if self-service install is not enabled for your stack.

### Splunk Enterprise, single search head

1. Go to **Apps > Manage Apps > Install app from file**.
2. Upload the .spl file and click **Upload**.
3. Restart Splunk when prompted. A restart is required before a new custom
   search command is registered.

Or unpack it and restart:

```
tar -xvzf fillcontinuous-<version>.spl -C $SPLUNK_HOME/etc/apps/
$SPLUNK_HOME/bin/splunk restart
```

### Search head cluster

1. Place the unpacked app in `$SPLUNK_HOME/etc/shcluster/apps/` on the
   deployer.
2. Apply the bundle:

```
$SPLUNK_HOME/bin/splunk apply shcluster-bundle -target <member-uri>
```

### Verifying the install

This search needs no indexed data. It should return exactly six rows - three
time buckets across two series - with `count=0` in the three that were filled.

```
| makeresults count=3
| streamstats count as row
| eval _time=case(row=1,1767225600, row=2,1767225600, row=3,1767232800),
       host=case(row=1,"web01", row=2,"web02", row=3,"web01"),
       sourcetype="access",
       count=case(row=1,5, row=2,3, row=3,7)
| fields _time host sourcetype count
| fillcontinuous span=1h by host, sourcetype
```

### Upgrading

Install the new version over the old one and restart. There are no saved
searches, lookups or configuration to migrate.


===============================================================================
TROUBLESHOOTING  (Markdown)
===============================================================================

**"Unknown search command 'fillcontinuous'"**

The command has not been registered. Restart Splunk - this is required after
installing an app that adds a custom search command. On a search head cluster,
confirm the bundle reached every member. Also check the app is enabled under
Apps > Manage Apps.

**Nothing is filled; the result looks identical to the input**

The span was probably inferred larger than you expected. Inference needs at
least three distinct timestamps: with only two, the single observed gap becomes
the span and there is nothing to fill. Pass `span` explicitly. Also confirm the
results really are sparse - if every series already has a row in every bucket,
there is nothing to add.

**"fillcontinuous needs at least one group-by field"**

The command was run without a by clause. It fills per series, so it needs to
know which fields identify a series:

```
| fillcontinuous span=1h by host, sourcetype
```

**"Span '1mon' uses a calendar unit"**

Calendar spans are rejected rather than approximated, because months, quarters
and years have no constant length. Use a fixed-width span (s, m, h, d, w), or
bin by the calendar unit first and fill at a fixed span.

**"Could not read span '...'"**

The span was not a number followed by a supported unit. Valid examples: 30s,
5m, 1h, 12h, 1d, 1w.

**"Filling N bucket(s) across M series would produce X rows, over the ... limit"**

The result would be too large to build in memory. The message names both
factors so you can see which is the problem. Widen the span, narrow the time
range, or group by fewer or lower-cardinality fields - grouping by something
like an IP address at a fine span is the usual cause.

**"Filling this range at span=... would need more than N time buckets"**

The time range divided by the span is too large. This almost always means the
span is smaller than intended.

**"fillcontinuous passed through N row(s) with no numeric _time"**

Some rows had a `_time` that was missing, empty, non-numeric or infinite. They
are passed through untouched rather than dropped. Run `bin` or `stats` before
the command so results are bucketed, and check for an eval that turned `_time`
into a string.

**Results are correct but the chart still shows gaps**

Charting commands need the results in a particular shape. After filling, pivot
for display with `xyseries`, or concatenate the group-by fields into a single
series field for timechart-style rendering.

**The command is not available from another app**

It is exported system-wide by default, so this usually means the export was
changed locally. Check `metadata/local.meta` on the search head.

**Errors mentioning Python or the interpreter**

The app requires Python 3 and supports 3.9 and 3.13. On Splunk 10.2 and later
the platform selects the highest available. Check
`$SPLUNK_HOME/var/log/splunk/splunkd.log` for ChunkedExternProcessor errors.

**Getting more detail**

Errors appear in the job inspector and in
`$SPLUNK_HOME/var/log/splunk/splunkd.log`. Every successful run writes an INFO
message saying how many rows were added, across how many buckets and series - a
quick way to confirm the command did what you expected.
