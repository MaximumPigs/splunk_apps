---
name: dev-loop
description: Iterate on a Splunk app until it is green on the local target. Use when changing anything under apps/<app>/ (conf, SPL, dashboards, bin/ scripts) or when asked to fix, test, deploy or verify an app.
argument-hint: "[app-id]"
---

# Dev loop for `$ARGUMENTS`

Current state of the target and recent runs:

!`splk doctor 2>&1`

!`splk runs --last 10`

## Steps

1. Read the `splunk-playbook` pattern for the feature you are building, and
   the lesson index (`.claude/agent-memory/learner/MEMORY.md`) for entries
   about this app or the files you are about to touch.
2. Make the smallest change that moves toward the goal. Unit-testable logic goes
   in `bin/<app>_core.py` with a test in `tests/test_<app>_*.py`.
3. Inner loop: `splk dev <app> --skip-inspect`. Read the first red stage only;
   later stages did not run.
4. When the inner loop is green, run the full `splk dev <app>` (adds AppInspect).
5. If deploy says a restart is required, stop and ask the person before
   `splk dev <app> --restart`. Index-time changes (props line breaking,
   timestamps, transforms) need it; search-time changes usually do not.
6. Behaviour change? Add or extend a live test (use the `write-live-test` skill)
   *before* calling the work done. Visible in Splunk Web? Look with
   `splk shot <app>/<view>` (open the PNG), then add a UI test
   (`write-ui-test`). Build pages to the `splunk-ux` standard.
7. Run `splunk-security-review` on the app and fix what it reports. If a
   view, page script or stylesheet changed, also run `splunk-ux-review`.
8. Run the `retro` skill before finishing: lessons for what failed, patterns
   for what worked, especially anything that took more than one attempt.

## Reading failures

| Stage | Where to look |
| --- | --- |
| build | Version mismatch between `[launcher]` and `[id]`, or a missing `default/app.conf`. |
| unit | `build/reports/unit-*.xml`; rerun one test with `pytest tests/<file>::<name> -q`. |
| inspect | `build/reports/appinspect-<app>.json`; use the `appinspect-fix` skill. |
| deploy | `splk doctor` first. "Installed version is X, expected Y" means the overwrite did not apply. |
| live | `build/reports/live-<app>.xml`; reproduce the SPL with `splk search "<spl>"`. |
| ui | `build/reports/ui/<app>/<test>-FAILED.png` (open it) and `<test>-trace.zip` (`python -m playwright show-trace <zip>`). Sign-in failures: ask the person to check `SPLUNK_WEB_*` in `.env`. |
| ux | `build/reports/ux/<app>/report.md` and the screenshots it lists (open them). An axe finding names the rule, a selector and a help link; fix the app, or set `scope` in `tests/ui/<app>/ux.toml` if it is in Splunk's own chrome. Rerun one view with `splk ux <app> --view <view>`. |

Logs: `.agent/logs/splk.log` (JSON lines, debug level). Run history: `.agent/runs/`.
