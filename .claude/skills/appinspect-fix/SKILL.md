---
name: appinspect-fix
description: Diagnose and fix AppInspect failures, errors and unreviewed manual checks for an app. Use when the inspect stage of splk is red.
argument-hint: "[app-id]"
---

# Fix AppInspect findings

1. Run `splk inspect <app> --json` and read the `details` of the inspect stage.
   The full report is `build/reports/appinspect-<app>.json`; each check has
   `name`, `result`, `messages[].message` and often a file and line.
2. Fix the cause in `apps/<app>/`, not the symptom. Never waive a failure to go
   green.
3. **failure / error**: must be fixed. A waiver in `.appinspect.expect.yaml`
   needs a Splunk ticket id (ADDON-n or APPCERT-n); only the person adds one.
4. **manual_check**: read what the check asks, verify it in the code, then add
   it to `.appinspect.manualcheck.yaml` with a comment saying what you verified
   and the date. Never add an entry you did not actually verify.
5. **future_failure** (logged as a warning): fix now if cheap; it becomes a
   failure in a later AppInspect release.
6. The run is deliberately untagged (full check set). Do not add
   `--included-tags cloud`: `check_for_updates_disabled` is tagged
   `private_app`, and a cloud-only run let a Splunkbase-rejected package through.
7. Re-run `splk inspect <app>` until green, then `splk dev <app>`.
8. Record anything non-obvious with the `retro` skill.
