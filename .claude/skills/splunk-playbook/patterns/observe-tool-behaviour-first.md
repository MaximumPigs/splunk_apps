---
confirmed: 1
seen: [2026-11-15]
apps: [splk]
---
# Observe a tool's real behaviour before building on it

**Use when:** `splk` code or a hook depends on how an external tool behaves:
a headless `claude -p` result, a guard's allow/deny, a git side effect.

**Recipe:**

1. Parsers: run the tool once for real (`claude -p --output-format json`) and
   read the output before writing the parser. Observed keys: `structured_output`,
   `is_error`, `subtype`, `api_error_status`, `terminal_reason`,
   `total_cost_usd`, `session_id`. Tests assert only these.
2. Guards: prove them with a real headless step in the exact step
   environment (`SPLK_LOOP=1`, scrubbed env). Check the variable reached the
   hooks, the token is absent, and push, merge and hook edits are denied. A
   cheap model is enough for a probe.
3. Suspicious git behaviour: reproduce in a throwaway bare repo
   (`git init --bare` plus a clone) before blaming a command. Here it cleared
   `git push -u origin <branch>` and pointed at the editor.
4. Spawn tools from Python with an argument list, never via a shell string
   (`lessons/windows-powershell-json-arguments.md`).

**Why this way:** guesses cost more than probes: an unchecked `.agent/` design
(`lessons/process-probe-guards-before-designing-on-them.md`), spelling-specific
deny lists (`lessons/security-unattended-agent-escape-routes.md`), and a wrong
suspect for pushes to main (`lessons/git-branch-tracking-main-editor-push.md`).

**Open:** the usage-limit error format of a headless step has not been
observed; do not parse it until seen.

**Verify:** the headless probe's denials and the parsed keys were observed in
the 2026-11-15 session (not re-checked by the retro; confirm the `loop_core`
unit tests cover the keys).

**Reference:** `tools/splk/loop.py`, `tools/splk/loop_core.py`,
`config/loop.toml`, `.claude/loop/prompts/`.
