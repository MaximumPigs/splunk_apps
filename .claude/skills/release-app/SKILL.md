---
name: release-app
description: Cut a release of one app (version bump, tag, release notes, Splunkbase package). Use only when the person asks to release or publish an app.
argument-hint: "[app-id] [new-version]"
disable-model-invocation: true
---

# Release `$ARGUMENTS`

Releases are per app, tagged `<app>-v<version>`, built and vetted by
`.github/workflows/release.yml`. Pushing a tag publishes, so **ask the person
before every push**.

## Before tagging

1. On a feature branch, bump the version in **all** of:
   `apps/<app>/default/app.conf` (`[launcher]` and `[id]`) and
   `apps/<app>/app.manifest` (`info.id.version`).
2. Update the app README for anything user-visible; keep claims to what has
   been observed on a live instance.
3. `splk dev <app>` green on the local target, including AppInspect.
4. PR, CI green, then **squash merge with an explicit subject and body file**
   (GitHub's default squash body concatenates every commit message):

   ```
   gh pr merge <n> --squash --subject "<subject>" --body-file <short path>
   ```

   No AI tool names and no `Co-Authored-By` trailers in either.

## Tag

5. After the merge, from an up-to-date `main`:
   `git tag <app>-v<version>` then, with the person's go-ahead,
   `git push origin <app>-v<version>`.
6. The workflow passes the tag's version as `--expect-version` and refuses to
   build on a mismatch with `app.conf`. If it fails there, delete the tag, fix
   the bump, and tag again.
7. Release notes list commits touching `apps/<app>/` since the previous
   `<app>-v*` tag. `generate_release_notes` stays off (it diffs against any app).

## Splunkbase

8. Upload the release asset `.spl` from the GitHub release, not a local build.
9. Listing text comes from `splunkbase/<app>/listing.md` (ASCII only); set
   compatible Splunk versions on the form too (currently 9.3+).
10. Note any known drift between the released package and `main` (e.g. a docs
    change not re-released) in the handoff to the person.
