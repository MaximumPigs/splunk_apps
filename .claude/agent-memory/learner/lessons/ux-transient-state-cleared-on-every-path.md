---
hits: 1
seen: [2026-11-16]
area: ux
level: lesson
---
**Symptom:** easyadmin 1.6.3 (request cap): the UX review found the "Not
staged" cap-refusal alert stayed in the side panel after the user undid the
change or discarded all staged changes. The loop log: "stale cap-refusal alert
fixed (cleared on undo and discard)". Build bumped to 44. The same run's first
UI stage also went red (2 cap tests, `Locator.inner_text` timeout); its cause
was not recorded, so it is not claimed here.
**Cause:** a transient message held in page state (`state.capRefusal`) was
cleared on the paths the author thought of (new stage, close) but not on every
path that changes what the message describes. No test exercised undo or discard
after a refusal.
**Fix:** `state.capRefusal = null` in the undo and discard handlers.
**Catch earlier:** for any transient message in page state, list the handlers
that mutate the state it describes and add a UI assertion after each. Pattern
`request-size-cap` step 4.
