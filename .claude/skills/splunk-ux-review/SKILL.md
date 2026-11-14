---
name: splunk-ux-review
description: UX review of an app's pages (views, page JavaScript and CSS, navigation) against the splunk-ux standard, from screenshots in both themes and the source, reporting findings for fixing. Use after changing anything a user sees in Splunk Web, before opening a PR, when the Stop hook asks, or when the person asks for a UX review.
argument-hint: "<app-id> [view]"
context: fork
agent: ux-reviewer
---

# UX review: `$ARGUMENTS`

Scope: an app id (every view of that app), or an app id and one view.

UI files changed on this branch:

!`git diff --name-only origin/main...HEAD -- "apps/*/appserver/*" "apps/*/default/data/ui/*"`

## Steps

1. Read the `splunk-ux` skill: it is the standard you review against.
2. Run the audit, which screenshots every view in both themes and scans it:

   ```bash
   splk ux <app> [--view <view>] --json
   ```

   Then read `build/reports/ux/<app>/report.md`. If the audit could not run
   (sign-in, app not deployed, Playwright missing), stop and report that as
   the result: a review without screenshots is a guess.
3. **Open every screenshot with Read**, light and dark. Where the report says
   a theme was not audited (the page follows the user's preference), say so
   in the report as a coverage gap; do not change the preference.
4. Read the view XML, the page's JavaScript and CSS, and the app README.
   The source shows what screenshots cannot: loading, empty and error states
   (`S1` to `S6`), validation messages, focus styles (`A3`), whether colour is
   the only signal (`A4`), live regions (`A5`), and the wording of every
   message (`W`).
5. Go through the standard item by item. For each item that applies, record
   pass or a finding. Use `splk shot <app>/<view> --theme <t> --wait-for
   <selector>` to look at a state the audit did not capture, if it can be
   reached without saving anything.
6. Record the outcome, one `--detail` per finding:

   ```bash
   splk review ux <app> fail --summary "1 major, 3 minor" \
       --detail "[MAJOR] UX-S3 easyadmin_roles.js:247 error replaces the grid; unsaved edits lost" \
       --detail "[MINOR] ..."
   ```

   `pass` when no Blocker or Major finding remains, `fail` otherwise. The
   Stop hook treats the UI as reviewed from this moment.
7. Return the report (format below) as your final answer.

## Report format

```markdown
# UX review: <app>, <YYYY-MM-DD HH:MM>
Audit: <summary line from report.md>. Screenshots opened: <list>.
Not covered: <themes or states not seen, and why>.

## Findings
### [MAJOR] UX-S3 <short title>
- **Where:** view, theme, screenshot path and/or source path:line
- **Seen:** what the user sees or experiences (quote the screenshot or code).
- **Fix:** the concrete change (code if short).
- **Confidence:** seen in <screenshot> | inferred from <path:line>

## Passes
- <standard items that applied and passed, one line each>

## Patterns worth keeping
- <a solution other apps should copy, with its file path>, or "None".
```

Order findings most severe first. If there are none, write "No findings"
and keep the Passes list, so the reader knows what was covered.

## After the review (main agent)

Fix Blocker and Major findings, deploy, and run this skill again on the same
scope. Minor and Polish: fix, or list them for the person with the reason
they remain. Ask the person only for judgement calls the standard does not
settle, and attach the screenshots. Pass "Patterns worth keeping" to the
`retro` skill, which records them in the `splunk-playbook`; a finding that
repeats becomes a standard item, a UI test or a `splk ux` check.
