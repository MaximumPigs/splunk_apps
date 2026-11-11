"""Command-line interface for splk.

Exit codes are part of the contract with Claude Code and CI:

* 0  every stage passed
* 1  a stage failed (details on stderr, in the run log, and in --json output)
* 2  usage or configuration error (bad target, missing token, unknown app)
"""

import argparse
import json
import sys

from splk import __version__, config, stages
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
    """Unit tests always; live tests only with --live (they need a target)."""
    results = [stages.unit_tests(command="test")]
    if args.live:
        target = config.resolve_target(args.target)
        for app in _apps_from(args):
            results.append(stages.live_tests(app, target))
    return _emit(args, results)


def cmd_dev(args, log):
    """The full loop for one app, stopping at the first failing stage.

    build -> unit tests -> AppInspect -> deploy -> live tests
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
    p.set_defaults(func=cmd_test)

    p = sub.add_parser("dev", help="full loop: build, unit, inspect, deploy, live")
    p.add_argument("app", help="app id under apps/")
    p.add_argument("--skip-inspect", action="store_true", help="skip AppInspect for a faster inner loop")
    p.add_argument("--restart", action="store_true", help="allow a splunkd restart if required")
    p.set_defaults(func=cmd_dev)

    p = sub.add_parser("search", help="run one SPL query on the target")
    p.add_argument("spl", help="the query")
    p.add_argument("--earliest", default="-24h")
    p.add_argument("--latest", default="now")
    p.add_argument("--limit", type=int, default=50, help="max rows printed")
    p.set_defaults(func=cmd_search)

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
