---
hits: 1
seen: [2026-11-14]
area: ux
level: pattern
---
**Symptom:** easyadmin 1.2.0 App management. UI run at 17:49:24:
`test_easyadmin_apps_ui::test_drag_to_another_app_stages_a_move_and_apply_makes_it`
failed with `Locator.drag_to: Timeout 30000ms exceeded`. The `-FAILED.png`
showed at once that the target app's box was gone.

**Cause:** the first design applied the text filter to the app boxes as well
as the objects, hiding every app with no matching object. Filtering to find
an object then removed the place to drop it. Any page that combines a filter
with drag and drop (or any "pick an item, then a container") breaks the same
way.

**Fix:** the filter narrows objects, never the apps that are drop targets
(`apps/easyadmin/appserver/static/easyadmin_apps.js`, comment above the
filtering code); an app with no match says so inside its box. UI green at
17:53:03.

**Catch earlier:** playbook `custom-page-classic-js` step on filters and
containers. Reading the `-FAILED.png` first (`verify-in-browser`) found it in
one look.

**Pattern:** `custom-page-classic-js`.
