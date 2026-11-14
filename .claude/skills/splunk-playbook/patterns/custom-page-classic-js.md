---
confirmed: 2
seen: [2026-11-12, 2026-11-14]
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
errors, and each control does what it says (`write-ui-test` skill). Look at
the screenshot. Check static changes with `splk shot <app>/<view>` after the
build bump.

**Reference:** `apps/easyadmin/default/data/ui/views/role_management.xml`,
`apps/easyadmin/appserver/static/easyadmin_roles.js`,
`tests/ui/easyadmin/test_easyadmin_ui.py`.
