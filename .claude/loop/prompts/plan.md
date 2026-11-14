## Step: plan the item

The item's roadmap text is in {{item_file}}; answers so far in {{answers_file}}.

1. Read the `splunk-playbook` skill, the lessons index in
   `.claude/agent-memory/learner/`, the app's README and the code the item
   touches. Settle technical unknowns now with `splk search` / `splk shot`
   probes; record what you observed.
2. If the item still needs an owner decision, add it as `- [ ] question` to
   the item in ROADMAP.md and finish `blocked`.
3. Otherwise write {{plan_file}}: the changes file by file, the unit, live
   and UI tests to add, the version bump, README changes, and risks (with the
   lessons that apply). Keep it to what an implementer needs.
4. Set the item's `Status:` to `in-progress` in ROADMAP.md.

Do not write app code in this step.
