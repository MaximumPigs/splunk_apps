"""Command-line interface for splk.

Exit codes are part of the contract with the coding agent and CI:

* 0  every stage passed
* 1  a stage failed (details on stderr, in the run log, and in --json output)
* 2  usage or configuration error (bad target, missing token, unknown app)
"""

import argparse
import json
import sys

from splk import __version__, config, stages, ux
from splk.logs import setup_logging
from splk.rest import SplunkClient, SplunkError

EXIT_OK, EXIT_FAILED, EXIT_USAGE = 0, 1, 2


def _emit(args, results):
    """Print stage results as JSON on stdout when --json was given."""
    if getattr(args, "json", False):
        print(json.dumps([r.as_dict() for r in results], indent=2))
    return EXIT_OK if all(r.ok for r in results) else EXIT_FAILED


def _check_app(app):
    """Fail fast with a usage error for an app that does not exist."""
    known = stages.discover_apps()
    if app not in known:
        raise config.ConfigError("Unknown app %r. Apps: %s" % (app, ", ".join(known) or "(none)"))


def _apps_from(args):
    """Resolve the app arguments, expanding --all."""
    if getattr(args, "all", False):
        return stages.discover_apps()
    for app in args.app:
        _check_app(app)
    return args.app


# ------------------------------------------------------------------ commands

def cmd_doctor(args, log):
    """Check the target is reachable, the token works, and report its version."""
    target = config.resolve_target(args.target)
    log.info("Target: %s", target.describe())
    try:
        info = SplunkClient(target, timeout=args.timeout).server_info()
    except SplunkError as exc:
        log.error("Target unreachable or token rejected: %s", exc)
        if args.json:
            print(json.dumps({"target": target.name, "ok": False, "error": str(exc)}))
        return EXIT_FAILED
    result = {
        "target": target.name,
        "ok": True,
        "version": info.get("version"),
        "server_name": info.get("serverName"),
        "os": info.get("os_name"),
    }
    log.info("Splunk %s on %s (%s)", result["version"], result["server_name"], result["os"])
    if args.json:
        print(json.dumps(result))
    return EXIT_OK


def cmd_build(args, log):
    results = [stages.build(app) for app in _apps_from(args)]
    return _emit(args, results)


def cmd_inspect(args, log):
    results = []
    for app in _apps_from(args):
        built = stages.build(app, command="inspect")
        results.append(built)
        if built.ok:
            results.append(stages.inspect(app, built.artifact))
    return _emit(args, results)


def cmd_deploy(args, log):
    target = config.resolve_target(args.target)
    results = []
    for app in _apps_from(args):
        built = stages.build(app, command="deploy")
        results.append(built)
        if built.ok:
            results.append(stages.deploy(app, built.artifact, target, restart=args.restart))
    return _emit(args, results)


def cmd_test(args, log):
    """Unit tests always; live tests with --live and browser tests with --ui (they need a target)."""
    results = [stages.unit_tests(command="test")]
    if args.live or args.ui:
        # Browser tests sign in with a password, not the token, so only
        # --live insists on one.
        target = config.resolve_target(args.target, require_token=args.live)
        for app in _apps_from(args):
            if args.live:
                results.append(stages.live_tests(app, target))
            if args.ui:
                results.append(stages.ui_tests(app, target, headed=args.headed))
    return _emit(args, results)


def cmd_dev(args, log):
    """The full loop for one app, stopping at the first failing stage.

    build -> unit tests -> AppInspect -> deploy -> live tests -> UI tests -> UX audit

    The UI stage runs only for apps that have tests/ui/<app>, and the UX
    audit only for apps that ship views.
    """
    _check_app(args.app)
    target = config.resolve_target(args.target)
    app, results = args.app, []

    def run(result):
        results.append(result)
        return result.ok

    ok = run(stages.build(app, command="dev"))
    ok = ok and run(stages.unit_tests(app, command="dev"))
    if ok and not args.skip_inspect:
        ok = run(stages.inspect(app, results[0].artifact, command="dev"))
    ok = ok and run(stages.deploy(app, results[0].artifact, target, restart=args.restart, command="dev"))
    ok = ok and run(stages.live_tests(app, target, command="dev"))
    if stages.has_ui_tests(app):
        ok = ok and run(stages.ui_tests(app, target, headed=args.headed, command="dev"))
    if ux.has_views(app):
        # Last: the audit screenshots every view, which is only worth doing
        # once the functional tests say the pages work.
        ok = ok and run(stages.ux_audit(app, target, headed=args.headed, command="dev"))
    log.info("dev %s: %s", app, "GREEN" if ok else "RED (see the failing stage above)")
    return _emit(args, results)


def cmd_search(args, log):
    """Run one SPL query on the target and print rows as JSON.

    For exploration and debugging. Assertions belong in tests/live, not here.
    """
    target = config.resolve_target(args.target)
    try:
        rows = SplunkClient(target, timeout=args.timeout).oneshot(
            args.spl, earliest=args.earliest, latest=args.latest,
        )
    except SplunkError as exc:
        log.error("%s", exc)
        return EXIT_FAILED
    print(json.dumps(rows[: args.limit], indent=2))
    log.info("%d row(s)%s", len(rows), " (truncated)" if len(rows) > args.limit else "")
    return EXIT_OK


def cmd_shot(args, log):
    """Open one Splunk Web page in a browser, save a screenshot, report errors.

    The browser counterpart of `splk search`: for looking, not asserting. The
    agent opens the PNG to see the page; checks that must keep passing belong
    in tests/ui/<app>/.
    """
    import os

    from splk import ui

    target = config.resolve_target(args.target, require_token=False)
    path, app, view = ui.parse_page_spec(args.page)
    if path is None:
        path = ui.view_path(app, view, args.theme)
    elif args.theme:
        path += ("&" if "?" in path else "?") + "theme=" + args.theme
    out = args.out or os.path.join(
        ui.REPORTS_DIR, "shots", "%s%s.png" % (ui.slug(args.page), "-" + args.theme if args.theme else ""))
    try:
        with ui.SplunkWeb(target, headed=args.headed, timeout_ms=args.timeout * 1000) as web:
            page = web.new_page()
            web.open(page, path, ready_selector=args.wait_for, settle_ms=args.settle)
            web.screenshot(page, out, full_page=not args.viewport_only)
            result = {"url": web.url(path), "final_url": page.url, "title": page.title(),
                      "screenshot": os.path.abspath(out)}
            result.update(web.page_log(page).as_dict())
    except ui.UiError as exc:
        log.error("%s", exc)
        return EXIT_FAILED
    # The JSON is the command's output (like `splk search`), so it is always printed.
    print(json.dumps(result, indent=2))
    errors = len(result["console_errors"]) + len(result["page_errors"])
    log.info("%s: %d console/page error(s)", result["final_url"], errors)
    return EXIT_OK


def cmd_ux(args, log):
    """Audit an app's views in a browser: screenshots in both themes, accessibility, errors.

    Writes build/reports/ux/<app>/report.md for the ux-reviewer. Fails on what
    a machine can judge (see splk.ux); the rest is for review.
    """
    _check_app(args.app)
    target = config.resolve_target(args.target, require_token=False)
    themes = (args.theme,) if args.theme else None
    return _emit(args, [stages.ux_audit(args.app, target, headed=args.headed, views=args.view, themes=themes)])


# Run-log stage for each kind of agent review (read by the Stop hook).
REVIEW_STAGES = {"security": "security", "ux": "ux-review"}


def cmd_review(args, log):
    """Record the outcome of an agent review (e.g. security) in the run log.

    Reviews are done by an agent, not by splk, but recording them here gives
    them the same evidence trail as every other stage: the Stop hook knows
    when code was last reviewed, and a review that failed and later passed is
    a fixed failure the retro picks up like any other.
    """
    from splk import runlog

    ok = args.result == "pass"
    # "ux" alone is the automated audit's stage, so the reviewer's verdict is
    # recorded as "ux-review"; security keeps its original stage name.
    stage = REVIEW_STAGES[args.kind]
    entry = runlog.record("review", args.scope, stage, ok, args.summary, args.detail or [])
    (log.info if ok else log.error)("[%s] %s: %s", args.kind, "PASS" if ok else "FAIL", args.summary)
    if args.json:
        print(json.dumps(entry, indent=2))
    return EXIT_OK


def cmd_runs(args, log):
    """Print recent stage results from the run log, oldest first.

    Feeds the retro skill and is handy for "what failed last time?".
    """
    import time

    from splk import runlog

    entries = runlog.read_since(time.time() - args.days * 86400)[-args.last:]
    if args.json:
        print(json.dumps(entries, indent=2))
        return EXIT_OK
    for entry in entries:
        print("%s %-4s %-15s %-8s %s" % (
            entry.get("ts"), "ok" if entry.get("ok") else "FAIL",
            entry.get("app"), entry.get("stage"), entry.get("summary")))
        if not entry.get("ok"):
            for line in entry.get("details", [])[:5]:
                print("    " + line)
    return EXIT_OK


# -------------------------------------------------------------------- parser

def build_parser():
    parser = argparse.ArgumentParser(prog="splk", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--version", action="version", version="splk %s" % __version__)

    def add_common(target_parser, suppress):
        """Options valid before or after the subcommand (`splk --json dev x` == `splk dev x --json`).

        On subparsers the defaults are SUPPRESSed so an option given before
        the subcommand is not reset to its default by the subparser.
        """
        default = (lambda value: argparse.SUPPRESS) if suppress else (lambda value: value)
        target_parser.add_argument("-v", "--verbose", action="store_true", default=default(False),
                                   help="debug output on stderr")
        target_parser.add_argument("--json", action="store_true", default=default(False),
                                   help="machine-readable results on stdout")
        target_parser.add_argument("--target", default=default(None),
                                   help="target name from config/targets.toml (default: default_target)")
        target_parser.add_argument("--timeout", type=int, default=default(60), help="REST timeout in seconds")

    add_common(parser, suppress=False)
    common = argparse.ArgumentParser(add_help=False)
    add_common(common, suppress=True)

    sub = parser.add_subparsers(dest="command")
    sub.required = True
    _add_parser = sub.add_parser

    def add_parser(name, **kwargs):
        # Every subcommand inherits the common options.
        return _add_parser(name, parents=[common], **kwargs)
    sub.add_parser = add_parser

    p = sub.add_parser("doctor", help="check the target is reachable and the token works")
    p.set_defaults(func=cmd_doctor)

    for name, func, text in (
        ("build", cmd_build, "package apps into dist/"),
        ("inspect", cmd_inspect, "build, then run AppInspect (full check set)"),
        ("deploy", cmd_deploy, "build, then install on the target via REST"),
    ):
        p = sub.add_parser(name, help=text)
        p.add_argument("app", nargs="*", help="app id(s) under apps/")
        p.add_argument("--all", action="store_true", help="every app")
        if name == "deploy":
            p.add_argument("--restart", action="store_true",
                           help="restart splunkd if required (target must allow it)")
        p.set_defaults(func=func)

    p = sub.add_parser("test", help="unit tests, plus live tests with --live")
    p.add_argument("app", nargs="*", help="app id(s) for live tests")
    p.add_argument("--all", action="store_true", help="live-test every app")
    p.add_argument("--live", action="store_true", help="also run tests/live/<app> on the target")
    p.add_argument("--ui", action="store_true", help="also run tests/ui/<app> in a browser on Splunk Web")
    p.add_argument("--headed", action="store_true", help="show the browser window during UI tests")
    p.set_defaults(func=cmd_test)

    p = sub.add_parser("dev", help="full loop: build, unit, inspect, deploy, live, ui, ux")
    p.add_argument("app", help="app id under apps/")
    p.add_argument("--skip-inspect", action="store_true", help="skip AppInspect for a faster inner loop")
    p.add_argument("--restart", action="store_true", help="allow a splunkd restart if required")
    p.add_argument("--headed", action="store_true", help="show the browser window during UI tests")
    p.set_defaults(func=cmd_dev)

    p = sub.add_parser("shot", help="screenshot a Splunk Web page and report its console errors")
    p.add_argument("page", help="<app>, <app>/<view>, or a Splunk Web path such as /manager/launcher/apps/local")
    p.add_argument("--theme", choices=("light", "dark"), help="add ?theme= (how Classic dashboards take a theme)")
    p.add_argument("--wait-for", metavar="SELECTOR", help="CSS selector that appears once the page is ready")
    p.add_argument("--settle", type=int, default=1500, metavar="MS",
                   help="extra wait after load for panels to render (default 1500)")
    p.add_argument("--out", help="PNG path (default build/reports/ui/shots/<page>.png)")
    p.add_argument("--viewport-only", action="store_true", help="capture the viewport, not the full page")
    p.add_argument("--headed", action="store_true", help="show the browser window")
    p.set_defaults(func=cmd_shot)

    p = sub.add_parser("ux", help="audit every view: screenshots in both themes, accessibility, JS errors")
    p.add_argument("app", help="app id under apps/")
    p.add_argument("--view", action="append", help="only this view (repeatable; default every view)")
    p.add_argument("--theme", choices=("light", "dark"), help="only this theme (default both)")
    p.add_argument("--headed", action="store_true", help="show the browser window")
    p.set_defaults(func=cmd_ux)

    p = sub.add_parser("search", help="run one SPL query on the target")
    p.add_argument("spl", help="the query")
    p.add_argument("--earliest", default="-24h")
    p.add_argument("--latest", default="now")
    p.add_argument("--limit", type=int, default=50, help="max rows printed")
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("review", help="record an agent review's outcome (security or ux) in the run log")
    p.add_argument("kind", choices=("security", "ux"), help="which review")
    p.add_argument("scope", help="app id, path or 'branch' that was reviewed")
    p.add_argument("result", choices=("pass", "fail"),
                   help="fail when any finding should be fixed before merging")
    p.add_argument("--summary", required=True, help="one line, e.g. '2 high, 1 low'")
    p.add_argument("--detail", action="append", help="one finding per flag: '[HIGH] path:line title'")
    p.set_defaults(func=cmd_review)

    p = sub.add_parser("runs", help="show recent stage results from the run log")
    p.add_argument("--last", type=int, default=40, help="number of entries")
    p.add_argument("--days", type=int, default=7, help="how far back to look")
    p.set_defaults(func=cmd_runs)
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    log = setup_logging(verbose=args.verbose)
    # .env is loaded for every command so tokens never need exporting by hand.
    config.load_env_file()
    log.debug("splk %s: %s", __version__, " ".join(argv if argv is not None else sys.argv[1:]))
    try:
        return args.func(args, log)
    except config.ConfigError as exc:
        log.error("%s", exc)
        return EXIT_USAGE
    except KeyboardInterrupt:
        log.error("Interrupted")
        return EXIT_FAILED


if __name__ == "__main__":
    sys.exit(main())
