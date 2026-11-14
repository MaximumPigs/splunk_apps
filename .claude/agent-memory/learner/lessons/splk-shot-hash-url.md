---
hits: 1
seen: [2026-11-14]
area: splk
level: lesson
---
**Symptom:** easyadmin 1.3.0. `splk shot easyadmin/app_management#precedence`
timed out: the `#` reached Splunk Web as `%23`, so the view name was wrong and
the ready selector never appeared.

**Cause:** `tools/splk/ui.py` builds the view URL with
`urllib.parse.quote(view, safe="")`, which encodes `#`. `splk shot` has no
way to pass a URL fragment, so any view that picks a tab or state from the
hash cannot be screenshotted in that state.

**Fix:** none in `splk`. Workaround: a UI test that clicks the tab, and
`test_easyadmin_conf_ui::test_precedence_link_opens_the_tab`, which opens
`page.goto(web.url("/app/<app>/<view>#precedence"))` directly.

**Catch earlier:** candidate `splk` improvement (not built; `tools/splk` was
not changed): a `--hash <fragment>` option on `splk shot` (and `splk ux`
views in `ux.toml`) appended after quoting. Until then, look at hash states
through a UI test's `shot()`. Noted in playbook `verify-in-browser`.
