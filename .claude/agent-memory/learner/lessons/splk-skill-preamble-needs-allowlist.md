---
hits: 3
seen: [2026-11-15, 2026-11-15, 2026-11-15]
area: splk
level: lesson
---
**Symptom:** The `retro` skill (and `dev-loop`) failed to load: the `!`
preamble `splk runs --last 40` could not run, so the retro was started
without its evidence.
**Cause:** Skill `!` preamble commands cannot prompt for permission; if the
command is not allowlisted the skill does not load. Permission changes made
mid-session are not picked up until the session reloads.
**Fix:** The owner added `Bash(splk runs*)` to the allowlist. This session's
retro ran `splk runs` and `git log` by hand.
**Again:** the loop's retro step for easyadmin item 1 hit it too, although
`Bash(splk runs*)` is in `.claude/settings.json`: the skill load failed with
"requires approval" for `!`splk runs --last 40``, and the retro read the
run log by hand. So the entry does not cover a skill preamble in an unattended
session (or the session predates it). Owner to check the pattern; until then
the retro step reads `splk runs --days 2` itself.
**Again (item 3, retro step):** same "requires approval" failure. The step
records in `.agent/loop/steps/` show the likely cause: every headless session
printed "Ignoring 15 permissions.allow entries from .claude/settings.json:
this workspace has not been trusted" (stderr of the six rate-limited
implement attempts). So the allowlist is not applied to loop sessions at all,
which explains why `Bash(splk runs*)` never helped. Owner fix: accept the
trust dialog once interactively in this folder, or set
`projects["D:/GitHub/splunk_apps"].hasTrustDialogAccepted: true` in
`~/.claude.json`. Until then the retro step reads the run log by hand.
**Catch earlier:** When a skill gains a `!` command, add its allowlist entry
in the same change (a settings change, so name it to the owner). After
editing permissions, restart the session before relying on them.
