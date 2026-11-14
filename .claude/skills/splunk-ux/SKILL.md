---
name: splunk-ux
description: The UX standard for every page an app shows in Splunk Web (dashboards, custom pages, setup pages, navigation). Read before building or changing a view, page JavaScript or CSS; the ux-reviewer checks work against it.
argument-hint: "[area]"
---

# Splunk UX standard

What a good page in this repo looks like. Builders read it before writing a
view; `splk ux` checks the parts a machine can; the `ux-reviewer` agent
(`splunk-ux-review` skill) judges the rest from screenshots and code. Each
item has an id so findings can cite it (`[UX-S2]`).

A user of these apps is a Splunk admin or analyst: they already know Splunk
Web, so the best page is one that looks and behaves like the rest of it, then
gets out of the way.

## How it is enforced

| Layer | Checks | Runs |
| --- | --- | --- |
| `splk ux <app>` (also the last stage of `splk dev`) | Every view in light and dark: screenshot, theme actually drawn, axe-core WCAG 2.2 A/AA scan of the app's own content, uncaught exceptions, the app's own console errors. Blocks on serious or critical axe findings and on errors. | Every dev loop, unattended |
| UI tests (`write-ui-test`) | Behaviour the README promises: states, validation, tabs, theme following. | Every dev loop |
| `splunk-ux-review` | This standard, item by item, from the screenshots and the source. | After a UI change; the Stop hook asks |

Per-app settings live in `tests/ui/<app>/ux.toml`: a `ready` selector and a
`scope` (the app's root element) per view, and waivers. A waiver needs a
reason; use one only for something outside the app's control, never to get
green.

## The standard

### Look: belong in Splunk Web (L)

- **L1** Use Dashboard Studio for pages of searches and charts. Use a Classic
  dashboard hosting app JavaScript only for what Studio cannot express
  (editable forms, grids, bulk changes): see the playbook pattern
  `custom-page-classic-js`.
- **L2** Inherit Splunk Web's font family and base size; do not set your own.
  Headings, labels and body text follow the surrounding page's scale.
- **L3** Controls look like Splunk Web's own: buttons, inputs, tabs and
  tables in the same shapes and weights. A primary action is visually
  distinct, and there is at most one per area.
- **L4** Spacing is consistent: one spacing scale for the app, the same
  padding in every panel, aligned edges.
- **L5** No decoration without a job: no custom logos, gradients or animations
  inside a working page.

### Theme: both themes, always (T)

- **T1** `app.conf [ui] supported_themes = light,dark`, and the page follows
  the user's preference (playbook pattern `follow-user-theme`).
- **T2** Every colour comes from CSS custom properties on the app's root, with
  light defaults and a `<app>-dark` override set. No colour literal outside
  those two blocks.
- **T3** Both themes meet the contrast rules in A1, including states (hover,
  selected, changed, disabled, error) and badges.
- **T4** Both themes are seen before the work is called done: `splk ux`
  screenshots them, and the reviewer opens both.

### States: never a blank or silent page (S)

- **S1** Loading: the page says what it is loading in words
  ("Loading roles...") within the first paint. Never an empty panel.
- **S2** Empty: say why there is nothing and what to do
  ("No roles are visible to your account."). A filter with no matches says so
  and names the filter.
- **S3** Errors: say what failed, in the user's terms, with the server's
  message when it helps, and what to do next. Never a stack trace, raw JSON,
  or "Error: undefined". An error does not wipe the user's unsaved input.
- **S4** Success: after a change, confirm what was done ("Saved 3 roles.").
  A partial failure lists each item that failed and why, and keeps those
  edits so they can be retried.
- **S5** Disabled controls say why (a tooltip or nearby text), or are hidden
  when the user can never use them.
- **S6** Anything over about a second shows progress, and the user cannot
  submit the same change twice while it runs.

### Input: safe, clear changes (I)

- **I1** Validate next to the field, as early as possible, and say the rule
  ("Must be a whole number of MB"), not just "invalid".
- **I2** Unsaved changes are visible (a count, a marker on changed cells) and
  marked by more than colour (A4). Leaving with unsaved changes asks first.
- **I3** Bulk or destructive actions say how many objects they touch before
  they run, and can be cancelled.
- **I4** The page acts with the signed-in user's own permissions (the
  security rules) and says plainly when an action was refused for lack of
  them.

### Words (W)

- **W1** British spelling, sentence case for labels, titles and buttons.
- **W2** Splunk's own terms, as Splunk Web uses them: index, role,
  capability, saved search, app. Show a setting's conf name beside a friendly
  label when admins will look it up (`Search jobs quota (srchJobsQuota)`).
- **W3** Buttons are verbs that say what happens ("Save changes", not "OK").
- **W4** Messages are short, specific and blame-free; they tell the user
  what to do next.
- **W5** Numbers, sizes and times are formatted for people (`1,024 MB`,
  relative or ISO times), units always shown.

### Accessibility: WCAG 2.2 AA (A)

- **A1** Contrast at least 4.5:1 for text, 3:1 for large text and for the
  edges of controls and focus indicators, in both themes. (axe checks text.)
- **A2** Every control has an accessible name: a `<label>`, or `aria-label`
  where a visible label would be redundant (a grid cell's checkbox named
  `role / capability`). (axe checks.)
- **A3** Everything works from the keyboard, in reading order, with a
  visible focus indicator. Do not remove outlines without a replacement.
  Custom widgets use the matching roles and states (`role="tab"`,
  `aria-selected`). (axe checks roles; the reviewer checks focus from CSS.)
- **A4** Never colour alone: changed, error, effective or disabled states
  also have text, an icon, a border or a pattern.
- **A5** Status and error messages are announced: put them in an element with
  `role="status"` (or `role="alert"` for errors).
- **A6** Images and icons that carry meaning have text alternatives;
  decorative ones are hidden from assistive tech.

### Layout (Y)

- **Y1** Works at 1280 px wide without horizontal page scroll; wide grids
  scroll inside their own container, with the header row and first column
  kept in view.
- **Y2** Long names (roles, indexes, fields) wrap or truncate with the full
  text available on hover; they never overlap neighbours.
- **Y3** The main task is above the fold; secondary settings are behind tabs
  or sections rather than one long page.

## Severity (for findings)

- **Blocker:** a user cannot complete the task, loses data, or is misled
  about what was saved; or an automated `splk ux` blocker.
- **Major:** a standard item fails in a way most users will notice: a missing
  state, a theme that is unreadable, a keyboard trap, a confusing label on a
  primary action.
- **Minor:** a standard item fails in a corner: one inconsistent spacing, a
  message that could be clearer.
- **Polish:** taste, not standard. Report at most three, clearly labelled.

## Keeping the standard alive

The standard holds only what this repo has seen matter. When a review finds
a good solution, the `retro` skill records it as a playbook pattern; when a
finding repeats in two apps, it becomes an item here, a UI test, or a `splk
ux` check. Remove an item that has stopped earning its place.
