#!/usr/bin/env bash
# Entrypoint of the dev container (docker/dev/Dockerfile).
#
#   loop   (default) clone or reuse the repo in /work, then run `splk loop`
#          forever, waiting while it is paused
#   shell  the same set-up, then an interactive shell
#   *      the same set-up, then run the given command
#
# Two stages, because secrets must not sit in any environment the loop user
# can read (/proc/<pid>/environ is readable by the process's own uid, and
# `unset` does not change it):
#
#  1. As root: write the secrets to a file in /run/loop-secrets (a tmpfs that
#     only root can write, see compose.yaml), give the file to `loop`, then
#     start stage 2 as `loop` with a clean environment holding only what
#     steps need (CLAUDE_CODE_OAUTH_TOKEN) and plain settings.
#  2. As loop: clone, check the tooling with git alone, and only then write
#     the clone's .env and run any repo code (pip, splk). `splk loop` loads
#     .env for the supervisor and keeps .env values out of every step.
#
# The .env file and the tmpfs copy are still readable by the loop user, and
# so by a step that deliberately looks: only running steps under another uid
# would close that. The ruleset on main is the boundary for what a step could
# do with them.
set -euo pipefail

REPO_DIR=/work/splunk_apps
SECRETS_DIR=/run/loop-secrets
SECRETS_FILE="$SECRETS_DIR/secrets.env"
SECRETS=(GH_TOKEN SPLUNK_TOKEN SPLUNK_WEB_USERNAME SPLUNK_WEB_PASSWORD
         SPLK_LOOP_GH_TOKEN SPLK_NTFY_TOPIC SPLK_NTFY_TOKEN)
# Plain settings passed to stage 2 (no secrets except the one steps need).
PASS_THROUGH=(REPO_URL GIT_AUTHOR_NAME GIT_AUTHOR_EMAIL SPLK_TARGET CLAUDE_CODE_OAUTH_TOKEN TZ)
# What the supervisor runs or trusts from the clone (targets.toml says where
# the Splunk token goes). A branch that changed any of it must not run with
# the secrets loaded. This catches accidental or unreviewed tooling changes;
# it is no defence against a hostile step, which could read the secrets
# file directly or plant commands on PATH.
TOOLING=(tools pyproject.toml setup.py setup.cfg .claude/hooks .claude/settings.json
         .claude/loop config/loop.toml config/targets.toml scripts/package_app.py)

log() { printf '%s loop-entrypoint: %s\n' "$(date -u +%FT%TZ)" "$*" >&2; }

stage_root() {
  : "${REPO_URL:?set REPO_URL (https URL of the repository)}"
  : "${GIT_AUTHOR_NAME:?set GIT_AUTHOR_NAME (the owner, not a bot)}"
  : "${GIT_AUTHOR_EMAIL:?set GIT_AUTHOR_EMAIL (the owner noreply address)}"
  : "${GH_TOKEN:?set GH_TOKEN (pushes branches and opens PRs)}"
  : "${CLAUDE_CODE_OAUTH_TOKEN:?set CLAUDE_CODE_OAUTH_TOKEN (from claude setup-token)}"
  # A token in the URL would end up in logs and .git/config.
  case "$REPO_URL" in
    *://*@*) log "REPO_URL must not contain credentials"; exit 2 ;;
  esac

  # Root owns the directory (0711: loop may open a file it is given, not
  # list or create), so loop cannot plant a symlink at the file's path.
  # Removing first means a stale file from an earlier start is never reused.
  if [ ! -d "$SECRETS_DIR" ] || [ -L "$SECRETS_DIR" ] || [ "$(stat -c %u "$SECRETS_DIR")" != "0" ]; then
    log "$SECRETS_DIR must be a root-owned directory (see compose.yaml tmpfs)"; exit 2
  fi
  rm -f "$SECRETS_FILE"
  (
    umask 077
    set -o noclobber
    for key in "${SECRETS[@]}"; do
      if [ -n "${!key:-}" ]; then printf '%s=%s\n' "$key" "${!key}"; fi
    done > "$SECRETS_FILE"
  )
  chown loop:loop "$SECRETS_FILE"

  local env_args=(HOME=/home/loop USER=loop LOGNAME=loop SHELL=/bin/bash
                  "PATH=/home/loop/.local/bin:/usr/local/bin:/usr/bin:/bin"
                  PYTHONUNBUFFERED=1 PLAYWRIGHT_BROWSERS_PATH="$PLAYWRIGHT_BROWSERS_PATH")
  for key in "${PASS_THROUGH[@]}"; do
    if [ -n "${!key:-}" ]; then env_args+=("$key=${!key}"); fi
  done
  exec setpriv --reuid=loop --regid=loop --init-groups \
    env -i "${env_args[@]}" bash "$0" --as-loop "$@"
}

# The push token, for git and gh calls in this script only. Never exported:
# it reaches a command's environment for that one command.
gh_token=""

github() { GH_TOKEN="$gh_token" "$@"; }

tooling_unchanged() {
  github git fetch --quiet origin
  # Only what this branch changed (committed, uncommitted or new files) since
  # it left main; tooling merged to main afterwards is not a reason to stop.
  local base
  base="$(git merge-base HEAD origin/main)"
  git diff --quiet "$base" -- "${TOOLING[@]}" \
    && [ -z "$(git ls-files --others --exclude-standard -- "${TOOLING[@]}")" ]
}

# Block until the checked-out tooling matches main. .env is removed so no repo
# code finds secrets meanwhile; the tmpfs copy stays readable by loop.
require_clean_tooling() {
  until tooling_unchanged; do
    rm -f .env
    log "tooling on $(git branch --show-current) was changed on this branch; not running splk."
    log "Inspect: docker compose exec -u loop -w /work/splunk_apps dev bash, then git diff \$(git merge-base HEAD origin/main) -- tools"
    sleep 300
  done
}

write_env() { (umask 077; printf '%s' "$secrets" > .env); }

wait_for_splunk() {
  until splk doctor; do
    log "Splunk target ${SPLK_TARGET:-default} not ready (first boot takes minutes; a missing token needs SPLUNK_TOKEN); retrying in 60 s"
    sleep 60
  done
}

stage_loop() {
  # Read once into memory; the file stays on the tmpfs (root removes it at
  # the next start) because loop cannot delete in root's directory.
  secrets="$(cat "$SECRETS_FILE")"
  gh_token="$(printf '%s\n' "$secrets" | sed -n 's/^GH_TOKEN=//p')"

  # git asks gh for credentials at call time; gh reads GH_TOKEN from the
  # environment of that call (the supervisor's, via .env). Steps get neither.
  github gh auth setup-git

  if [ ! -d "$REPO_DIR/.git" ]; then
    log "cloning $REPO_URL"
    github git clone --quiet "$REPO_URL" "$REPO_DIR"
  fi
  cd "$REPO_DIR"
  # Commits are the owner's: the bash guard refuses an AI author, and GitHub's
  # squash merge would turn one into a co-author trailer.
  git config user.name "$GIT_AUTHOR_NAME"
  git config user.email "$GIT_AUTHOR_EMAIL"

  # git only until here. No repo code runs before this check passes.
  require_clean_tooling
  write_env
  # Editable, without dependencies (they are in the image): tooling changes
  # merged to main apply on the next start without a rebuild.
  pip install --user --quiet --no-deps -e .

  case "${1:-loop}" in
    loop)
      wait_for_splunk
      while true; do
        require_clean_tooling
        write_env
        splk loop run || log "splk loop run exited with $?"
        # Paused by the owner or stuck: wait for `splk loop resume`
        # (docker compose exec -u loop -w /work/splunk_apps dev splk loop resume).
        while [ -f .agent/loop/PAUSE ]; do sleep 60; done
        sleep 60
      done
      ;;
    shell)
      exec bash -l
      ;;
    *)
      exec "$@"
      ;;
  esac
}

if [ "${1:-}" = "--as-loop" ]; then
  shift
  stage_loop "$@"
elif [ "$(id -u)" = "0" ]; then
  stage_root "$@"
else
  log "start the container as root; it drops to the loop user itself"
  exit 2
fi
