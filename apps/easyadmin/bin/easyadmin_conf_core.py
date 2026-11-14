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

"""Pure logic behind the configuration precedence view: no Splunk imports.

Shows, like ``splunk btool <conf> list --debug``, which file each setting
comes from and which apps set the same setting differently.

Why files rather than REST: splunkd's configs/conf-<name> entries are the
merged result for an app's context. Observed on 10.6.1: the Monitoring
Console's [scheduler] props entry also holds EXTRACT-fields, which only the
search app sets, plus every [default] value. REST cannot say which app or
layer set a value, so the files are read, read-only, as btool does.

Precedence is btool's global context, from the Splunk documentation on
configuration file precedence:

    1. etc/system/local
    2. etc/apps/<app>/local, apps in ASCII order of directory name (A first)
    3. etc/apps/<app>/default, apps in ASCII order
    4. etc/system/default

Search-time settings (props EXTRACT, eventtypes...) are resolved per app
context instead; the view says so and does not model it.

Must remain valid on Python 3.9 as well as 3.13.
"""

import logging
import re

from easyadmin_core import EasyAdminError, error_payload

logger = logging.getLogger("easyadmin")

# Conf names the view accepts: lowercase file stems as Splunk uses them.
# \Z, not $: "$" also matches before a trailing newline.
CONF_NAME_RE = re.compile(r"^[a-z0-9_\-]{1,64}\Z")

# Never read: holds encrypted credentials only.
EXCLUDED_CONFS = ("passwords",)

# Attribute names whose values are secrets (passwords, keys, tokens). Their
# values are never sent to the browser: the view shows that they are set and
# where, which is what precedence needs, and masks the value.
#
# Matched on the END of the name, so that settings about secrets whose values
# are not secret (pass4SymmKey_minLength, invalidateSessionTokensOnLogout)
# stay readable. Masking is by name only: a secret inside an ordinary-looking
# value (a webhook URL, user:pass@host) is shown, to admins only.
SECRET_RE = re.compile(r"(password|passwd|pwd|pass4symmkey|passphrase|secret|token|credentials?|"
                       r"priv_?key|private_?key|api_?key|access_?key|auth_?key|_key)\Z", re.IGNORECASE)
MASK = "********"

# Settings that hold secrets without a secret-sounding name, masked by exact
# name: scripted authentication passes its credentials in this one.
SECRET_NAMES = ("scriptsecurearguments",)

# Bounds, so one request cannot read without limit. Counted in characters, as
# the files are read as text (a byte limit would be up to four times lower).
MAX_FILE_CHARS = 8 * 1024 * 1024
MAX_TOTAL_CHARS = 64 * 1024 * 1024
MAX_VALUE_LENGTH = 2000

LAYERS = ("system/local", "app/local", "app/default", "system/default")

# Files whose settings are applied at search time, where the app a search runs
# in (and object sharing) decide which value applies, not the global order.
# For these the view labels the first value "first in global order", never
# "in effect", and says why.
SEARCH_TIME_CONFS = ("props", "transforms", "macros", "eventtypes", "tags", "savedsearches", "fields",
                     "workflow_actions", "times", "datamodels", "collections", "lookups", "commands",
                     "alert_actions", "ui-prefs", "searchbnf")
SYSTEM = "system"


def parse_conf(text):
    """Parse Splunk .conf text into an ordered list of (stanza, {attr: value}).

    Follows Splunk's syntax: ``[stanza]`` headers, ``attr = value`` lines,
    ``#`` comment lines, and a trailing backslash continuing a value onto the
    next line (the newline is kept, as btool shows it). Settings before any
    header belong to ``default``. A repeated stanza merges, the later value
    winning, as Splunk reads a single file.
    """
    stanzas = {}
    order = []
    current = "default"
    pending_attr = None
    pending_value = None

    def put(stanza, attr, value):
        if stanza not in stanzas:
            stanzas[stanza] = {}
            order.append(stanza)
        stanzas[stanza][attr] = value

    if text.startswith(u"﻿"):
        text = text[1:]
    for raw in text.splitlines():
        if pending_attr is not None:
            line = raw
            if line.endswith("\\"):
                pending_value += "\n" + line[:-1]
                continue
            pending_value += "\n" + line
            put(current, pending_attr, pending_value.strip())
            pending_attr = pending_value = None
            continue
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            current = line[1:-1].strip() or "default"
            if current not in stanzas:
                stanzas[current] = {}
                order.append(current)
            continue
        if "=" not in line:
            continue
        attr, value = line.split("=", 1)
        attr = attr.strip()
        if not attr:
            continue
        value = value.strip()
        if raw.rstrip().endswith("\\"):
            pending_attr, pending_value = attr, value[:-1]
            continue
        put(current, attr, value)
    if pending_attr is not None:
        put(current, pending_attr, pending_value.strip())
    return [(name, stanzas[name]) for name in order]


def precedence_order(app_names):
    """The layers in btool's global order, highest priority first.

    Returns a list of (app, layer) pairs, ``app`` being ``system`` for
    etc/system. Apps sort by ASCII order of their directory name, so an
    uppercase name comes before every lowercase one, as in Splunk.
    """
    apps = sorted(a for a in app_names if a != SYSTEM)
    return ([(SYSTEM, "local")] + [(a, "local") for a in apps] +
            [(a, "default") for a in apps] + [(SYSTEM, "default")])


def is_secret(attr):
    return attr.lower() in SECRET_NAMES or bool(SECRET_RE.search(attr))


def _shown(attr, value):
    if is_secret(attr) and value:
        return MASK
    return value[:MAX_VALUE_LENGTH]


def build_precedence(conf, files, only_conflicts=True):
    """Every stanza and setting of ``conf`` with the file each value comes from.

    ``files`` maps (app, layer) to the text of that layer's <conf>.conf, for
    the layers that have one. Returns the stanzas, each with its settings,
    and for each setting every layer that sets it in precedence order, the
    first being the one in effect. A setting is a conflict when two layers
    set it to different values; with ``only_conflicts`` only stanzas with a
    conflict are returned.
    """
    order = precedence_order({app for app, _ in files})
    rank = {layer: position for position, layer in enumerate(order)}
    stanzas = {}
    for key in sorted(files, key=lambda k: rank[k]):
        app, layer = key
        for stanza, attrs in parse_conf(files[key]):
            entry = stanzas.setdefault(stanza, {})
            for attr, value in attrs.items():
                entry.setdefault(attr, []).append({"app": app, "layer": layer, "value": value})

    result = []
    for stanza in sorted(stanzas, key=lambda s: (s != "default", s.lower())):
        settings = []
        for attr in sorted(stanzas[stanza], key=str.lower):
            sources = stanzas[stanza][attr]
            values = {s["value"] for s in sources}
            settings.append({
                "name": attr,
                "secret": is_secret(attr),
                "conflict": len(values) > 1,
                "overridden": len(sources) > 1,
                "sources": [{"app": s["app"], "layer": s["layer"], "value": _shown(attr, s["value"]),
                             "effective": i == 0} for i, s in enumerate(sources)],
            })
        conflicts = sum(1 for s in settings if s["conflict"])
        if only_conflicts and not conflicts:
            continue
        result.append({"name": stanza, "conflicts": conflicts,
                       "apps": sorted({s["app"] for st in settings for s in st["sources"]}),
                       "settings": settings})
    return {
        "conf": conf,
        "search_time": conf in SEARCH_TIME_CONFS,
        "order": [{"app": app, "layer": layer} for app, layer in order if (app, layer) in files],
        "stanzas": result,
        "conflicting_stanzas": sum(1 for s in result if s["conflicts"]),
    }


def clean_conf_name(value):
    if not isinstance(value, str) or not CONF_NAME_RE.match(value):
        raise EasyAdminError("'conf' must be a configuration file name such as props or savedsearches.")
    if value in EXCLUDED_CONFS:
        raise EasyAdminError("%s.conf holds credentials and is not shown." % value)
    return value


def handle_request(method, query, reader, context):
    """Route one REST call. Returns ``(http_status, payload)``.

    ``reader`` reads the files (easyadmin_conf_rest.ConfFileReader in Splunk);
    ``context`` holds the caller's capabilities. Reading files bypasses
    splunkd's per-object permissions, so only administrators may use it.
    """
    if (method or "").upper() != "GET":
        return 405, error_payload("Only GET is supported: this view never changes configuration.")
    if "admin_all_objects" not in (context.get("capabilities") or []):
        logger.warning("user=%s action=conf_precedence refused: no admin_all_objects", context.get("user"))
        return 403, error_payload("The configuration precedence view needs the admin_all_objects "
                                  "capability, because it reads every app's configuration files.")
    try:
        conf = (query or {}).get("conf")
        if conf is None:
            return 200, {"confs": [c for c in reader.list_confs() if c not in EXCLUDED_CONFS]}
        conf = clean_conf_name(conf)
        only = (query or {}).get("all") not in ("1", "true")
        result = build_precedence(conf, reader.read_conf(conf), only_conflicts=only)
        # An audit line for every read of every app's configuration.
        logger.info("user=%s action=conf_precedence conf=%s stanzas=%d", context.get("user"), conf,
                    len(result["stanzas"]))
        return 200, result
    except EasyAdminError as error:
        return error.status, error_payload(str(error))
