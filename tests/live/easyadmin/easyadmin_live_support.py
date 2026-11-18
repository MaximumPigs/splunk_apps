"""Helpers shared by easyadmin's live tests (not a test module: no test_ prefix).

Everything here reads from or writes to splunkd through the ``splunk`` client
(or a client signed in as a sandbox user), so a test can check what the app
did against splunkd itself rather than against the app's own report.
"""

import json
import logging
import time
import urllib.parse
import uuid

from splk.rest import SplunkError

APP = "easyadmin"
ENDPOINT = "/services/easyadmin/roles"

log = logging.getLogger("splk.live.easyadmin")


def grant(role, item, on=True, field="srchIndexesAllowed"):
    """A matrix change: tick (on=True) or untick ``item`` in ``field``."""
    return {"role": role, "field": field, "item": item, "grant": on}


def setting(role, field, value, previous):
    """A settings change, based on the value the page loaded (``previous``)."""
    return {"role": role, "field": field, "value": value, "previous": previous}


def submit(client, changes):
    """POST as a generic REST client would: the list as JSON in a form field."""
    return client.request("POST", ENDPOINT, {"changes": json.dumps(changes)})


def submit_json(client, document):
    """POST a JSON body, as the page does."""
    return client.request("POST", ENDPOINT, json_body=document)


def model(client):
    return client.request("GET", ENDPOINT)


def tab(document, tab_id):
    return next(t for t in document["tabs"] if t["id"] == tab_id)


def tab_of_field(document, field):
    """The tab that edits ``field``."""
    return next(t for t in document["tabs"] if any(f["name"] == field for f in t["fields"]))


def loaded_value(document, role, field):
    """What the page would show (and send as ``previous``) for a setting."""
    return tab_of_field(document, field)["values"][role][field]["value"]


def role_content(client, role):
    path = "/services/authorization/roles/%s" % urllib.parse.quote(role, safe="")
    return client.request("GET", path)["entry"][0]["content"]


def as_set(value):
    # splunkd returns a lone value as a bare string, and stores lists sorted
    # rather than as written, so compare as sets.
    if value in (None, ""):
        return set()
    return set(value) if isinstance(value, list) else {value}


def text(value):
    # splunkd's JSON gives numeric settings as numbers and flags as booleans
    # (srchAllowAdvancedCron comes back as false, observed on 10.6.1); the
    # app deals in text, with a flag as "1" or "0".
    if value is None:
        return ""
    if isinstance(value, bool):
        return "1" if value else "0"
    return str(value)


def wait_for_audit_line(search, role, timeout=90):
    """Poll _internal until easyadmin.log's line for ``role`` is searchable.

    Returns the matching rows (empty when it never arrived). Indexing the
    app's log takes a few seconds after the write.
    """
    spl = 'search index=_internal source=*easyadmin.log "role=%s" | table _raw' % role
    deadline = time.time() + timeout
    while True:
        rows = search(spl, earliest="-15m", latest="now")
        if rows or time.time() >= deadline:
            return rows
        time.sleep(3)


def wait_for_marker(client, search, user, timeout=90):
    """Send a request nothing else sends, then wait until it is searchable in splunkd_access.

    Why: "no such request in the log" proves nothing while the log is still
    being indexed. splunkd writes an access line when a request finishes, and
    splunkd_access lines become searchable in the order they were written
    (observed on 10.6.1 with one ingestion pipeline: in batches that were
    always a prefix, never a later line before an earlier one; checked on
    every live run by test_access_log_becomes_searchable_in_request_order), so
    once this later request is searchable, an earlier request by ``user`` is
    too. Not observed with several pipelines or on an indexer cluster.
    Returns the marker's rows (empty when it never arrived).
    """
    marker = "splktest_marker_%d_%s" % (int(time.time() * 1000), uuid.uuid4().hex[:4])
    try:
        client.request("GET", "/servicesNS/nobody/search/admin/macros/%s" % marker)
    except SplunkError as error:
        # A 404 is what we expect: the macro does not exist; the request is logged all the same.
        log.debug("marker request %s answered %s", marker, error)
    return wait_for_access_rows(search, user, "*%s*" % marker, timeout)


def access_log_order_snapshots(client, count=40):
    """Send ``count`` marker requests one after another; after each, list which markers are searchable.

    Returns ``(prefix, snapshots)``: the unique marker prefix and one
    ``(sent, seen, low, top)`` tuple of ints per request. ``low`` and ``top``
    are the smallest and largest marker number searchable at that point (0
    when none is: the search returns no such fields then, observed on 10.6.1).

    Why ``map``: it runs the iterations serially, so request n has finished,
    and been logged, before request n+1 is sent, and each snapshot is taken
    without a Python round trip in between. The request is a 404 GET of a
    macro that does not exist (splunkd logs it all the same); the 404 comes
    back inside the search and ``map`` carries on. ``maxsearches`` must equal
    ``count``, or ``map`` stops early without saying so.
    """
    prefix = "splktest_order_%d_%s" % (int(time.time() * 1000), uuid.uuid4().hex[:4])
    spl = ('| makeresults count=%(n)d | streamstats count as n'
           ' | map maxsearches=%(n)d search="'
           '| rest splunk_server=local count=0 /servicesNS/nobody/search/admin/macros/%(p)s_$n$'
           ' | append [search index=_internal sourcetype=splunkd_access uri=\\"*%(p)s_*\\"'
           ' earliest=-5m latest=+5m'
           ' | rex field=uri \\"%(p)s_(?<m>\\d+)\\" | eval m=tonumber(m)'
           ' | stats dc(m) as seen max(m) as top min(m) as low]'
           ' | eval sent=$n$ | where isnotnull(seen) | table sent seen low top"'
           ' | sort 0 num(sent)' % {"n": count, "p": prefix})
    rows = client.oneshot(spl, earliest="-5m", latest="+5m", timeout=240)
    snapshots = [tuple(int(row.get(key) or 0) for key in ("sent", "seen", "low", "top")) for row in rows]
    log.info("order probe %s: %d snapshot(s)", prefix, len(snapshots))
    return prefix, snapshots


def wait_for_access_rows(search, user, uri, timeout=90):
    """Poll _internal until splunkd_access has a request by ``user`` for ``uri``.

    ``uri`` is a search wildcard pattern. splunkd logs the handler's own
    requests to splunkd with the caller as ``user``, so this shows which
    splunkd calls a REST endpoint made on the caller's behalf. Returns the
    rows (empty when none arrived); indexing lags the request by seconds.
    """
    spl = ('search index=_internal sourcetype=splunkd_access user="%s" uri="%s" | table _time uri'
           % (user, uri))
    deadline = time.time() + timeout
    while True:
        rows = search(spl, earliest="-15m", latest="now")
        if rows or time.time() >= deadline:
            return rows
        time.sleep(3)
