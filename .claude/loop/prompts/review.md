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
