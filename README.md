# splunk_apps

A monorepo of Splunk apps, each independently validated, packaged and released.

Every app targets **Splunk Cloud Platform** and is built to pass **AppInspect**
Cloud vetting.

## Apps

| App | What it does |
| --- | --- |
| [`fillcontinuous`](apps/fillcontinuous/) | Fills the missing time buckets that `timechart` and `makecontinuous` cannot, across any number of group-by fields. Registers `fillcontinuous` and the alias `fillgaps`. |

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

1. **discover** — finds each app under `apps/`
2. **test** — pytest on Python 3.9 and 3.13, plus a 3.9 byte-compile of all scripts
3. **package** — builds each `.spl`
4. **appinspect** — runs the AppInspect CLI against the built package, with **no
   tag filter**, so all 252 checks run
5. **appinspect-api** — submits the package to Splunk's hosted AppInspect API,
   the authoritative service behind Cloud vetting. Skips with a notice when the
   credentials are absent, so forks and outside contributors are unaffected.

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
splunk-appinspect inspect dist/fillcontinuous-1.1.1.spl --mode test --included-tags cloud
```

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
ships inside every app.

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
