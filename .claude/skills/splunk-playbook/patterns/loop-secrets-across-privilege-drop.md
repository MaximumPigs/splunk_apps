---
confirmed: 1
seen: [2026-11-15]
apps: [repo-splk-loop]
---
# Give an unattended loop its secrets and settings safely

**Use when:** a container or supervisor starts `splk loop` (or any unattended
agent steps) and must hand it credentials or target settings.

**Recipe:**
1. Compose: an explicit `environment:` allow-list. Never `env_file: .env`.
2. Entrypoint starts as root. It writes secrets to a file inside a root-owned
   tmpfs directory (mode 0711), created fresh, with `rm` first and `noclobber`
   on, then chowns the file to the loop user. No fixed `/tmp` file name.
3. Drop privilege with `setpriv` and `env -i`, passing only the one variable the
   agent needs (`CLAUDE_CODE_OAUTH_TOKEN`). Do not rely on `unset`.
4. Run the git-only "tooling changed vs main" check **before** writing `.env`
   or running anything from the repo (`pip install -e`, `splk doctor`).
5. Step-time config (target name, host, token, allow_restart) comes from a
   supervisor-written `.env` file. Under `SPLK_LOOP=1`,
   `config.resolve_target` ignores `SPLK_TARGET_*` env vars and refuses a
   different `--target`.

**Why this way:** `unset` leaves values in `/proc/<pid>/environ`, readable by the
same uid. A predictable `/tmp` path can be planted, or left over and crash-loop
under `cap_drop ALL` (no DAC_OVERRIDE). Env overrides are settable by any step
command, with no `.env` read for the guard to catch. Checking after running
branch code is too late. Same-uid secrets remain speed bumps: the real
boundary is server-side (ruleset, read-only token). See lesson
`security-unattended-agent-escape-routes`.

**Verify:** the third security review passed with 0 medium findings (by
reading). NOT yet built or run: no Docker on the dev machine. Before raising
`confirmed`, run it and check from a step that the env, `/proc/self/environ`
and the tmpfs dir hold no secret except the intended one.

**Reference:** `docker/compose.yaml`, `docker/dev/entrypoint.sh`,
`tools/splk/config.py` (`resolve_target`), `tools/splk/loop.py`.
