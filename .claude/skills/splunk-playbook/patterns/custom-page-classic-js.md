---
confirmed: 7
seen: [2026-11-12, 2026-11-14, 2026-11-14, 2026-11-14, 2026-11-16, 2026-11-17, 2026-11-18]
apps: [easyadmin]
---
# Custom page: Classic dashboard hosting JavaScript

**Use when:** the app needs an interactive page (editable grids, forms, one
bulk submit) that Dashboard Studio cannot express. For read-only panels of
search results, use Dashboard Studio instead (see the searches-dashboards rule).

**Recipe:**

1. `default/data/ui/views/<view>.xml`: a Simple XML `<dashboard version="1.1"
   script="<app>_<page>.js" stylesheet="<app>_<page>.css" hideEdit="true">`
   with one `<html>` panel holding an empty container `<div id="<app>-...">`.
   No inline `<script>`, no `<?xml ...?>` declaration, ASCII only.
2. `appserver/static/<app>_<page>.js`: plain ES5, no build step, wrapped in
   `require(['jquery', 'splunk.util', 'splunkjs/mvc/simplexml/ready!'], ...)`.
3. Build every element with `document.createElement` and set content with
   `.text()`, `.val()` or `.attr()`. Never `.html()` or string concatenation
   of server data.
4. Call the app's endpoint at `splunkUtil.make_url('/splunkd/__raw/services/<path>')`.
   For POST, send the header `X-Splunk-Form-Key: splunkUtil.getFormKey()`.
5. `default/data/ui/nav/default.xml` with the view as `default="true"`.
6. Increment `[install] build` in `app.conf` for **every deploy** that
   changes `appserver/static/`, again if the current number was already
   served (not once per release).
7. Keep page logic thin: validation and meaning live server-side in
   `bin/<app>_core.py`, where they are unit-tested. That includes text that
   varies by section: a per-tab note is a `note` key on the tab in the core
   model (unit-tested, `None` when absent), and the JS legend appends
   `tab.note` only when set and explains lists only when the tab has a list
   field (`legend()` in `easyadmin_roles.js`; UI test
   `test_imported_value_is_shown_under_a_setting`). Kept after UX review.
8. Pages that re-render the whole body (`easyadmin_apps.js`):
   - put the `role=status` and `role=alert` live regions **outside** the
     re-rendered body, created once, and set their text only when it changes;
   - give every focusable control a `data-fid` and restore focus, caret and
     scroll after each render, so typing in a filter is not lost;
   - filters narrow items, never the containers that are drop or move
     targets (`lessons/ux-filter-hides-drop-target.md`);
   - a button whose state depends on an input is updated from that input's
     handler, not only at render (`lessons/ux-every-control-needs-a-ui-test.md`);
   - when a status's meaning changes, change its badges, colours and
     strikethrough with the words, and assert `getComputedStyle` in a UI test
     (`lessons/ux-label-meaning-needs-matching-style.md`);
   - a staged change that takes an object out of a box keeps a row there
     until Apply, with its own look and its own `data-fid`: a move shows a
     struck-through "moving to <app>" row with a discard button, not the
     dashed `ea-ghost` ("not here yet") nor `ea-deleted` ("being deleted"),
     and cannot be ticked or dragged; hidden-by-filter counts include it
     (`renderMovingOut`, `objectsByApp`; 1.6.4, three UI tests red on 1.6.3
     then green). The row was never seen in a UX-review screenshot, so look
     at it once in a real browser.
   - a filter over a large list is debounced and redraws only the grid, not
     the page (`patterns/large-list-filter-debounce.md`; 1.7.2). The "filters
     re-render and restore focus" approach above is only fine for small models.
   - tabs: `role=tablist/tab/tabpanel` with `aria-controls`, roving tabindex
     and arrow keys; a `#hash` deep link kept with `history.replaceState`;
     explanations in a `<details>` whose open state is kept in page state so
     it survives re-renders (`easyadmin_apps.js`, precedence tab).
   - text that must match the body font size inherits it: a UI test
     (`test_edit_is_staged_with_old_and_new_value_and_can_be_discarded`)
     failed `'12px' == '14px'` because the page's root class
     (`.ea-settings`) fixed 12px, so changing only the child rules did
     nothing. Check the whole ancestor chain, and assert `getComputedStyle`.
   - a fixed side panel must not cover the page's own buttons: toggle an
     `ea-panel-open` class on the page root in `buildPanel()` and let the
     stylesheet pad the toolbar (and selection bar) by panel width plus a gap,
     plain px not a variable (asset tests read `--ea-*` as palette colours;
     `test_an_open_panel_keeps_the_toolbar_clear`). Toolbar buttons then call
     `leavePanel()` first: it closes the panel, confirming only when
     `panelTyping()` (input not yet staged, compared with the draft the panel
     opened with) would be lost, and clears the panel's drafts (easyadmin 1.7.1;
     87 UI tests green). Open the screenshot: the selection-bar clearance was
     fixed after review without being looked at.
9. Bulk or destructive edits: stage, then one Apply that reports a result per
   object; keep failed items staged for retry, and re-key staged edits for an
   object whose location changed in a partial apply.
**Why this way:**
- `version="1.1"` selects the current jQuery, which AppInspect requires of a
  dashboard that loads custom JavaScript.
- Splunk Web caches static files by `[install] build`. Without a bump, a green
  deploy still serves the old JS, and a hard refresh does not help
  (`lessons/conf-app-build-static-cache.md`). `/<locale>/_bump` clears it by hand.
- `text()`-only rendering means a role or index name with markup cannot run
  script in an administrator's session.
- Splunk Web rejects state-changing proxy requests without the form key.

**Verify:** `tests/ui/<app>/`: the page renders its main element, has no page
errors, and each control does what it says, secondary panels included: an
untested bulk-panel control shipped a Major (`write-ui-test` skill). Look at
the screenshot. Check static changes with `splk shot <app>/<view>` after the
build bump.

**Reference:** `apps/easyadmin/default/data/ui/views/role_management.xml`,
`apps/easyadmin/appserver/static/easyadmin_roles.js`,
`tests/ui/easyadmin/test_easyadmin_ui.py`; steps 8 and 9 in
`views/app_management.xml`, `easyadmin_apps.js`,
`tests/ui/easyadmin/test_easyadmin_apps_ui.py`.
