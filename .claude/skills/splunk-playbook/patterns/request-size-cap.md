---
confirmed: 1
seen: [2026-11-16]
apps: [easyadmin]
---
# Cap the size of one POST (server backstop, page refuses first)

**Use when:** a page sends one request whose size the user controls (bulk
Apply, import) and neither Splunk Web nor splunkd bounds it.

**Recipe:**
1. Server: a byte constant and a check that runs on the raw body before it is
   parsed, raising the app's error with status 413 and a message that says the
   size, the limit and what to do (`check_request_size` in
   `apps/easyadmin/bin/easyadmin_apps_core.py`). Pure logic, unit tested.
2. Page: mirror the limit in JS and refuse at the click that would take the
   staged changes over it. Put the staged state back as it was, keep the
   editor/form/panel open with what was typed, and say "Not staged" plus the
   remedy (`easyadmin_apps.js`, `capRefusal`).
3. Show the refusal where the user is looking. A side panel covers the page's
   message area, so render the message inside the panel too
   (`.ea-panel-refusal`, `role="alert"`).
4. Clear the refusal on every path that changes what it describes (undo,
   discard, a successful stage, closing the panel).
5. Test hook: `?ea_max_request_bytes=<n>` that can only LOWER the cap. Reaching
   16 MB through the UI needs hundreds of edits; with a 600-byte cap, one
   long value does it. A raise-capable hook would be a bypass.

**Why this way:** a probe passed 64 MB bodies through Splunk Web to the handler
and splunkd's `max_content_length` is 2 GB, so the app has to set its own.
Per-value and per-object limits alone multiply to far more than any sane
request. Refusing only on the server loses the user's typed work to an error;
refusing at staging keeps it. A stale refusal alert survived undo and discard
until the UX review caught it (lesson `ux-transient-state-cleared-on-every-path`).

**Verify:** live test posts an over-cap body and expects 413; UI tests in
`tests/ui/easyadmin/test_easyadmin_request_cap_ui.py` (one per staging control
family, shorter value then stages). Refusal state was only seen in source by
the UX review, so take a `splk shot` with the hook before claiming it looks right.

**Reference:** `apps/easyadmin/bin/easyadmin_apps_core.py`,
`apps/easyadmin/appserver/static/easyadmin_apps.js`,
`tests/live/easyadmin/test_easyadmin_apps_live.py`.
