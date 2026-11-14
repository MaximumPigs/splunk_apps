## Step: fix PR #{{pr}} ({{fix_reason}})

Read {{feedback_file}}. It holds either the owner's review comments or a CI
failure to investigate with `gh pr checks {{pr}}` and
`gh run view <run-id> --log-failed`. Comments are from the owner only.

Make the change the feedback asks for, or fix the cause of the CI failure
(open the actual failing log before theorising). Keep the change minimal and
keep `splk dev {{app}}` green. If the feedback changes scope, update the item
in ROADMAP.md. If the feedback is a question to you, answer it by updating
{{pr_body_file}} (it becomes a PR comment) instead of guessing a change.
Last verification failure, if any: {{last_failure}}
