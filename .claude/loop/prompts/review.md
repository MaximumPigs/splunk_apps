## Step: review the branch

Review everything on this branch since `main` (`git diff main...HEAD`).

1. Run the `splunk-security-review` skill. Fix every finding that should be
   fixed before merging; record the outcome with `splk review security ...`.
2. If a view, page script or stylesheet changed, run `splk ux {{app}}` and
   the `splunk-ux-review` skill. Fix findings; record with `splk review ux ...`.
3. Run the `splunk-reviewer` agent on the change and fix what it finds.
4. Re-run `splk dev {{app}}` after fixes; it must be green.

Findings you deliberately leave go into {{pr_body_file}} under "Open
findings", each with the reason, so the owner sees them in the PR.

Write the same findings to {{findings_file}} too, so the next groom step adds
them to ROADMAP.md as proposals. One block per finding:

    ### <app or Tooling>: <short title>
    Source: security | ux | splunk-reviewer; severity: <severity>
    Where: <file:line>
    <what is wrong, evidence observed, the fix you would make, and why it was
    left (out of scope, needs the owner, predates this change)>

Leave {{findings_file}} absent when you left no findings.
