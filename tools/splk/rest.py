"""Minimal Splunk management-port (8089) REST client.

Built on urllib only, so splk has no runtime dependency on the Splunk SDK and
runs on any Python the CI matrix uses. It covers exactly what the dev loop
needs: server info, app install, reload, restart, messages and oneshot search.
"""

import json
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request

from splk.logs import get_logger

log = get_logger("rest")


class SplunkError(Exception):
    """A non-2xx response or a transport failure talking to splunkd."""

    def __init__(self, message, status=None, body=None):
        super(SplunkError, self).__init__(message)
        self.status = status
        self.body = body


def _messages_from_body(body):
    """Pull Splunk's human-readable error text out of a JSON error response."""
    try:
        data = json.loads(body)
    except (TypeError, ValueError):
        return body[:500] if body else ""
    messages = data.get("messages") or []
    return "; ".join(m.get("text", "") for m in messages if isinstance(m, dict)) or body[:500]


class SplunkClient(object):
    """Talks to one target. Every request carries ``output_mode=json``."""

    def __init__(self, target, timeout=60, opener=None, session_key=None):
        self.target = target
        self.timeout = timeout
        # Requests carry the target's token unless this client was made for a
        # signed-in user (see as_user), when they carry that user's session.
        self._session_key = session_key
        if opener is not None:
            # Tests inject an opener pointing at a fake server.
            self._opener = opener
        else:
            context = ssl.create_default_context()
            if not target.verify_tls:
                # A fresh Splunk install serves a self-signed certificate on
                # 8089. Verification is switched off per target, explicitly.
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
            self._opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=context))

    # ------------------------------------------------------------------ core

    def _authorization(self):
        """The Authorization header value: a user's session, else the target token."""
        if self._session_key:
            return "Splunk %s" % self._session_key
        return "Bearer %s" % self.target.token

    def request(self, method, path, params=None, timeout=None, json_body=None):
        """Send one request and return the decoded JSON body (or {} if empty).

        ``path`` is relative to the management port root, e.g.
        ``/services/server/info``. GET and DELETE params go in the query
        string; POST params are form-encoded in the body, which is what
        splunkd expects. ``json_body`` sends that object as an
        ``application/json`` body instead (params then go in the query string),
        for custom endpoints that accept JSON.
        """
        params = dict(params or {})
        params.setdefault("output_mode", "json")
        encoded = urllib.parse.urlencode(params, doseq=True)
        url = self.target.base_url + path
        data = None
        content_type = None
        if method in ("GET", "DELETE") or json_body is not None:
            url = "%s?%s" % (url, encoded)
        else:
            data = encoded.encode("utf-8")
            content_type = "application/x-www-form-urlencoded"
        if json_body is not None:
            data = json.dumps(json_body).encode("utf-8")
            content_type = "application/json"

        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", self._authorization())
        if content_type is not None:
            req.add_header("Content-Type", content_type)

        started = time.time()
        log.debug("%s %s", method, path)
        try:
            with self._opener.open(req, timeout=timeout or self.timeout) as resp:
                body = resp.read().decode("utf-8", "replace")
                status = resp.status
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")
            detail = _messages_from_body(body)
            log.debug("%s %s -> HTTP %s: %s", method, path, exc.code, detail)
            raise SplunkError(
                "%s %s failed: HTTP %s %s" % (method, path, exc.code, detail),
                status=exc.code, body=body,
            )
        except (urllib.error.URLError, OSError) as exc:
            reason = getattr(exc, "reason", exc)
            raise SplunkError("Cannot reach %s: %s" % (self.target.base_url, reason))

        log.debug("%s %s -> HTTP %s in %.2fs", method, path, status, time.time() - started)
        if not body.strip():
            return {}
        try:
            return json.loads(body)
        except ValueError:
            raise SplunkError("Non-JSON response from %s %s" % (method, path), status=status, body=body)

    # ------------------------------------------------------------- helpers

    def as_user(self, username, password):
        """Sign in as another user and return a client that acts as them.

        Live tests use this to check what a less privileged account sees and
        may do. The password travels only in the login request's body and is
        never logged (request() logs method and path, nothing else).
        """
        data = self.request("POST", "/services/auth/login",
                            {"username": username, "password": password})
        key = data.get("sessionKey")
        if not key:
            raise SplunkError("Sign-in as %s returned no session key" % username)
        log.debug("Signed in to splunkd as %s", username)
        return SplunkClient(self.target, timeout=self.timeout, opener=self._opener, session_key=key)

    def server_info(self):
        """Return the ``content`` dict of /services/server/info."""
        data = self.request("GET", "/services/server/info")
        return data["entry"][0]["content"]

    def app_info(self, app):
        """Return the app's entry content, or None if it is not installed."""
        try:
            data = self.request("GET", "/services/apps/local/%s" % urllib.parse.quote(app))
        except SplunkError as exc:
            if exc.status == 404:
                return None
            raise
        return data["entry"][0]["content"]

    def install_package(self, server_path, app=None):
        """Install or upgrade an app from a package path readable by splunkd.

        ``update=true`` lets the same call upgrade an existing install. The
        apps/local reference documents ``filename``/``name``/``explicit_appname``;
        ``update`` is documented on the older appinstall endpoint, so the deploy
        command verifies the installed version afterwards rather than trusting it.
        """
        params = {"filename": "true", "name": server_path, "update": "true"}
        if app:
            params["explicit_appname"] = app
        return self.request("POST", "/services/apps/local", params)

    def reload_apps(self):
        """Ask splunkd to re-read app configuration without a restart."""
        return self.request("POST", "/services/apps/local/_reload")

    def restart_required(self):
        """True when splunkd has posted its 'restart required' message."""
        try:
            self.request("GET", "/services/messages/restart_required")
        except SplunkError as exc:
            if exc.status == 404:
                return False
            raise
        return True

    def restart(self, wait_seconds=300, poll_seconds=5):
        """Restart splunkd and block until it answers again (or time out)."""
        self.request("POST", "/services/server/control/restart")
        log.info("Restart requested; waiting up to %ds for splunkd", wait_seconds)
        # Give splunkd a moment to actually go down before polling.
        time.sleep(poll_seconds)
        deadline = time.time() + wait_seconds
        while time.time() < deadline:
            try:
                self.server_info()
                log.info("splunkd is back")
                return True
            except SplunkError:
                time.sleep(poll_seconds)
        raise SplunkError("splunkd did not come back within %ds" % wait_seconds)

    def index_exists(self, index):
        """True when ``index`` exists on the target."""
        try:
            self.request("GET", "/services/data/indexes/%s" % urllib.parse.quote(index))
        except SplunkError as exc:
            if exc.status == 404:
                return False
            raise
        return True

    def submit_event(self, raw, index, sourcetype, source="splk:live-test", host="splk"):
        """Index one raw event via receivers/simple, for live-test seed data.

        The event goes through the normal parsing pipeline, so index-time
        props (line breaking, timestamps) apply exactly as for real data.
        """
        params = {"index": index, "sourcetype": sourcetype, "source": source, "host": host}
        url = "/services/receivers/simple?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(self.target.base_url + url, data=raw.encode("utf-8"), method="POST")
        req.add_header("Authorization", self._authorization())
        try:
            with self._opener.open(req, timeout=self.timeout) as resp:
                resp.read()
        except urllib.error.HTTPError as exc:
            raise SplunkError("receivers/simple failed: HTTP %s" % exc.code, status=exc.code)
        except (urllib.error.URLError, OSError) as exc:
            raise SplunkError("Cannot reach %s: %s" % (self.target.base_url, getattr(exc, "reason", exc)))

    def oneshot(self, spl, earliest=None, latest=None, timeout=None):
        """Run a blocking search and return its result rows as a list of dicts.

        A query that does not start with a generating pipe or ``search`` gets
        ``search`` prepended, mirroring what the search bar does.
        """
        query = spl.strip()
        if not (query.startswith("|") or query.startswith("search ")):
            query = "search " + query
        params = {"search": query, "exec_mode": "oneshot", "count": 0}
        if earliest is not None:
            params["earliest_time"] = earliest
        if latest is not None:
            params["latest_time"] = latest
        data = self.request("POST", "/services/search/jobs", params, timeout=timeout)
        rows = data.get("results", [])
        log.debug("Search returned %d row(s)", len(rows))
        return rows
