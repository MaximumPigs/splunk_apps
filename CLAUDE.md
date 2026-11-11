# splunk_apps

Monorepo of Splunk apps. Every app targets Splunk Cloud and must pass the full
AppInspect check set. Read [README.md](README.md) for layout and release flow.

## The one rule

Everything that builds, vets, deploys or tests goes through `splk`. Never call
the Splunk REST API, the `splunk` CLI, or copy into `etc/apps` directly: hooks
deny it, and results outside `splk` are not recorded in the run log.

| Command | What it does |
| --- | --- |
| `splk doctor` | Target reachable? Token valid? Splunk version. Run first if anything fails. |
| `splk dev <app>` | Full loop: build, unit tests, AppInspect, deploy, live tests. Stops at the first red stage. |
| `splk dev <app> --skip-inspect` | Faster inner loop while iterating on SPL or conf. |
| `splk test` / `splk test --live <app>` | Unit tests only / plus live tests on the target. |
| `splk inspect <app>` | Build and run AppInspect alone. |
| `splk deploy <app> [--restart]` | Build and install on the target. `--restart` always asks the person. |
| `splk search "<spl>"` | Exploratory search. Assertions belong in `tests/live/`, not here. |

Add `--json` for machine-readable results and `-v` for debug logs. Target
config is `config/targets.toml`; the token is in `.env` (never read or print it).

## Definition of done for an app change

1. `splk dev <app>` is green, including AppInspect with no unreviewed manual checks.
2. New behaviour has a unit test (pure logic) and a live test (real SPL result).
3. `[launcher]` and `[id]` versions in `app.conf` match and were bumped if the package changed.
4. README of the app reflects the change.

## Conventions

- Python: logging (never print), comments explaining *why*, runs on 3.9 and 3.13.
  App code keeps pure logic in `<app>_core.py` with no splunklib import.
- Conf: only `default/`, never `local/`. LF line endings.
- Module names are shared across apps: prefix helpers with the app id.
- Supported floor: Splunk 9.3. Author `MaximumPigs`, URL `https://github.com/maximumpigs`.
- British spelling in prose. Listing files are ASCII only.

## Owner's rules (non-negotiable)

- **No AI tool or model names** in app files, commit messages or PR
  descriptions, and **no `Co-Authored-By` trailers**. The README's single
  "AI assistance" section is the only such reference. (Agent config paths such
  as this file and `.claude/` are the exception, because the tool requires them.)
- Commit messages concise but meaningful.
- Feature branch, PR, green CI, **squash merge** with an explicit subject and
  body file. Never push to `main`. **Ask before pushing.**
- Never write repository files with PowerShell (see the Windows rule).

## How to work here

- **Verify against source, not documentation or metadata.** Read the SDK, the
  action's entrypoint, the actual file. Docs and PyPI metadata have been wrong.
- **Never assert behaviour you have not observed.** A one-line `splk search`
  settles most questions in seconds; three past defects were confident,
  untested claims.
- **Prove a fix closes the original reproduction**, before and after, not just
  that a new test passes.
- Report what was verified versus inferred, volunteer the gap ("passes
  AppInspect but has never run in Splunk"), state failures with their output,
  and own a wrong diagnosis explicitly.

Path-scoped rules in `.claude/rules/` load when you touch matching files.

## Skills

`dev-loop` (iterate on an app), `new-app` (scaffold), `write-live-test`,
`appinspect-fix`, `release-app` (person-invoked), `retro` (record a lesson after
fixing a failure).

## Learning loop

`splk` records every stage result in `.agent/runs/`. When a failure you fixed
this session is unrecorded, the Stop hook asks for `retro`. Lessons live in
`.claude/agent-memory/learner/`. A lesson hit twice is promoted into a rule or
skill; one that must never recur becomes a hook or a test. Promotions are
ordinary diffs in a PR, reviewed by the person.

Before working on an app, check the lesson index for that app or area.
