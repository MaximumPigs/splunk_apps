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
| `splk dev <app>` | Full loop: build, unit tests, AppInspect, deploy, live tests, UI tests (if `tests/ui/<app>/` exists), UX audit (if the app has views). Stops at the first red stage. |
| `splk dev <app> --skip-inspect` | Faster inner loop while iterating on SPL or conf. |
| `splk test` / `splk test --live <app>` | Unit tests only / plus live tests on the target. |
| `splk inspect <app>` | Build and run AppInspect alone. |
| `splk deploy <app> [--restart]` | Build and install on the target. `--restart` always asks the person. |
| `splk search "<spl>"` | Exploratory search. Assertions belong in `tests/live/`, not here. |
| `splk shot <app>/<view> [--theme dark]` | Screenshot a Splunk Web page and list its JS errors. Open the PNG to look. Assertions belong in `tests/ui/`. |
| `splk test --ui <app> [--headed]` | Browser tests in `tests/ui/<app>/` (also a stage of `splk dev`). |
| `splk ux <app> [--view v] [--theme t]` | Every view in light and dark: screenshots, axe-core accessibility scan, JS errors. Report in `build/reports/ux/<app>/`. |
| `splk review security\|ux <scope> pass\|fail` | Record a security or UX review's outcome in the run log (the reviewer runs it). |

Add `--json` for machine-readable results and `-v` for debug logs. Target
config is `config/targets.toml`; the token and the Splunk Web sign-in are in
`.env` (never read or print it).

## Definition of done for an app change

1. `splk dev <app>` is green, including AppInspect with no unreviewed manual checks.
2. New behaviour has a unit test (pure logic) and a live test (real SPL result);
   anything visible in Splunk Web also has a UI test (`write-ui-test`).
3. `[launcher]` and `[id]` versions in `app.conf` match and were bumped if the package changed.
4. README of the app reflects the change.
5. `splunk-security-review` recorded `pass` for the change, or the person was
   told which findings remain and why.
6. For a change users see: the `ux` audit is green and `splunk-ux-review`
   recorded `pass`, or the person was told which findings remain and why.
7. `retro` ran: lessons for what went wrong, playbook patterns for what worked.

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
  Commits must be authored as the owner, not an AI identity: GitHub's squash
  merge turns any other author into a `Co-authored-by` trailer. The bash guard
  denies such commits.
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
- **For UI behaviour, look before you claim.** `splk shot` and UI tests let you
  see the page yourself: open the screenshot and check it. Ask the person only
  for judgement (does it look right) or what the browser cannot reach, and
  say what you already checked.
- **Tests may change the dev target, but only through `sandbox`.** Live and UI
  tests can create users and roles, edit roles and change app permissions;
  the guard snapshots users, roles and app permissions around every test and
  fails any test that leaves a difference (see `write-live-test`).
- **Prove a fix closes the original reproduction**, before and after, not just
  that a new test passes.
- Report what was verified versus inferred, volunteer the gap ("passes
  AppInspect but has never run in Splunk"), state failures with their output,
  and own a wrong diagnosis explicitly.

Path-scoped rules in `.claude/rules/` load when you touch matching files.

## Skills

`dev-loop` (iterate on an app), `splunk-playbook` (proven recipes: read before
building), `new-app` (scaffold), `write-live-test`, `write-ui-test`,
`appinspect-fix`, `splunk-security-review` (forked `security-reviewer` agent),
`splunk-ux` (the UX standard for pages), `splunk-ux-review` (forked
`ux-reviewer` agent), `release-app` (person-invoked), `retro` (debrief:
lessons and patterns).

## Learning loop

Three stores, each with one job:

| Store | Holds | Read |
| --- | --- | --- |
| `.claude/skills/splunk-playbook/` | What works: recipes per feature, with what was tried and failed | Before building a feature |
| `.claude/agent-memory/learner/` | What went wrong: lessons with evidence and hit counts | Before working on an app or area |
| `.claude/rules/`, hooks, tests | What must always hold: promoted from the two above | Automatically |

`splk` records every stage and review result in `.agent/runs/`. The Stop hook
asks for `retro` when a failure was fixed, **and after any session that
deployed an app** (naming apps that took 3+ deploys), and asks for
`splunk-security-review` when code changed after the last review, and
`splunk-ux-review` when a view, page script or stylesheet changed after the
last UX review. A lesson hit
twice becomes a rule or skill; a pattern confirmed in two apps becomes a
scaffold step or check. Promotions are ordinary diffs in a PR, reviewed by the
person.

When something took several attempts or the person had to correct you, run
`retro` even if no stage went red: that is the knowledge worth keeping.
