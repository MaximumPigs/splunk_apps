"""UX audit: every view of an app, in both themes, checked in a real browser.

`splk ux <app>` (and the `ux` stage of `splk dev`) opens each view under
``apps/<app>/default/data/ui/views/`` once per theme and records, per view
and theme:

* a full-page screenshot, for the ux-reviewer agent (and the person) to look at;
* the theme Splunk actually drew, read from the page's background, because a
  page that follows the user's preference can refuse the ``?theme=`` asked for;
* an axe-core accessibility scan (WCAG 2.2 A and AA rules) of the app's own
  content: contrast, labels, names, roles, keyboard-reachable controls;
* console errors and uncaught exceptions, split into the app's own and
  Splunk Web's.

What blocks (fails the stage): an uncaught exception, a console error from the
app's own static files, a view that never shows its ready selector, and an axe
violation of ``serious`` or ``critical`` impact that is not waived in
``tests/ui/<app>/ux.toml``. Everything else is reported for the reviewer.
Judgement (layout, wording, states, consistency) is the ux-reviewer's job,
against the ``splunk-ux`` skill: a machine check cannot see that a table
is confusing.

The pure helpers (config, colours, summarising) have no Playwright import, so
they are unit-tested everywhere; the browser part runs only where Playwright is.
"""

import contextlib
import json
import os
import re
import urllib.parse

from splk import config, paths
from splk.logs import get_logger

log = get_logger("ux")

THEMES = ("light", "dark")
# axe impact levels, most severe first. The top two block; the rest are
# reported so the reviewer can weigh them.
IMPACTS = ("critical", "serious", "moderate", "minor")
BLOCKING_IMPACTS = ("critical", "serious")
# The standard the scan enforces: WCAG 2.2 level A and AA. axe's
# "best-practice" rules are left out on purpose: most of them (landmarks,
# regions, a single h1) are about the page shell, which Splunk Web owns.
AXE_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]

AXE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor", "axe-core")
AXE_PATH = os.path.join(AXE_DIR, "axe.min.js")
REPORTS_DIR = os.path.join(paths.BUILD_DIR, "reports", "ux")
CONFIG_NAME = "ux.toml"

# Keys a view may set in ux.toml, with their defaults. "body" scans the whole
# page, including Splunk Web's own chrome: set scope to the app's root element
# so findings are about code this repo can change. "states" lists panels and
# other states to open after the view is ready, each audited like a view.
VIEW_DEFAULTS = {"ready": None, "scope": "body", "settle_ms": 1500, "skip": False, "states": []}
# Keys of one [[views.<view>.states]] entry. click: selectors clicked in turn
# (the first match of each); query: extra URL parameters for the view, such
# as a page's test hook; ready: what the state shows once it is open.
STATE_KEYS = {"name", "click", "query", "ready", "settle_ms"}
_STATE_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


class UxConfigError(config.ConfigError):
    """tests/ui/<app>/ux.toml is malformed (bad key, waiver without a reason)."""


# ------------------------------------------------------------- discovery

def views_dir(app, apps_dir=None):
    return os.path.join(apps_dir or paths.APPS_DIR, app, "default", "data", "ui", "views")


def discover_views(app, apps_dir=None):
    """Names of the app's views (Simple XML or Dashboard Studio files), sorted."""
    directory = views_dir(app, apps_dir)
    if not os.path.isdir(directory):
        return []
    return sorted(os.path.splitext(name)[0] for name in os.listdir(directory)
                  if name.endswith(".xml") and not name.startswith("."))


def has_views(app, apps_dir=None):
    """True when the app ships at least one view; apps without pages have no UX stage."""
    return bool(discover_views(app, apps_dir))


# ---------------------------------------------------------------- config

def config_path(app, ui_dir=None):
    return os.path.join(ui_dir or paths.UI_TESTS_DIR, app, CONFIG_NAME)


def load_config(app, ui_dir=None):
    """Read tests/ui/<app>/ux.toml, or return an empty config when there is none.

    Shape::

        [defaults]                 # applies to every view
        settle_ms = 1500
        [views.role_management]    # per view: ready, scope, settle_ms, skip
        ready = "#root table"
        scope = "#root"
        [[waive]]                  # an accepted axe finding; reason is required
        rule = "color-contrast"
        view = "role_management"   # optional: only this view
        target = ".ea-badge"       # optional: only nodes whose selector contains this
        reason = "why it is acceptable"
    """
    path = config_path(app, ui_dir)
    if not os.path.isfile(path):
        log.debug("No %s; using defaults for every view", paths.display(path))
        return {"defaults": {}, "views": {}, "waive": []}
    with open(path, "rb") as handle:
        try:
            raw = config.tomllib.load(handle)
        except config.tomllib.TOMLDecodeError as exc:
            raise UxConfigError("%s: %s" % (paths.display(path), exc))
    return validate_config(raw, paths.display(path))


def validate_config(raw, where="ux.toml"):
    """Check keys and waivers; return a normalised dict. Raises UxConfigError."""
    unknown = set(raw) - {"defaults", "views", "waive"}
    if unknown:
        raise UxConfigError("%s: unknown section(s) %s" % (where, ", ".join(sorted(unknown))))
    defaults = raw.get("defaults") or {}
    views = raw.get("views") or {}
    for name, settings in [("defaults", defaults)] + sorted(views.items()):
        bad = set(settings) - set(VIEW_DEFAULTS)
        if bad:
            raise UxConfigError("%s: [%s] has unknown key(s) %s; allowed: %s" % (
                where, name, ", ".join(sorted(bad)), ", ".join(sorted(VIEW_DEFAULTS))))
    if defaults.get("states"):
        raise UxConfigError("%s: states belong to a view ([[views.<view>.states]]), not [defaults]" % where)
    for view, settings in sorted(views.items()):
        names = set()
        for number, state in enumerate(settings.get("states") or [], 1):
            label = "[[views.%s.states]] entry %d" % (view, number)
            bad = set(state) - STATE_KEYS
            if bad:
                raise UxConfigError("%s: %s has unknown key(s) %s; allowed: %s" % (
                    where, label, ", ".join(sorted(bad)), ", ".join(sorted(STATE_KEYS))))
            name = str(state.get("name") or "")
            if not _STATE_NAME_RE.match(name) or name in names:
                raise UxConfigError("%s: %s needs a unique name of lower-case letters, digits, - or _"
                                    % (where, label))
            names.add(name)
            click = state.get("click") or []
            state["click"] = [click] if isinstance(click, str) else list(click)
            if not state["click"] and not state.get("query"):
                raise UxConfigError("%s: %s needs click or query, or it is the view itself" % (where, label))
    waivers = raw.get("waive") or []
    for number, waiver in enumerate(waivers, 1):
        # A waiver with no reason is how real problems get silenced, so the
        # reason is required, as for AppInspect's expect file.
        if not waiver.get("rule") or not str(waiver.get("reason", "")).strip():
            raise UxConfigError("%s: waiver %d needs both rule and reason" % (where, number))
        bad = set(waiver) - {"rule", "view", "state", "theme", "target", "reason"}
        if bad:
            raise UxConfigError("%s: waiver %d has unknown key(s) %s" % (where, number, ", ".join(sorted(bad))))
    return {"defaults": defaults, "views": views, "waive": waivers}


def view_settings(cfg, view):
    """Settings for one view: built-in defaults, then [defaults], then [views.<view>]."""
    settings = dict(VIEW_DEFAULTS)
    settings.update(cfg.get("defaults") or {})
    settings.update((cfg.get("views") or {}).get(view) or {})
    return settings


# --------------------------------------------------------------- colours

_RGB_RE = re.compile(r"rgba?\(\s*([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)(?:[,\s/]+([\d.]+%?))?\s*\)")


def parse_css_color(value):
    """(r, g, b, alpha) from a computed ``rgb()``/``rgba()`` string, or None."""
    match = _RGB_RE.match((value or "").strip())
    if not match:
        return None
    r, g, b = (float(match.group(i)) for i in (1, 2, 3))
    alpha = match.group(4)
    if alpha is None:
        a = 1.0
    elif alpha.endswith("%"):
        a = float(alpha[:-1]) / 100.0
    else:
        a = float(alpha)
    return r, g, b, a


def relative_luminance(rgb):
    """WCAG relative luminance (0 black .. 1 white) of an (r, g, b) in 0..255."""
    def channel(c):
        c = c / 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = rgb[:3]
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def theme_of(css_color):
    """"dark" or "light" for a background colour, or None if it cannot be read.

    0.18 is roughly where white and black text have equal contrast against
    the background, so it splits "needs light text" from "needs dark text".
    """
    parsed = parse_css_color(css_color)
    if parsed is None or parsed[3] == 0:
        return None
    return "dark" if relative_luminance(parsed) < 0.18 else "light"


# ------------------------------------------------------------- findings

def flatten_violations(axe_result):
    """One finding per axe rule violated, with the selectors of the failing nodes."""
    findings = []
    for violation in (axe_result or {}).get("violations", []):
        nodes = violation.get("nodes") or []
        targets = []
        for node in nodes:
            # axe gives each node's target as a list (one entry per frame / shadow root).
            target = node.get("target") or []
            targets.append(" ".join(str(t) for t in target) if isinstance(target, list) else str(target))
        findings.append({
            "rule": violation.get("id"),
            "impact": violation.get("impact") or "minor",
            "help": violation.get("help", ""),
            "help_url": violation.get("helpUrl", ""),
            "targets": targets,
            # The first node's summary says what to change ("Element has insufficient colour contrast of 2.1").
            "example": ((nodes[0].get("failureSummary") or "").strip().splitlines() or [""])[-1].strip()
                       if nodes else "",
        })
    findings.sort(key=lambda f: IMPACTS.index(f["impact"]) if f["impact"] in IMPACTS else len(IMPACTS))
    return findings


def waiver_for(finding, view, theme, waivers, state=None):
    """The waiver that accepts this finding on this view, state and theme, or None.

    A waiver with a ``target`` covers the finding only if every failing node
    matches it, so a new failing element is not hidden by an old waiver. One
    with a ``state`` covers only that state; one without covers the view and
    all its states.
    """
    for waiver in waivers:
        if waiver["rule"] != finding["rule"]:
            continue
        if waiver.get("view") and waiver["view"] != view:
            continue
        if waiver.get("state") and waiver["state"] != state:
            continue
        if waiver.get("theme") and waiver["theme"] != theme:
            continue
        if waiver.get("target") and not all(waiver["target"] in t for t in finding["targets"]):
            continue
        return waiver
    return None


def own_console_errors(app, entries):
    """Console errors raised by the app's own static files or REST endpoints.

    Splunk Web logs errors of its own on most pages, so blocking on every
    console error would fail every app. An error whose source or text points
    at /static/app/<app>/, or at the app's own endpoints under
    /splunkd/__raw/services/<app>/ (a 500 from a page's handler), is the
    app's, and that one blocks. servicesNS/<user>/<app>/ is not matched:
    Splunk Web's own requests run in the app's namespace too.
    """
    markers = ("/static/app/%s/" % app, "/splunkd/__raw/services/%s/" % app)
    return [e for e in entries
            if any(m in (e.get("url") or "") or m in (e.get("text") or "") for m in markers)]


def label(result):
    """``view`` or ``view#state``: how a result is named in the report."""
    return result["view"] + ("#" + result["state"] if result.get("state") else "")


def summarise(app, results, waivers, run_notes=()):
    """Reduce audit results to (ok, summary, details) for the run log.

    ``details`` lists blocking problems first, then non-blocking notes, then
    ``run_notes`` (about the run as a whole, such as a theme switch that failed).
    """
    blocking, notes = [], []
    counts = {"views": len({r["view"] for r in results}), "shots": 0, "blocking": 0, "waived": 0, "reported": 0}
    for result in results:
        where = "%s [%s]" % (label(result), result["theme"])
        if result.get("skipped"):
            notes.append("%s skipped in ux.toml" % where)
            continue
        if result.get("error"):
            blocking.append("%s: %s" % (where, result["error"]))
            continue
        counts["shots"] += 1
        for error in result.get("page_errors", []):
            blocking.append("%s: uncaught exception: %s" % (where, error[:200]))
        for entry in own_console_errors(app, result.get("console", [])):
            blocking.append("%s: console error from the app: %s%s" % (
                where, entry.get("text", "")[:200], " (%s)" % entry["url"] if entry.get("url") else ""))
        rendered = result.get("rendered_theme")
        if rendered and rendered != result["theme"]:
            notes.append("%s: page rendered %s, so the %s theme was not audited here (the page follows "
                         "the signed-in user's theme preference, which the audit sets for each pass)"
                         % (where, rendered, result["theme"]))
        for finding in result.get("violations", []):
            line = "%s: axe %s %s (%d node(s), e.g. %s): %s" % (
                where, finding["impact"], finding["rule"], len(finding["targets"]),
                (finding["targets"] or ["?"])[0], finding["help"])
            waiver = waiver_for(finding, result["view"], result["theme"], waivers, result.get("state"))
            if waiver:
                counts["waived"] += 1
                notes.append(line + " [waived: %s]" % waiver["reason"])
            elif finding["impact"] in BLOCKING_IMPACTS:
                counts["blocking"] += 1
                blocking.append(line)
            else:
                counts["reported"] += 1
                notes.append(line)
    ok = not blocking
    summary = "%d view(s), %d screenshot(s), %d blocking, %d reported, %d waived" % (
        counts["views"], counts["shots"], len(blocking), counts["reported"], counts["waived"])
    return ok, summary, blocking + notes + list(run_notes)


# --------------------------------------------------------------- report

def write_report(app, results, ok, summary, details, axe_version, out_dir):
    """Write report.json (for tools) and report.md (for the reviewer); return their paths."""
    os.makedirs(out_dir, exist_ok=True)
    json_path = os.path.join(out_dir, "report.json")
    with open(json_path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump({"app": app, "ok": ok, "summary": summary, "details": details,
                   "axe_version": axe_version, "results": results}, handle, indent=2)
    md_path = os.path.join(out_dir, "report.md")
    lines = ["# UX audit: %s" % app, "",
             "%s. axe-core %s, WCAG 2.2 A/AA rules." % (summary, axe_version), "",
             "| View | Theme asked | Theme drawn | Screenshot | Errors | axe findings |",
             "| --- | --- | --- | --- | --- | --- |"]
    for r in results:
        if r.get("skipped") or r.get("error"):
            lines.append("| %s | %s | - | - | %s | - |" % (label(r), r["theme"], r.get("error") or "skipped"))
            continue
        lines.append("| %s | %s | %s | `%s` | %d page, %d console | %d |" % (
            label(r), r["theme"], r.get("rendered_theme") or "?", paths.display(r["screenshot"]),
            len(r.get("page_errors", [])), len(r.get("console", [])), len(r.get("violations", []))))
    lines += ["", "## Details", ""] + ["- %s" % d for d in details or ["None."]]
    with open(md_path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(lines) + "\n")
    return json_path, md_path


def axe_version():
    """The vendored axe-core version, or "missing"."""
    try:
        with open(os.path.join(AXE_DIR, "VERSION"), "r", encoding="utf-8") as handle:
            return handle.read().strip()
    except OSError:
        return "missing"


# --------------------------------------------------------------- browser

# Walk up from the scope element to the first opaque background: that is what
# a person sees behind the app's content, whatever theme mechanism drew it.
_BACKGROUND_JS = """(selector) => {
    let node = document.querySelector(selector);
    while (node && node.nodeType === 1) {
        const bg = getComputedStyle(node).backgroundColor;
        const m = bg.match(/rgba?\\(([^)]+)\\)/);
        const parts = m ? m[1].split(/[ ,\\/]+/).filter(Boolean) : [];
        if (parts.length === 3 || (parts.length === 4 && parseFloat(parts[3]) > 0.5)) { return bg; }
        node = node.parentElement;
    }
    return getComputedStyle(document.body).backgroundColor;
}"""

# axe is evaluated through the browser's debugging protocol, which Splunk Web's
# Content Security Policy does not apply to (a <script> tag would be blocked).
_AXE_RUN_JS = """async ([selector, tags]) => {
    const result = await axe.run(selector, {runOnly: {type: "tag", values: tags}, resultTypes: ["violations"]});
    return {violations: result.violations.map(v => ({
        id: v.id, impact: v.impact, help: v.help, helpUrl: v.helpUrl,
        nodes: v.nodes.slice(0, 20).map(n => ({target: n.target, failureSummary: n.failureSummary}))}))};
}"""


def _load_axe_source():
    if not os.path.isfile(AXE_PATH):
        raise config.ConfigError("axe-core is missing at %s; run python scripts/vendor_axe.py"
                                 % paths.display(AXE_PATH))
    with open(AXE_PATH, "r", encoding="utf-8") as handle:
        return handle.read()


def _open_state(web, page, state, timeout_ms):
    """Click through to a state of an open view; raise UiError naming the step that failed."""
    from splk import ui

    for selector in state["click"]:
        try:
            page.locator(selector).first.click(timeout=timeout_ms)
        except Exception as exc:  # noqa: BLE001 - Playwright's TimeoutError/Error
            raise ui.UiError("state %s: could not click %r (%s)" % (
                state["name"], selector, (str(exc).strip().splitlines() or ["?"])[0]))
    if state.get("ready"):
        try:
            page.wait_for_selector(state["ready"], state="visible", timeout=timeout_ms)
        except Exception:  # noqa: BLE001 - Playwright's TimeoutError
            raise ui.UiError("state %s never showed %r" % (state["name"], state["ready"]))
    if state.get("settle_ms", 500):
        page.wait_for_timeout(state.get("settle_ms", 500))
    # A click scrolls its target into view, and a full-page screenshot then
    # draws fixed elements (a side panel, Splunk's nav) part-way down the page.
    page.evaluate("window.scrollTo(0, 0)")


def audit_view(web, app, view, theme, settings, out_dir, axe_source, state=None):
    """Open one view (or one state of it) in one theme; return its result dict (never raises UiError)."""
    from splk import ui

    result = {"view": view, "theme": theme, "scope": settings["scope"]}
    if state:
        result["state"] = state["name"]
    if settings.get("skip"):
        result["skipped"] = True
        return result
    page = web.new_page()
    try:
        try:
            params = urllib.parse.parse_qsl(state.get("query") or "") if state else None
            web.open_view(page, app, view, theme=theme, ready_selector=settings.get("ready"),
                          settle_ms=settings.get("settle_ms") or 0, params=params)
            if state:
                _open_state(web, page, state, web.timeout_ms)
        except ui.UiError as exc:
            result["error"] = str(exc)
            return result
        result["final_url"] = page.url
        name = view + ("-" + state["name"] if state else "")
        shot = os.path.join(out_dir, "%s-%s.png" % (ui.slug(name), theme))
        result["screenshot"] = web.screenshot(page, shot)
        if not page.query_selector(settings["scope"]):
            result["error"] = "scope selector %r not found on the page; fix it in %s" % (
                settings["scope"], paths.display(config_path(app)))
            return result
        # Errors are copied before axe is injected, so they describe the app alone.
        # Each console entry keeps its source URL: that is how the app's own
        # errors are told apart from Splunk Web's (own_console_errors).
        page_log = web.page_log(page)
        result["page_errors"] = list(page_log.page_errors)
        result["console"] = [dict(e) for e in page_log.console_entries]
        console = result["console"]
        result["rendered_theme"] = theme_of(page.evaluate(_BACKGROUND_JS, settings["scope"]))
        page.evaluate(axe_source)
        result["violations"] = flatten_violations(page.evaluate(_AXE_RUN_JS, [settings["scope"], AXE_TAGS]))
        log.info("%s [%s]: drew %s, %d axe finding(s), %d page error(s), %d console error(s)",
                 label(result), theme, result["rendered_theme"], len(result["violations"]),
                 len(result["page_errors"]), len(console))
        return result
    finally:
        page.close()


class ThemeSwitch(object):
    """Sets the signed-in user's theme preference for each audit pass, then puts it back.

    A page that follows the preference (both of easyadmin's do) reloads
    itself out of any other ``?theme=``, so before this the audit covered one
    theme only, and light went unaudited for five releases (#38 to #57).
    The change goes through a Sandbox. The original value is also written to
    ``pending_path`` before the first change, so an audit that is killed is
    repaired when the next one starts.
    """

    def __init__(self, client, user, pending_path):
        self.client = client
        self.user = user
        self.pending_path = pending_path
        self.box = None

    def __enter__(self):
        from splk import sandbox
        self._recover()
        self.box = sandbox.Sandbox(self.client)
        return self

    def set(self, theme):
        """Make ``theme`` the user's preference. Raises SplunkError or ValueError."""
        from splk import sandbox
        if not os.path.isfile(self.pending_path):
            current = sandbox.read_user_prefs(self.client, self.user)
            if current is None:
                raise ValueError("user %s has no user-prefs" % self.user)
            original = "" if current.get("theme") is None else str(current["theme"])
            os.makedirs(os.path.dirname(self.pending_path), exist_ok=True)
            with open(self.pending_path, "w", encoding="utf-8") as handle:
                json.dump({"user": self.user, "theme": original}, handle)
        self.box.set_user_prefs(self.user, theme=theme)

    def __exit__(self, *exc_info):
        from splk import sandbox
        try:
            self.box.cleanup()
        except sandbox.SandboxError as exc:
            # The pending file stays, so the next audit tries again.
            log.warning("Could not put back the theme preference of %s: %s", self.user, exc)
            return False
        if os.path.isfile(self.pending_path):
            os.remove(self.pending_path)
        return False

    def _recover(self):
        from splk import sandbox
        if not os.path.isfile(self.pending_path):
            return
        with open(self.pending_path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        sandbox.write_user_prefs(self.client, data["user"], {"theme": data["theme"]})
        log.warning("Put back the theme preference of %s (%r) left changed by an interrupted audit",
                    data["user"], data["theme"])
        os.remove(self.pending_path)


def theme_switch_for(target, environ=None, state_dir=None):
    """(ThemeSwitch, None), or (None, why not) when the preference cannot be switched.

    The REST client uses the target's token, as every live test does; the
    user is the one Splunk Web signs in as.
    """
    from splk import rest, ui
    environ = os.environ if environ is None else environ
    user = environ.get(target.web_user_env)
    if not getattr(target, "token", None):
        return None, "no token for target %s" % target.name
    if not user:
        return None, "$%s is not set" % target.web_user_env
    pending = os.path.join(state_dir or ui.STATE_DIR, "ux-theme-%s-pending.json" % target.name)
    return ThemeSwitch(rest.SplunkClient(target), user, pending), None


def run_audit(app, target, headed=False, views=None, themes=THEMES, out_dir=None, ui_dir=None,
              apps_dir=None, environ=None, state_dir=None, theme_switch=None):
    """Audit ``views`` (default: all) of ``app`` in ``themes``; return (ok, summary, details, report_md).

    Each theme is one pass over every view and its states, with the signed-in
    user's theme preference set to it first (``theme_switch``, default from
    ``theme_switch_for``) and put back at the end.
    """
    from splk import ui
    from splk.rest import SplunkError

    cfg = load_config(app, ui_dir)
    known = discover_views(app, apps_dir)
    unknown = sorted(set(cfg["views"]) - set(known))
    if unknown:
        # A stale section usually means a renamed view whose settings now apply to nothing.
        raise UxConfigError("%s names view(s) the app does not have: %s" % (
            paths.display(config_path(app, ui_dir)), ", ".join(unknown)))
    views = views or known
    out_dir = out_dir or os.path.join(REPORTS_DIR, app)
    axe_source = _load_axe_source()
    results, run_notes = [], []
    if theme_switch is None:
        theme_switch, why_not = theme_switch_for(target, environ, state_dir)
        if why_not:
            run_notes.append("theme preference not switched (%s): a page that follows it is audited "
                             "in that theme only" % why_not)
    switching = theme_switch is not None
    with ui.SplunkWeb(target, headed=headed, environ=environ, state_dir=state_dir) as web, \
            (theme_switch or contextlib.nullcontext()):
        for theme in themes:
            if switching:
                try:
                    theme_switch.set(theme)
                except (SplunkError, ValueError) as exc:
                    switching = False
                    run_notes.append("theme preference not switched (%s): a page that follows it is "
                                     "audited in that theme only" % exc)
            for view in views:
                settings = view_settings(cfg, view)
                results.append(audit_view(web, app, view, theme, settings, out_dir, axe_source))
                for state in settings["states"]:
                    results.append(audit_view(web, app, view, theme, settings, out_dir, axe_source, state))
    ok, summary, details = summarise(app, results, cfg["waive"], run_notes)
    _json_path, md_path = write_report(app, results, ok, summary, details, axe_version(), out_dir)
    return ok, summary, details, md_path
