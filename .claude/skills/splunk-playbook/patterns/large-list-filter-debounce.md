---
confirmed: 1
seen: [2026-11-18]
apps: [easyadmin]
---
# Fast filters on a large list page

**Use when:** a custom page filters hundreds of boxes or thousands of rows as
the person types (App management: 300 apps, 5000 objects). Typing `perf_obj`
took about 8.0 s to settle; after the change about 1.2 s (easyadmin 1.7.2,
measured on a stubbed model).

**Recipe:**

1. Measure first. `tests/ui/easyadmin/test_easyadmin_apps_perf_probe.py` is an
   opt-in probe (`EASYADMIN_PERF_PROBE=1`): it stubs the list response with a
   big model through `page.route` (nothing on the target changes), times each
   keystroke and profiles which functions the time goes to. Fix what it shows,
   not what looks slow.
2. Keep two values per filter: the draft the field holds and the value the
   grid shows. The `input` handler sets the draft and calls `filterSoon()`
   (250 ms timer, reset per key). Only the timer copies draft to shown value.
   A full `render()` calls `flushFilters()` first so it shows the field text
   and cancels the timer.
3. A filter change calls `renderFilterResults()`: build the new grid and
   `replaceChild` the old one. The toolbar is never rebuilt, so the caret
   stays and no focus restore (a whole-page layout, about 40% of the cost) is
   needed. Restore only the boxes' scroll and focus that was on a row control.
4. Build rows with `document.createElement` helpers (`node()`, `setAttrs()`)
   instead of jQuery chains, and cache each SVG icon once and `cloneNode`.
   Still `textContent`/`setAttribute` only, so no markup from server data.
5. Stamp the grid with `data-filter` / `data-app-filter` so a test can wait on
   the redraw, which is otherwise not observable.

**Why this way:**
- Redrawing on every keystroke rebuilt the whole page; debouncing alone left
  the full render, so both the pause and the partial redraw are needed.
- Native `replaceChild` is safe only because nothing inside the grid has a
  directly bound handler (all delegated from `$root`); keep it that way.
- A click during the pause acts on the list the person can see, because the
  shown value changes only when the timer fires.

**Verify:** UI tests in `tests/ui/easyadmin/test_easyadmin_apps_ui.py` (four
new ones failed on 1.7.1, three by timing out on the missing `data-filter`),
then the probe for before and after numbers. Not solved: one keystroke on the
big model still costs about 0.6 s of browser layout; the fix (cap or lazily
draw rows) changes what a box lists, so it is an owner decision.

**Reference:** `apps/easyadmin/appserver/static/easyadmin_apps.js`
(`filterSoon`, `flushFilters`, `renderFilterResults`, `node`, `icon`).
