## Step: implement the item (attempt {{attempt}})

The item is in {{item_file}}, the plan in {{plan_file}}. The last
verification failure, if any:

    {{last_failure}}

Use the `dev-loop` skill and iterate until `splk dev {{app}}` is green
(`--restart` is allowed on the local target). Meet CLAUDE.md's definition of
done items 1 to 4: unit test for pure logic, live test for real SPL results
(`write-live-test`), UI test for anything visible (`write-ui-test`),
`[launcher]` and `[id]` versions bumped and matching (and `[install] build`
bumped if `appserver/static` changed), the app README updated.

Write the new unit, live or UI tests first and run them against the current
code before changing the app: record in {{pr_body_file}} that each failed,
and how (CLAUDE.md: prove a fix closes the original reproduction, before and
after). Skip this only for a test of something that did not exist before,
and say so in the PR body.

Also:

- Move the item to the app's Done table in ROADMAP.md with the new version
  (keep any answered questions out of the table).
- Write {{pr_title_file}} (one line, e.g. `easyadmin 1.5.0: export and import`)
  and {{pr_body_file}} (what changed and why, how it was verified, anything
  left open). British spelling, no tool names.

If attempt is 3 or more, step back first: re-read the failure evidence
(screenshots, logs, timestamps) before changing more code. Finish `done` only
when `splk dev {{app}}` was green on your last run.
