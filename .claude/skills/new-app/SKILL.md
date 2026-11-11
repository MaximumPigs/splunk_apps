---
name: new-app
description: Scaffold a new Splunk app in apps/<app-id>/ that passes AppInspect and the dev loop from its first commit. Use when the person asks for a new app or add-on.
argument-hint: "[app-id] [one-line purpose]"
disable-model-invocation: true
---

# New app `$ARGUMENTS`

Confirm with the person before creating: the app id (short, lowercase,
underscores), the Splunkbase display name
(`(Company | Brand | Author) [solution] (App | Add-on | Connector)`), and
whether it ships views (App) or not (Add-on).

## Create

Model every file on `apps/fillcontinuous/`, which already passes the full
AppInspect set; copy its comments' reasoning, not its command-specific content.

```
apps/<app>/
  default/app.conf        [install] is_configured=false, [package] id, [id] + [launcher] same version 1.0.0, [ui] label
  metadata/default.meta   export only what other apps need
  app.manifest            info.title == [ui] label
  README.md               what it does, how to use it, settings
  LICENSE                 copy the repo's
  bin/<app>_core.py       only if it has Python; pure logic, unit-tested
tests/test_<app>_core.py  if bin/ exists
tests/live/<app>/test_<app>_live.py   at least one live test
splunkbase/<app>/listing.md           if it will be published
```

Add the app to the table in the root `README.md`.

## Verify

1. `splk build <app>` then `splk inspect <app>`: fix to green (`appinspect-fix`).
2. `splk dev <app>`: green including the live test.
3. CI discovers the app automatically via `default/app.conf`; no workflow edits.
