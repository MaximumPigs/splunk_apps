# fillcontinuous - Splunkbase listing

Copy each section below into the matching field on the Splunkbase upload form.
See ../README.md for the field mapping and why this lives outside apps/.

## Two rules for editing this file

**ASCII only.** No characters above U+007F. Use "-" not an em dash, and
straight quotes. This text is pasted into a third-party web form, so it
survives at least one encoding round-trip outside our control.

**HTML in the long fields only.** APP NAME, SUMMARY and SHORT DESCRIPTION are
short single-line fields and are pasted as plain text; markup there would
appear as literal tags. DETAILS, INSTALLATION and TROUBLESHOOTING are long-form
fields and take HTML.

## About the CSS

Splunkbase sanitises submitted markup, and a `<style>` block may well be
stripped. The HTML below is therefore written to read correctly with **no**
styling applied: headings, lists and tables carry the structure, and the CSS
only makes it nicer where it is allowed through. After your first submission,
look at the rendered page and delete the `<style>` blocks if they did not
survive - leaving dead markup in the field helps nobody.

Angle brackets inside code samples are escaped as `&lt;` and `&gt;`. If you
edit a syntax block, keep them escaped or the browser will eat them as tags.

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
than "App" because this ships no views. No "for &lt;technology&gt;" suffix,
since that form is only for interoperating with a third-party product.

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
DETAILS  (HTML)
===============================================================================

<style>
.mp-fc { max-width: 62em; line-height: 1.55; }
.mp-fc h3 { margin: 1.6em 0 .5em; padding-bottom: .25em;
            border-bottom: 2px solid #65a637; font-size: 1.15em; }
.mp-fc h4 { margin: 1.2em 0 .4em; font-size: 1em; font-weight: 700; }
.mp-fc pre { background: #f5f6f7; border: 1px solid #dcdee0;
             border-left: 3px solid #65a637; border-radius: 3px;
             padding: .75em 1em; overflow-x: auto; font-size: .9em; }
.mp-fc code { font-family: Consolas, Monaco, "Courier New", monospace; }
.mp-fc table { border-collapse: collapse; margin: 1em 0; width: 100%; }
.mp-fc th, .mp-fc td { border: 1px solid #dcdee0; padding: .45em .7em;
                       text-align: left; vertical-align: top; font-size: .93em; }
.mp-fc th { background: #f5f6f7; font-weight: 700; }
.mp-fc ul { margin: .6em 0; padding-left: 1.4em; }
.mp-fc li { margin: .35em 0; }
.mp-fc .mp-lede { font-size: 1.05em; }
.mp-fc .mp-note { background: #fff8e5; border-left: 3px solid #f8be34;
                  padding: .7em 1em; margin: 1em 0; }
</style>

<div class="mp-fc">

<p class="mp-lede"><strong>fillcontinuous</strong> makes sparse time-series
results dense. It adds a row for every combination of time bucket and group-by
values that is missing, so every series has a value in every bucket.</p>

<h3>The problem</h3>

<p><code>timechart</code> zero-fills gaps for you, but only across a single
split-by field. Add a second dimension and you fall back to
<code>stats</code>, which returns nothing at all for buckets where nothing
happened:</p>

<pre><code>index=web
| bin _time span=1h
| stats count by _time, host, sourcetype</code></pre>

<p>Those absent rows become false drops to zero on a chart, and averages
computed over only the buckets that happen to exist.</p>

<div class="mp-note">
<p><strong>makecontinuous does not solve this.</strong> It fills along one
dimension and has no concept of group-by fields, so it inserts a single
valueless row per missing bucket instead of one row per series - and it does
not warn you. On the example above it returns four rows where the answer is
six, including one row belonging to no host at all.</p>
</div>

<h3>The solution</h3>

<pre><code>index=web
| bin _time span=1h
| stats count by _time, host, sourcetype
| fillcontinuous span=1h by host, sourcetype</code></pre>

<p>Every combination of time bucket and observed host/sourcetype pair now has a
row, with <code>count=0</code> in the ones that were missing.
<code>fillgaps</code> is registered as an alias if you prefer the shorter
name.</p>

<h3>Syntax</h3>

<pre><code>fillcontinuous [span=&lt;span&gt;] [fillvalue=&lt;string&gt;] [marker=&lt;field&gt;]
               [start=&lt;epoch&gt;] [end=&lt;epoch&gt;]
               [maxbuckets=&lt;int&gt;] [maxrows=&lt;int&gt;]
               [by] &lt;field&gt;, ...</code></pre>

<table>
<tr><th>Option</th><th>Default</th><th>Description</th></tr>
<tr><td><code>span</code></td><td>inferred</td>
    <td>Bucket width. Fixed-width units only: ms, cs, ds, s, m (minutes), h, d,
        w.</td></tr>
<tr><td><code>fillvalue</code></td><td><code>0</code></td>
    <td>Value given to every aggregate field on an added row.</td></tr>
<tr><td><code>marker</code></td><td>none</td>
    <td>Field to add, set to 1 on added rows and 0 on real ones. Useful for
        auditing what the command did.</td></tr>
<tr><td><code>start</code>, <code>end</code></td><td>none</td>
    <td>Epoch seconds. Extend the grid beyond the observed data, for leading or
        trailing buckets containing no events at all.</td></tr>
<tr><td><code>maxbuckets</code></td><td><code>100000</code></td>
    <td>Ceiling on time buckets. Can be lowered, not raised.</td></tr>
<tr><td><code>maxrows</code></td><td><code>1000000</code></td>
    <td>Ceiling on rows produced, which is buckets multiplied by series. Can be
        lowered, not raised.</td></tr>
</table>

<p>The <code>by</code> keyword is optional, and field lists may be separated by
commas or spaces.</p>

<h3>Examples</h3>

<h4>Flag which rows were added, letting the span be inferred</h4>

<pre><code>index=web
| bin _time span=5m
| stats sum(bytes) as bytes by _time, host, status
| fillcontinuous marker=was_filled by host, status</code></pre>

<h4>Fill with something other than zero, where zero would be a lie</h4>

<pre><code>... | fillcontinuous span=1m fillvalue="" by host, metric_name</code></pre>

<h4>Cover the whole window, including buckets with no events at all</h4>

<pre><code>index=web
| bin _time span=1h
| stats count by _time, host, sourcetype
| fillcontinuous span=1h start=1767225600 end=1767312000 by host, sourcetype</code></pre>

<h3>How it works</h3>

<ul>
<li><strong>Only combinations that actually occur are filled.</strong> A
    host/sourcetype pair that never appears is not invented, so the output does
    not expand into the full cross product of every field's values. This
    matches how timechart creates a column only for values it saw.</li>
<li><strong>The bucket grid is anchored on the timestamps in your
    results</strong>, with synthetic buckets inserted only between consecutive
    observed times - never computed from a fabricated origin. Real rows are
    therefore never moved, duplicated or misaligned.</li>
<li><strong>Daylight saving is handled by that anchoring.</strong> Splunk bins
    d and w spans in the server's local timezone, so the day containing a
    transition is 23 or 25 hours, not 24. Stepping a fixed 86400 seconds from a
    start time would drift out of alignment after it; anchoring on observed
    timestamps cannot.</li>
<li><strong>Calendar spans are rejected, not approximated.</strong>
    <code>1mon</code>, <code>1q</code> and <code>1y</code> raise a clear error,
    because months and years have no constant length and stepping them as
    seconds would silently misalign the buckets.</li>
<li><strong>Output is ordered by _time, then by the group-by values</strong>,
    matching the ordering of the <code>stats by _time, ...</code> that almost
    always precedes it.</li>
</ul>

<h3>Things worth knowing</h3>

<ul>
<li>Rows without a usable numeric <code>_time</code> are passed through
    unchanged, not dropped, and the command tells you how many. Nothing is
    silently lost.</li>
<li>Duplicate rows are preserved. Real data is never deduplicated; rows are
    only added where a series has no row in a bucket.</li>
<li>A group-by field absent from the real rows stays absent on added rows,
    rather than being invented as an empty string.</li>
<li>Aggregate fields are collected across all rows, so a field present on only
    some rows still gets a fill value everywhere and the columns stay
    consistent.</li>
<li>Every successful run reports how many rows it added, across how many
    buckets and series.</li>
</ul>

<h3>Resource limits</h3>

<p>Output is buckets multiplied by series, and the series count comes from your
data - so a few hundred rows spread over a few hundred high-cardinality values
amplifies into millions. The command checks that product before building
anything and refuses with a message naming both factors. Both ceilings can be
lowered but never raised, so one search cannot disable the protection on a
shared search head.</p>

<h3>Compatibility</h3>

<ul>
<li>Splunk Enterprise 9.x and 10.x, and Splunk Cloud Platform.</li>
<li>Runs on Python 3.9 and Python 3.13.</li>
<li>Search head only. No indexer or forwarder installation, and no
    configuration.</li>
<li>Collects no data, opens no network connections, reads and writes no files.</li>
<li>Licensed under Apache 2.0.</li>
</ul>

</div>


===============================================================================
INSTALLATION  (HTML)
===============================================================================

<style>
.mp-fc-i { max-width: 62em; line-height: 1.55; }
.mp-fc-i h3 { margin: 1.5em 0 .5em; padding-bottom: .25em;
              border-bottom: 2px solid #65a637; font-size: 1.1em; }
.mp-fc-i pre { background: #f5f6f7; border: 1px solid #dcdee0;
               border-left: 3px solid #65a637; border-radius: 3px;
               padding: .75em 1em; overflow-x: auto; font-size: .9em; }
.mp-fc-i code { font-family: Consolas, Monaco, "Courier New", monospace; }
.mp-fc-i ol, .mp-fc-i ul { margin: .6em 0; padding-left: 1.5em; }
.mp-fc-i li { margin: .35em 0; }
</style>

<div class="mp-fc-i">

<p>Install on <strong>search heads only</strong>. No indexer or forwarder
installation is needed, and there is nothing to configure afterwards.</p>

<h3>Splunk Cloud</h3>

<p>Install from Splunkbase through the Splunk Cloud UI, or request installation
through Splunk Support if self-service install is not enabled for your
stack.</p>

<h3>Splunk Enterprise, single search head</h3>

<ol>
<li>Go to <strong>Apps &gt; Manage Apps &gt; Install app from file</strong>.</li>
<li>Upload the .spl file and click <strong>Upload</strong>.</li>
<li>Restart Splunk when prompted. A restart is required before a new custom
    search command is registered.</li>
</ol>

<p>Or unpack it and restart:</p>

<pre><code>tar -xvzf fillcontinuous-&lt;version&gt;.spl -C $SPLUNK_HOME/etc/apps/
$SPLUNK_HOME/bin/splunk restart</code></pre>

<h3>Search head cluster</h3>

<ol>
<li>Place the unpacked app in <code>$SPLUNK_HOME/etc/shcluster/apps/</code> on
    the deployer.</li>
<li>Apply the bundle:</li>
</ol>

<pre><code>$SPLUNK_HOME/bin/splunk apply shcluster-bundle -target &lt;member-uri&gt;</code></pre>

<h3>Verifying the install</h3>

<p>This search needs no indexed data. It should return exactly six rows - three
time buckets across two series - with <code>count=0</code> in the three that
were filled.</p>

<pre><code>| makeresults count=3
| streamstats count as row
| eval _time=case(row=1,1767225600, row=2,1767225600, row=3,1767232800),
       host=case(row=1,"web01", row=2,"web02", row=3,"web01"),
       sourcetype="access",
       count=case(row=1,5, row=2,3, row=3,7)
| fields _time host sourcetype count
| fillcontinuous span=1h by host, sourcetype</code></pre>

<h3>Upgrading</h3>

<p>Install the new version over the old one and restart. There are no saved
searches, lookups or configuration to migrate.</p>

</div>


===============================================================================
TROUBLESHOOTING  (HTML)
===============================================================================

<style>
.mp-fc-t { max-width: 62em; line-height: 1.55; }
.mp-fc-t dt { font-weight: 700; margin: 1.3em 0 .3em;
              font-family: Consolas, Monaco, "Courier New", monospace;
              font-size: .95em; color: #33343a; }
.mp-fc-t dd { margin: 0 0 .8em 0; padding-left: 1em;
              border-left: 3px solid #dcdee0; }
.mp-fc-t code { font-family: Consolas, Monaco, "Courier New", monospace; }
.mp-fc-t pre { background: #f5f6f7; border: 1px solid #dcdee0;
               border-radius: 3px; padding: .6em .9em; overflow-x: auto;
               font-size: .9em; }
</style>

<div class="mp-fc-t">

<dl>

<dt>"Unknown search command 'fillcontinuous'"</dt>
<dd>The command has not been registered. Restart Splunk - this is required
    after installing an app that adds a custom search command. On a search head
    cluster, confirm the bundle reached every member. Also check the app is
    enabled under Apps &gt; Manage Apps.</dd>

<dt>Nothing is filled; the result looks identical to the input</dt>
<dd>The span was probably inferred larger than you expected. Inference needs at
    least three distinct timestamps: with only two, the single observed gap
    becomes the span and there is nothing to fill. Pass <code>span</code>
    explicitly. Also confirm the results really are sparse - if every series
    already has a row in every bucket, there is nothing to add.</dd>

<dt>"fillcontinuous needs at least one group-by field"</dt>
<dd>The command was run without a by clause. It fills per series, so it needs
    to know which fields identify a series:
    <pre><code>| fillcontinuous span=1h by host, sourcetype</code></pre></dd>

<dt>"Span '1mon' uses a calendar unit"</dt>
<dd>Calendar spans are rejected rather than approximated, because months,
    quarters and years have no constant length. Use a fixed-width span (s, m,
    h, d, w), or bin by the calendar unit first and fill at a fixed span.</dd>

<dt>"Could not read span '...'"</dt>
<dd>The span was not a number followed by a supported unit. Valid examples:
    30s, 5m, 1h, 12h, 1d, 1w.</dd>

<dt>"Filling N bucket(s) across M series would produce X rows, over the ...
    limit"</dt>
<dd>The result would be too large to build in memory. The message names both
    factors so you can see which is the problem. Widen the span, narrow the
    time range, or group by fewer or lower-cardinality fields - grouping by
    something like an IP address at a fine span is the usual cause.</dd>

<dt>"Filling this range at span=... would need more than N time buckets"</dt>
<dd>The time range divided by the span is too large. This almost always means
    the span is smaller than intended.</dd>

<dt>"fillcontinuous passed through N row(s) with no numeric _time"</dt>
<dd>Some rows had a <code>_time</code> that was missing, empty, non-numeric or
    infinite. They are passed through untouched rather than dropped. Run
    <code>bin</code> or <code>stats</code> before the command so results are
    bucketed, and check for an eval that turned <code>_time</code> into a
    string.</dd>

<dt>Results are correct but the chart still shows gaps</dt>
<dd>Charting commands need the results in a particular shape. After filling,
    pivot for display with <code>xyseries</code>, or concatenate the group-by
    fields into a single series field for timechart-style rendering.</dd>

<dt>The command is not available from another app</dt>
<dd>It is exported system-wide by default, so this usually means the export was
    changed locally. Check <code>metadata/local.meta</code> on the search
    head.</dd>

<dt>Errors mentioning Python or the interpreter</dt>
<dd>The app requires Python 3 and supports 3.9 and 3.13. On Splunk 10.2 and
    later the platform selects the highest available. Check
    <code>$SPLUNK_HOME/var/log/splunk/splunkd.log</code> for
    ChunkedExternProcessor errors.</dd>

<dt>Getting more detail</dt>
<dd>Errors appear in the job inspector and in
    <code>$SPLUNK_HOME/var/log/splunk/splunkd.log</code>. Every successful run
    writes an INFO message saying how many rows were added, across how many
    buckets and series - a quick way to confirm the command did what you
    expected.</dd>

</dl>

</div>
