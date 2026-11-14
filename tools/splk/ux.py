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

import json
import os
import re

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
# so findings are about code this repo can change.
VIEW_DEFAULTS = {"ready": None, "scope": "body", "settle_ms": 1500, "skip": False}


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
    waivers = raw.get("waive") or []
    for number, waiver in enumerate(waivers, 1):
        # A waiver with no reason is how real problems get silenced, so the
        # reason is required, as for AppInspect's expect file.
        if not waiver.get("rule") or not str(waiver.get("reason", "")).strip():
            raise UxConfigError("%s: waiver %d needs both rule and reason" % (where, number))
        bad = set(waiver) - {"rule", "view", "theme", "target", "reason"}
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


def waiver_for(finding, view, theme, waivers):
    """The waiver that accepts this finding on this view and theme, or None.

    A waiver with a ``target`` covers the finding only if every failing node
    matches it, so a new failing element is not hidden by an old waiver.
    """
    for waiver in waivers:
        if waiver["rule"] != finding["rule"]:
            continue
        if waiver.get("view") and waiver["view"] != view:
            continue
        if waiver.get("theme") and waiver["theme"] != theme:
            continue
        if waiver.get("target") and not all(waiver["target"] in t for t in finding["targets"]):
            continue
        return waiver
    return None


def own_console_errors(app, entries):
    """Console errors raised by the app's own static files.

    Splunk Web logs errors of its own on most pages, so blocking on every
    console error would fail every app. An error whose source or text points
    at /static/app/<app>/ is the app's, and that one blocks.
    """
    marker = "/static/app/%s/" % app
    return [e for e in entries if marker in (e.get("url") or "") or marker in (e.get("text") or "")]


def summarise(app, results, waivers):
    """Reduce audit results to (ok, summary, details) for the run log.

    ``details`` lists blocking problems first, then non-blocking notes.
    """
    blocking, notes = [], []
    counts = {"views": len({r["view"] for r in results}), "shots": 0, "blocking": 0, "waived": 0, "reported": 0}
    for result in results:
        where = "%s [%s]" % (result["view"], result["theme"])
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
            blocking.append("%s: console error from the app: %s" % (where, entry.get("text", "")[:200]))
        rendered = result.get("rendered_theme")
        if rendered and rendered != result["theme"]:
            notes.append("%s: page rendered %s (it follows the signed-in user's theme); the %s theme was "
                         "not audited, switch the preference in Splunk Web to cover it"
                         % (where, rendered, result["theme"]))
        for finding in result.get("violations", []):
            line = "%s: axe %s %s (%d node(s), e.g. %s): %s" % (
                where, finding["impact"], finding["rule"], len(finding["targets"]),
                (finding["targets"] or ["?"])[0], finding["help"])
            waiver = waiver_for(finding, result["view"], result["theme"], waivers)
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
    return ok, summary, blocking + notes


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
            lines.append("| %s | %s | - | - | %s | - |" % (r["view"], r["theme"], r.get("error") or "skipped"))
            continue
        lines.append("| %s | %s | %s | `%s` | %d page, %d console | %d |" % (
            r["view"], r["theme"], r.get("rendered_theme") or "?", paths.display(r["screenshot"]),
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


def audit_view(web, app, view, theme, settings, out_dir, axe_source):
    """Open one view in one theme and return its result dict (never raises UiError)."""
    from splk import ui

    result = {"view": view, "theme": theme, "scope": settings["scope"]}
    if settings.get("skip"):
        result["skipped"] = True
        return result
    page = web.new_page()
    console = []

    def on_console(message):
        # Keep where the error came from: that is how the app's own errors
        # are told apart from Splunk Web's (own_console_errors).
        if message.type == "error":
            location = message.location or {}
            console.append({"text": message.text, "url": location.get("url", "")})
    page.on("console", on_console)
    try:
        try:
            web.open_view(page, app, view, theme=theme, ready_selector=settings.get("ready"),
                          settle_ms=settings.get("settle_ms") or 0)
        except ui.UiError as exc:
            result["error"] = str(exc)
            return result
        result["final_url"] = page.url
        shot = os.path.join(out_dir, "%s-%s.png" % (ui.slug(view), theme))
        result["screenshot"] = web.screenshot(page, shot)
        if not page.query_selector(settings["scope"]):
            result["error"] = "scope selector %r not found on the page; fix it in %s" % (
                settings["scope"], paths.display(config_path(app)))
            return result
        # Errors are copied before axe is injected, so they describe the app alone.
        result["page_errors"] = list(web.page_log(page).page_errors)
        result["console"] = list(console)
        result["rendered_theme"] = theme_of(page.evaluate(_BACKGROUND_JS, settings["scope"]))
        page.evaluate(axe_source)
        result["violations"] = flatten_violations(page.evaluate(_AXE_RUN_JS, [settings["scope"], AXE_TAGS]))
        log.info("%s [%s]: drew %s, %d axe finding(s), %d page error(s), %d console error(s)",
                 view, theme, result["rendered_theme"], len(result["violations"]),
                 len(result["page_errors"]), len(console))
        return result
    finally:
        page.close()


def run_audit(app, target, headed=False, views=None, themes=THEMES, out_dir=None, ui_dir=None,
              apps_dir=None, environ=None, state_dir=None):
    """Audit ``views`` (default: all) of ``app`` in ``themes``; return (ok, summary, details, report_md)."""
    from splk import ui

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
    results = []
    with ui.SplunkWeb(target, headed=headed, environ=environ, state_dir=state_dir) as web:
        for view in views:
            for theme in themes:
                results.append(audit_view(web, app, view, theme, view_settings(cfg, view), out_dir, axe_source))
    ok, summary, details = summarise(app, results, cfg["waive"])
    _json_path, md_path = write_report(app, results, ok, summary, details, axe_version(), out_dir)
    return ok, summary, details, md_path
