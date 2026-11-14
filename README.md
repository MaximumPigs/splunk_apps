# splunk_apps

A monorepo of Splunk apps, each independently validated, packaged and released.

Every app targets **Splunk Cloud Platform** and is built to pass **AppInspect**
Cloud vetting.

## Apps

| App ID | Splunkbase name | What it does |
| --- | --- | --- |
| [`fillcontinuous`](apps/fillcontinuous/) | MaximumPigs fillcontinuous Add-on | Fills the missing time buckets that `timechart` and `makecontinuous` cannot, across any number of group-by fields. Registers `fillcontinuous` and the alias `fillgaps`. |
| [`easyadmin`](apps/easyadmin/) | MaximumPigs Easy Admin App | An admin page for bulk-editing settings with the logged-in user's own permissions. Role management: every role's indexes, capabilities, inheritance and other settings in tabbed grids, saved in one submit. App management: every app's knowledge objects in boxes, moved by drag and drop, re-permissioned or deleted in bulk, applied at once. |

Splunkbase requires the display name to follow
`(Company | Brand | Author) [solution] (App | Add-on | Connector)`, and to match
`[ui] label` in `app.conf` exactly — so the two columns above differ on purpose.
The app **ID** is unconstrained by that and stays short and lowercase. Change
one of `app.conf` label, `app.manifest` title, or the listing, and change all
three.

## Layout

```
apps/<app>/            one directory per app, named for its app id
  bin/                 command scripts; <app>_core.py holds testable logic
  default/             app.conf, commands.conf, searchbnf.conf
  lib/                 vendored Python dependencies (splunklib)
  metadata/            default.meta
  app.manifest
  README.md
  LICENSE
scripts/               packaging and dependency vendoring
splunkbase/<app>/      listing copy for the app's Splunkbase page
tests/                 pytest suite covering every app's core logic
tests/live/<app>/      live tests run against a Splunk target by splk
tools/splk/            the splk CLI: build, inspect, deploy, live test
config/targets.toml    Splunk targets for splk (no secrets)
.claude/               coding-agent rules, skills, agents, hooks and lessons
.github/workflows/     CI and release automation
```

[`splunkbase/`](splunkbase/) sits outside `apps/` on purpose: the packager walks
`apps/<app>/` and nothing else, so listing copy cannot end up inside a `.spl`.

`apps/<app>/default/app.conf` is what marks a directory as an app: CI discovers
apps by looking for it, so a new app is picked up with no workflow changes.

## Developing

Requires Python 3.9 or later.

```bash
pip install -r requirements-dev.txt
pytest
```

Tests import each app's `bin/` directory directly, the same way Splunk makes a
command's own directory importable. Keep the pure logic in a module with no
`splunklib` import so it stays testable without a Splunk install — see
[`fillcontinuous_core.py`](apps/fillcontinuous/bin/fillcontinuous_core.py) — and
keep the `splunklib` wrapper thin.

Because module names share one namespace across apps, prefix helper modules with
the app name.

### Python version policy

Apps must run on **both** Python 3.9 and 3.13, and CI tests both:

- **3.9** is Splunk's LTS runtime, the default, and the fallback on 10.2+.
- **3.13** is the opt-in runtime introduced in Splunk 10.2.

So `commands.conf` declares both settings:

```ini
python.version = python3        # read by Splunk 10.0 and 10.1
python.required = 3.9, 3.13     # read by Splunk 10.2+, picks the highest available
```

Practically, that rules out 3.10+ syntax: no `match` statements, no `X | Y`
annotations. CI byte-compiles every script under 3.9 to catch these before they
reach a search head.

### Vendoring dependencies

Splunk does not provide `splunklib` to apps, so each app bundles its own copy in
`lib/`. The vendored code is committed, so CI and packaging need no network.

```bash
python scripts/vendor_splunklib.py fillcontinuous
```

**The `ai/` subpackage is excluded deliberately.** splunk-sdk 3.0.0 declares
`requires_python >= 3.13`, which would break the moment Splunk falls back to its
3.9 LTS runtime. But the only 3.13-only syntax in the SDK — `match` statements —
is confined to `splunklib/ai/`, the LLM integration. Nothing outside it imports
it, and everything else parses cleanly on 3.9. Omitting it satisfies
AppInspect's `check_python_sdk_version`, which wants 3.0.0 or later, without
giving up the 3.9 runtime.

> `lib/` is deliberately **not** in `.gitignore`. The stock GitHub Python
> template ignores it, which would silently ship apps that cannot import
> `splunklib`. If you regenerate `.gitignore`, remove that line again.

## Local development loop: `splk` and the coding agent

`splk` is the one entry point for building, vetting, deploying and testing an
app against a live Splunk instance. Humans, the coding agent and CI run the same
commands, so a result in one place reproduces in the others.

### Setup

```bash
pip install -e ".[dev]"         # puts `splk` on PATH, with pytest, AppInspect and Playwright
python -m playwright install chromium   # the browser for UI tests and `splk shot`
cp .env.example .env            # then paste a Splunk auth token into SPLUNK_TOKEN,
                                # and a Splunk Web username and password for UI tests
splk doctor                     # reachable? token valid? which version?
```

Targets live in [`config/targets.toml`](config/targets.toml). The default,
`local`, is `https://localhost:8089` with TLS verification off for the
self-signed certificate of a fresh install, and Splunk Web at
`http://localhost:8000` (`web_url`) for browser tests. Live tests that seed
events need a dev-only index called `splk_test` on the target (create it once
in Splunk Web).

### Commands

| Command | What it does |
| --- | --- |
| `splk dev <app>` | Build, unit tests, AppInspect, install on the target, live tests, then UI tests and the UX audit for apps that have them. Stops at the first red stage. |
| `splk dev <app> --skip-inspect` | The same without AppInspect, for a faster inner loop. |
| `splk test [--live] [--ui] <app>` | Unit tests; with `--live`, also `tests/live/<app>/` on the target; with `--ui`, also `tests/ui/<app>/` in a browser (`--headed` to watch). |
| `splk inspect <app>` | Build and run the full AppInspect check set. |
| `splk deploy <app> [--restart]` | Build and install via `POST /services/apps/local`, verify the installed version, reload. Restarts only with `--restart` on a target that allows it. |
| `splk search "<spl>"` | Run one query on the target and print rows as JSON. |
| `splk shot <app>[/<view>] [--theme dark]` | Open a Splunk Web page in a browser, save a screenshot to `build/reports/ui/shots/`, and print the final URL and any JavaScript errors as JSON. |
| `splk ux <app> [--view <v>] [--theme <t>]` | Open every view of the app in light and dark, save screenshots, scan them for accessibility problems (axe-core) and record JavaScript errors. Report in `build/reports/ux/<app>/report.md`. |
| `splk review security\|ux <scope> pass\|fail --summary ...` | Record the outcome of a security or UX review in the run log. |
| `splk runs` | Recent stage results from the run log. |

`--json` gives machine-readable results; `-v` gives debug output. Every run
logs to `.agent/logs/splk.log` (JSON lines, tokens masked) and records each
stage result in `.agent/runs/`. Exit codes: 0 green, 1 a stage failed, 2 usage
or configuration error.

### Live tests

`tests/live/<app>/` holds tests that run SPL on the target and assert on the
rows. They are skipped by plain `pytest` and in CI, and run via `splk test
--live <app>` or as the last stage of `splk dev`. Fixtures in
[`tests/live/conftest.py`](tests/live/conftest.py): `search`, `seed` (index raw
events into the test index under a unique `source`), `splunk`, `target`.

### UI tests

`tests/ui/<app>/` holds tests that drive Splunk Web in a real browser
(Playwright, headless Chromium) and assert on what the page renders: a view
loads, its controls work, it follows the user's theme. They sign in with
`SPLUNK_WEB_USERNAME` and `SPLUNK_WEB_PASSWORD` from `.env`, once per run (the
session is cached in `.agent/ui/`), because Splunk Web does not accept auth
tokens. Use a dev instance: those credentials sit in `.env` in plain text.

Like live tests they never run in plain `pytest` or CI. Each run leaves
screenshots in `build/reports/ui/<app>/`, and for a failure a screenshot and a
trace you can replay with `python -m playwright show-trace <file>.zip`.
Fixtures in [`tests/ui/conftest.py`](tests/ui/conftest.py): `open_view`,
`shot`, `page_log`, `page`, `web`.

### UX audit

`splk ux <app>`, also the last stage of `splk dev`, opens every view under
`apps/<app>/default/data/ui/views/` in both themes. For each it saves a
screenshot, reads the theme the page actually drew, runs an
[axe-core](https://github.com/dequelabs/axe-core) scan of the app's own
content against the WCAG 2.2 A and AA rules, and records uncaught exceptions
and console errors. The stage fails on:

- an uncaught exception, or a console error from the app's own static files
  (Splunk Web logs errors of its own, which are reported but do not fail it);
- a view that never shows its ready selector;
- an accessibility violation of serious or critical impact that is not waived.

Lesser findings are reported for review. Each app sets, per view, a `ready`
selector and a `scope` (its root element, so Splunk Web's own header is not
scanned) in `tests/ui/<app>/ux.toml`, which can also waive a finding with a
written reason. A page that follows the user's theme preference may refuse the
other theme; the report then says that theme was not audited.

The audit catches what a machine can. Layout, wording, loading, empty and
error states are judged by the `ux-reviewer` agent against the
[`splunk-ux`](.claude/skills/splunk-ux/SKILL.md) standard, from the
screenshots and the source.

axe-core is vendored in `tools/splk/vendor/axe-core/` (MPL-2.0, licence
alongside) by `python scripts/vendor_axe.py`, which checks the npm registry's
SHA-512 before writing anything.

### Coding agent configuration

The repository carries configuration for the coding agent described under
[AI assistance](#ai-assistance):

| Path | Role |
| --- | --- |
| [`CLAUDE.md`](CLAUDE.md) | Always-loaded project instructions: the `splk` commands and the definition of done. |
| `.claude/rules/` | Path-scoped rules (Python, conf files, search commands, inputs/props, searches/dashboards, pages in Splunk Web, Splunkbase listings, CI and release) that load only when matching files are touched, plus always-on Windows environment rules. |
| `.claude/skills/` | `dev-loop`, `splunk-playbook`, `write-live-test`, `write-ui-test`, `appinspect-fix`, `splunk-security-review`, `splunk-ux` (the UX standard), `splunk-ux-review`, `new-app`, `release-app`, `retro`. |
| `.claude/skills/splunk-playbook/` | What works: proven recipes per feature (custom pages, REST endpoints behind a page, theme support, search commands, checking UI in a browser), with the approaches that failed. |
| `.claude/agents/` | `splunk-reviewer` (read-only review), `security-reviewer` (read-only security review), `ux-reviewer` (read-only UX review from screenshots) and `learner` (maintains lessons and the playbook). |
| `.claude/hooks/` + `.claude/settings.json` | Deterministic guards: deny raw REST/restarts/`etc/apps` copies and edits to `local/`, lint every edited file (Python 3.9 grammar, conf syntax, BOMs and mojibake, ASCII-only listings), inject target status at session start, and before a session ends ask for a retro (after a fix, or after any app deploy), a security review (after code changes) and a UX review (after changes to what users see). |
| `.claude/agent-memory/learner/` | Lessons learned, committed and reviewed like code. |

Hooks run `python`, so a Python 3.9+ interpreter must be on PATH under that
name (true for the python.org installer on Windows).

**How it improves itself:** it keeps two kinds of memory. *Lessons* record
what went wrong (symptom, cause, fix, how to catch it earlier). *Playbook
patterns* record what works: the recipe for a feature, why each step is there,
and which approaches failed first. The second matters as much as the first:
easyadmin's theme support took three attempts without any `splk` stage going
red, so a failure-only loop would have learned nothing from it.

Every `splk` stage result, and every security review outcome, is recorded.
Before a session ends, the Stop hook asks the agent to run `retro` when a
failure was fixed or an app was deployed (naming apps that needed three or
more deploys), to run `splunk-security-review` when code changed after the
last review, and to run `splunk-ux-review` when a view, page script or
stylesheet changed after the last UX review. The `learner` agent writes the lessons and patterns. A lesson seen
twice is promoted into a rule or skill; a pattern confirmed in a second app
becomes a scaffold step or check; anything that must never recur becomes a
test or hook check. Those promotions arrive as ordinary diffs in a pull request.

## Packaging

```bash
python scripts/package_app.py fillcontinuous          # -> dist/fillcontinuous-1.0.0.spl
python scripts/package_app.py --all --outdir dist
```

The packager excludes `local/`, `local.meta`, caches and editor droppings, and
normalises file modes to `0644`/`0755`. That last part matters on Windows, which
has no Unix permission bits — an archive built there would otherwise carry
whatever mode the filesystem invented, and AppInspect rejects files that are
world-writable or needlessly executable.

It also refuses to build when `[launcher] version` and `[id] version` in
`app.conf` disagree, which AppInspect treats as a failure.

## CI

[`ci.yml`](.github/workflows/ci.yml) runs on every pull request and push to
`main`:

1. **discover** — picks the apps this PR or push changed, using
   [`scripts/changed_apps.py`](scripts/changed_apps.py)
2. **test** — pytest on Python 3.9 and 3.13, plus a 3.9 byte-compile of all scripts
3. **package** — builds each selected `.spl`
4. **appinspect** — runs the AppInspect CLI against the built package, with **no
   tag filter**, so all 252 checks run
5. **appinspect-api** — submits the package to Splunk's hosted AppInspect API,
   the authoritative service behind Cloud vetting. Skips with a notice when the
   credentials are absent, so forks and outside contributors are unaffected.

### Which apps get vetted

Steps 3 to 5 run only for apps with a changed file under `apps/<app>/`, so one
app's PR does not resubmit every other app to AppInspect. Every app is vetted
instead when:

- the run was started by hand (**Run workflow**, `workflow_dispatch`);
- a shared file changed: `scripts/package_app.py`, `scripts/changed_apps.py`,
  `.github/workflows/ci.yml` or any `.appinspect*.yaml` waiver file;
- there is no usable commit to compare against, such as the first push of a new
  branch or a force push that orphaned the old tip.

When nothing under `apps/` changed (a docs or tooling PR), those steps are
skipped and only the tests run.

### The two AppInspect actions take `app_path` differently

This is worth knowing before you touch either workflow, because both fail
quietly rather than loudly:

| Action | `app_path` must be | Why |
| --- | --- | --- |
| `appinspect-cli-action` | the package **file** | Given a directory it globs and scans only the first entry — pointed at an app source folder it would inspect `README.md` and report a clean pass. |
| `appinspect-api-action` | a **directory** holding exactly one package | Its entrypoint runs `ls $app_path` and appends the result, so a file path resolves to `<file>/<file>` and the upload fails. |

The API action also reads its own expect file,
[`.appinspect_api.expect.yaml`](.appinspect_api.expect.yaml) — a *different*
filename from the CLI action's `.appinspect.expect.yaml`. It is consulted only
when the API reports failures, and at that point the file must exist or the job
fails on the missing file rather than on the actual problem.

### Current status

`fillcontinuous` passes the cloud checks with **0 failures and 0 errors**, and
AppInspect returns no manual checks for it. Three warnings remain, none
actionable: a generic Splunk 8.0 Python 2/3 migration notice, and two checks
that only run on Linux or macOS.

### Manual checks and waivers

If a future app does produce checks a human must decide, the CI action fails
unless each is recorded in [`.appinspect.manualcheck.yaml`](.appinspect.manualcheck.yaml)
with a comment. It prints the exact YAML to paste in, under `You can initialize
it with below yaml content`. Copy it in, say what you actually verified, and the
job goes green — nothing gets waived by accident.

[`.appinspect.expect.yaml`](.appinspect.expect.yaml) does the same for accepted
failures, and should stay empty — a Cloud submission must have none. Waivers
there require a comment carrying an `ADDON-<n>` or `APPCERT-<n>` ticket id.

### `check_for_updates` depends on how the app is distributed

The two destinations want opposite settings, and only one of them is checked by
the `cloud` tag:

| Destination | `[package] check_for_updates` |
| --- | --- |
| **Splunkbase** | must **not** be `false`. Leave it absent, which defaults to enabled — Splunkbase serves the update notifications itself, and its uploader rejects the package outright with *"must not be disabled"*. |
| Private app, not on Splunkbase | should be `false`. AppInspect's `check_for_updates_disabled` warns when it is missing. |

Apps here target Splunkbase, so the setting is deliberately absent and the
resulting warning is expected. Do not "fix" that warning by setting it to
`false`; that trades a warning for a rejected upload.

`check_for_updates_disabled` is tagged `private_app`, not `cloud`, so CI never
sees it either way.

### Running AppInspect locally

```bash
pip install splunk-appinspect
python scripts/package_app.py fillcontinuous --outdir dist
splunk-appinspect inspect dist/fillcontinuous-1.1.1.spl --mode test
```

Or `splk inspect fillcontinuous`, which does both steps and also fails on any
manual check not recorded in `.appinspect.manualcheck.yaml`, as CI does.

Note the absence of `--included-tags`. CI runs the complete set for the same
reason: filtering to `cloud` covers 246 of 252 checks, and one of the six it
skips is what let a Splunkbase-rejecting package through. Splunkbase's own
uploader is stricter still in places, so even a clean full run is necessary
rather than sufficient.

## Releasing

Tags name the app they belong to, so apps version independently:

```bash
git tag fillcontinuous-v1.0.0
git push origin fillcontinuous-v1.0.0
```

[`release.yml`](.github/workflows/release.yml) then runs the tests, builds the
package, runs the AppInspect CLI, and publishes a GitHub release with the
`.spl` attached. `workflow_dispatch` does the same for a dry run without tagging.

Two details exist because a monorepo breaks the usual assumptions:

- **The tag version must match `app.conf`.** The workflow passes the version
  from the tag to the packager as `--expect-version`, which refuses to build on
  a mismatch. Otherwise tagging `v1.0.1` while `app.conf` still said `1.0.0`
  would publish a `1.0.0` package under a `1.0.1` release, with nothing to
  flag it.
- **Release notes are scoped to the app.** GitHub's `generate_release_notes`
  diffs against the previous release of *any* app, so releasing app B after app
  A would list app A's commits. The workflow instead resolves the previous
  `<app>-v*` tag and logs only commits touching `apps/<app>/`.

It also runs the **AppInspect API** vetting, using the repository secrets
`SPLUNK_COM_USERNAME` and `SPLUNK_COM_PASSWORD`. Without them the step is
skipped with a warning rather than failing the release.

Since the API vetting also runs on every pull request, a release should hold no
surprises. If the API's rate limits or runtime become a nuisance as the repo
grows, drop the `appinspect-api` job from `ci.yml` and rely on the release
workflow alone.

## Adding an app

1. Create `apps/<name>/` with `default/app.conf` (`[id] name` must equal the
   directory name, and `[launcher] version` must match `[id] version`).
2. Add `default/commands.conf` (or inputs, etc.) with both Python settings.
3. Add `metadata/default.meta`, `app.manifest`, `README.md` and `LICENSE`.
4. Put testable logic in `bin/<name>_core.py` and add tests under `tests/`.
5. Vendor dependencies: `python scripts/vendor_splunklib.py <name>`.

CI picks it up automatically.

## Supply chain

**Actions are pinned to commit SHAs**, with the version in a trailing comment.
Tags are mutable, and `release.yml` runs with `contents: write` and the
Splunk.com credentials, so a moved tag would be a direct path to both. To bump
one, resolve the new SHA rather than editing the tag:

```bash
gh api repos/actions/checkout/commits/v7 --jq .sha
```

Two honest limits on how far that protects us:

- **The Splunk AppInspect actions are Docker actions.** Pinning the action ref
  fixes `action.yml`, but that file refers to its image by tag
  (`ghcr.io/splunk/appinspect-cli-action/appinspect-cli-action:v2.15.0`), and an
  image tag is mutable too. Pinning the ref is still worth doing; it just does
  not pin the container.
- **The AppInspect API action handles the credential loosely.** Its entrypoint
  echoes it and passes it in `argv` to `python3 /main.py <user> <pass> …`.
  GitHub masks registered secrets in logs and the runner is ephemeral, so
  exposure is limited — but prefer a Splunk.com account used only for app
  vetting, rather than one with wider access.

**The vendored SDK is verified.** `vendor_splunklib.py` checks the SHA-256 that
PyPI publishes alongside the download, because that code is committed and then
ships inside every app. `vendor_axe.py` does the same for axe-core with the
npm registry's SHA-512; that file is developer tooling only and never ships in
an app.

## AI assistance

Content in this repository — app code, tests, packaging scripts, CI workflows
and documentation — was produced with the help of an AI coding assistant, then
reviewed, tested and published by the author.

Everything here has been exercised rather than taken on trust: the test suite
runs on both supported Python versions, packages are validated against Splunk's
AppInspect API, and the search commands have been run against a live Splunk
instance. Treat it as you would any third-party code — read it before you run it
on anything that matters.

## Author

[MaximumPigs](https://github.com/maximumpigs)

## Licence

Apache 2.0. See [LICENSE](LICENSE).
