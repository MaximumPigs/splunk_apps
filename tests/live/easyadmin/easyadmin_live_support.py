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
    splunkd_access.log is indexed in file order (inferred, not observed), so
    once this later request is searchable, an earlier request by ``user`` would
    be too. Returns the marker's rows (empty when it never arrived).
    """
    marker = "splktest_marker_%d_%s" % (int(time.time() * 1000), uuid.uuid4().hex[:4])
    try:
        client.request("GET", "/servicesNS/nobody/search/admin/macros/%s" % marker)
    except SplunkError as error:
        # A 404 is what we expect: the macro does not exist; the request is logged all the same.
        log.debug("marker request %s answered %s", marker, error)
    return wait_for_access_rows(search, user, "*%s*" % marker, timeout)


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
