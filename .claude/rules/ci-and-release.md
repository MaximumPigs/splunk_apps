---
paths:
  - ".github/**"
  - "scripts/**"
  - ".appinspect*.yaml"
---

# CI, packaging and release

- AppInspect runs the **full** check set everywhere. Never add `--included-tags`.
- The two official actions take `app_path` in opposite ways, and both fail quietly:

  | Action | Wants | If wrong |
  | --- | --- | --- |
  | `appinspect-cli-action` | the package **file** | scans only the first entry of a directory, e.g. `README.md`, and passes |
  | `appinspect-api-action` | a **directory** holding exactly one package | `ls $app_path` turns a file into `<file>/<file>` |

- They read different expect files: `.appinspect.expect.yaml` (CLI) and
  `.appinspect_api.expect.yaml` (API). Both stay empty and must exist: the API
  action fails on a missing file and buries the real finding.
- Actions are pinned to commit SHAs. To bump, resolve the SHA
  (`gh api repos/<owner>/<action>/commits/<tag> --jq .sha`), never edit a tag.
  Splunk's actions are Docker actions whose image tag is still mutable.
- CI packages and vets only apps changed in the PR/push
  (`scripts/changed_apps.py`). Any doubt must select every app, never none. A
  new file that affects every package or verdict belongs in its `SHARED_PATHS`.
- `ubuntu-latest` can drop old Pythons: the test job is pinned to
  `ubuntu-24.04` to keep 3.9. Re-check before unpinning.
- `scripts/package_app.py` normalises modes to 0644/0755 (load-bearing on
  Windows) and excludes `local/`, `local.meta`, caches. `.gitattributes` pins LF
  so Windows-built packages byte-match CI's.
- **`lib/` must never be gitignored**; the stock Python template does, and the
  app would still work on the dev machine.
- Releases: per-app tags `<app>-v<version>`. The workflow passes the tag's
  version as `--expect-version`; bump `app.conf` **and** `app.manifest` first.
  Notes cover commits touching `apps/<app>/` since the previous `<app>-v*` tag;
  `generate_release_notes` stays off. Use the `release-app` skill.
- When a hosted check (AppInspect API) fails, check the obvious mechanical
  causes (stale secret, timestamps of when it was set) before theorising.
