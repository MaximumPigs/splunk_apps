---
name: retro
description: Record a lesson after a splk stage failed and was then fixed, so the same mistake is caught earlier next time. Use when the Stop hook asks for it, after any fix of a red stage, or when the person says "retro" or "review lessons".
argument-hint: "[--review]"
context: fork
agent: learner
---

# Retro

Mode: `$ARGUMENTS` (empty = record lessons for this session; `--review` = prune).

Recent stage results (newest last):

!`splk runs --last 40`

Current diff against main:

!`git diff --stat origin/main...HEAD`

## Record (default)

For each (app, stage) that failed then passed above:

1. Find the cause in the diff and the failure details. One cause per lesson.
2. If `.claude/agent-memory/learner/lessons/` already has the same cause, increment its `hits`, add the
   date, and stop. Otherwise create `.claude/agent-memory/learner/lessons/<area>-<short-slug>.md`:

   ```markdown
   ---
   hits: 1
   seen: [YYYY-MM-DD]
   area: <app id, or conf | spl | appinspect | python | splk>
   level: lesson
   ---
   **Symptom:** what failed, quoting the check name or test id.
   **Cause:** the actual mistake.
   **Fix:** what changed.
   **Catch earlier:** the rule, test or hook that would have prevented it.
   ```

3. Update `.claude/agent-memory/learner/MEMORY.md`: one line per lesson, sorted by hits, most first.
4. **Promote** when `hits >= 2` (or the person asks): propose the exact edit
   to a `.claude/rules/*.md` file or skill, or a new test or hook check. Write
   the edit, set `level:` to `rule`, `skill`, `test` or `hook`, and say in your
   final answer which files changed so the person reviews them in the PR.

## Review (`--review`)

Merge duplicate lessons, delete lessons with `level: lesson` not seen in 60
days, confirm each promoted lesson's rule still exists, and keep `MEMORY.md`
under 100 lines and root `CLAUDE.md` under 200.

## Constraints

- Never edit `.claude/settings.json` or the hook scripts' deny lists without
  saying so explicitly in the final answer: those are the safety layer.
- Lessons describe this repo's reality, with evidence. No generic advice.
