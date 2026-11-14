## Step: review the code base for improvements

No roadmap item is ready, so look for work worth proposing. Review every app
under `apps/` and the tooling (`tools/splk`, `scripts/`, `.claude/hooks/`):
read the code, the app READMEs, the lessons index in
`.claude/agent-memory/learner/` and recent run failures (`splk runs --days 30`).

Look for, in this order of value:

1. Bugs: behaviour that is wrong or will break (verify with `splk search`,
   `splk shot` or a unit test before claiming it).
2. Security: anything the `splunk-security-review` skill would flag.
3. Efficiency: slow searches, needless REST round trips, heavy pages.
4. Refactoring that removes real duplication or risk (not taste).
5. Small improvements users would notice.

Add each finding as a new item at the end of its app's section in ROADMAP.md
(repo-wide ones under `## Tooling`, created if missing), at most 8 in total,
best first:

    ### Proposed: <short title>
    Status: proposed

    <what, where (file:line), why it matters, evidence you observed>

    - [ ] Confirm: should this be done? (<your recommendation>)

Do not change any code. Edit ROADMAP.md only. Status `done` when written,
even if you found nothing (then say so and add nothing).
