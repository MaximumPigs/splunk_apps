---
hits: 1
seen: [2026-11-18]
area: ux
level: lesson
---
**Symptom:** easyadmin 1.7.1, panel/toolbar change: after the review fix
(selection bar also reserved space beside the open panel) `splk dev` stopped at
unit: `tests.test_easyadmin_assets::test_an_open_panel_keeps_the_toolbar_clear:
AssertionError: no rule keeps the toolbar clear of an open panel`. The CSS
rule had become a selector list (`.ea-toolbar, .ea-selection`) and the test
looked for a single selector. Next run green after the test split the list on
commas. The loop-review summary also admits the new screenshots were not opened
to confirm the selection bar now clears the panel.
**Cause:** a CSS asset test that locates a rule by its exact selector breaks
when a legitimate edit groups selectors. Separately, the fix to a UX finding was
asserted only by that CSS text test, not by a layout measurement, so only the
unit stage noticed the change.
**Fix:** test matches the selector as a member of the comma-split list and
compares `padding-right >= panel width`.
**Catch earlier:** in `tests/test_easyadmin_assets.py` helpers, match selectors
as list members. For a layout claim ("clears the panel") add a UI test with
`bounding_box` of the toolbar buttons against the panel, and look at the
screenshot after a review-driven fix.
