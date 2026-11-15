## Step: groom the roadmap

Read all of ROADMAP.md, then the owner's answers in {{answers_file}}.

1. Record every answer in the item it belongs to: turn the question into
   `- [x] question: answer`, in the owner's meaning, without embellishing.
   Fold agreed requirements into the item's text where that reads better.
2. Review **every** item that is not done for ambiguity: what would an
   implementer have to guess? For each gap that is the owner's decision, add
   `- [ ] question` to that item. Make each question answerable in one reply
   (offer the options you see and your recommendation). Do not ask what the
   code, Splunk docs or a probe can settle; note those as "Probe first:" lines.
3. Set each item's `Status:` line (directly under its heading):
   `ready` when it has no open question and enough detail to build,
   `blocked` when it has open questions, `proposed` for an unconfirmed
   proposal, `done` only when it is shipped (and move it to the app's Done
   table instead). Keep `in-progress` as it is.
4. Keep the roadmap's priority order; never reorder items.
5. Read {{review_findings_file}} if it exists: findings the review step left
   unfixed on recent PRs. For each one, check it still applies on this
   branch (read the file it names). If an item already covers it, add the
   finding to that item. Otherwise add it at the end of its app's section
   (repo-wide ones under `## Tooling`) as:

       ### Proposed: <short title>
       Status: proposed

       <what, where (file:line), why it matters, the PR it came from>

       - [ ] Confirm: should this be done? (<your recommendation>)

   Drop a finding only when the code shows it is already fixed, and say so
   in your summary. Adding these items is not reordering.

Edit ROADMAP.md only. Status `done` when the roadmap is groomed (even if
nothing is ready), `failed` only if you could not edit it.
