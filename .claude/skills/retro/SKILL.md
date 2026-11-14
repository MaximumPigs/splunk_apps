---
name: retro
description: Debrief after app work, recording what went wrong as lessons and what worked as playbook patterns, so later sessions build Splunk apps better, not only avoid repeat errors. Use when the Stop hook asks, after fixing a red stage, after a feature took several attempts or person corrections, or when the person says "retro" or "review lessons".
argument-hint: "[--review]"
context: fork
agent: learner
---

# Retro

Mode: `$ARGUMENTS` (empty = debrief this session; `--review` = prune).

Recent stage results (newest last):

!`splk runs --last 40`

Current diff against main:

!`git diff --stat origin/main...HEAD`

## Debrief (default)

Answer three questions from the run log, the diff and the conversation. Each
answer that holds evidence becomes a file change; "nothing new" is a valid
answer, but say which question it answers.

1. **What failed and was fixed?** Every (app, stage) that went red then green
   above, plus any fixed `splunk-security-review` or `splunk-ux-review`
   finding, and every time the person reported something did not work.
   Record a **lesson** (below).
2. **What took more than one attempt, or worked better than expected?**
   Several deploys of the same app, a feature redone after the person looked,
   a technique found after reading SDK or Splunk source. Record or update a
   **pattern** in the playbook (below). This is how agents get better, not
   just safer: the next session starts from the approach that worked. A
   `splunk-ux-review` report's "Patterns worth keeping" are candidates too.
3. **Did an existing pattern, rule or skill hold?** If you followed a
   pattern and it worked, add 1 to its `confirmed` count and the date. If it
   was wrong or incomplete, correct it now, citing the evidence.

### Lessons (what went wrong)

1. Find the cause in the diff and the failure details. One cause per lesson.
2. **Scope it by what it impacts, not by what exposed it.** Ask whether the
   same cause could bite in another scenario: another app, any app using the
   same Splunk feature, API or conf setting, or `splk` itself. If it could,
   the area, file name, title and **Cause** describe that broader thing
   (`python-simplerequest-postargs-dict`, not `easyadmin-role-update-fails`),
   and the app that exposed it appears only in **Symptom** as the evidence.
   Use the app id as the area only when the cause is specific to that app's
   own code or design and could not recur elsewhere.
3. If `.claude/agent-memory/learner/lessons/` already has the same cause,
   increment its `hits`, add the date, and stop. Match on the cause, not the
   app. Otherwise create `lessons/<area>-<short-slug>.md`:

   ```markdown
   ---
   hits: 1
   seen: [YYYY-MM-DD]
   area: <app id, or conf | spl | appinspect | python | splk | splunkd | splunkweb | security | ux>
   level: lesson
   ---
   **Symptom:** what failed, quoting the check name, test id or the person's
   report. Name the app here; this is the evidence.
   **Cause:** the actual mistake, stated as broadly as it really applies.
   **Fix:** what changed.
   **Catch earlier:** the rule, test, hook or pattern that would have prevented it.
   ```

4. Update `.claude/agent-memory/learner/MEMORY.md`: one line per lesson,
   sorted by hits, most first.
5. **Promote** when `hits >= 2` (or the person asks): edit a
   `.claude/rules/*.md` file or skill, or add a test or hook check. Set
   `level:` to `rule`, `skill`, `test`, `hook` or `pattern`.

### Patterns (what works)

Patterns live in `.claude/skills/splunk-playbook/patterns/`, indexed in that
skill's `SKILL.md`. Follow the format there.

- A pattern names a feature (`follow-user-theme`), not an app. Its
  **Why this way** lists the approaches that failed, linking their lessons;
  that is what stops the next agent from trying them again.
- Write only what was observed working in this repo: by a green stage, a
  UI test, a screenshot you looked at, or the person confirming it.
- When the same pattern is confirmed in a second app, consider promoting
  it: a scaffold step in `new-app`, a template file, or a hook check.
- Update the table in `splunk-playbook/SKILL.md` (pattern, use when, confirmed count).
- When a lesson's **Fix** is really a recipe for building something, put the
  recipe in a pattern and keep the lesson as evidence: shorten its Fix to a
  pointer, add a `**Pattern:**` line, set `level: pattern`, and link the
  lesson from the pattern's **Why this way**. Hits still count on the lesson.

## Review (`--review`)

Merge duplicate lessons and patterns, rename any scoped to an app whose cause
applies more broadly, delete lessons with `level: lesson` not seen in 60 days,
confirm each promoted lesson's rule still exists, check each pattern's
reference paths still exist, and keep `MEMORY.md` under 100 lines and root
`CLAUDE.md` under 200.

## Constraints

- Never edit `.claude/settings.json` or the hook scripts' deny lists without
  saying so explicitly in the final answer: those are the safety layer.
- Lessons and patterns describe this repo's reality, with evidence. No
  generic advice.
- Finish with the list of files changed and, for each, which question it answers.
