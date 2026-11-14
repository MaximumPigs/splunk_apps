---
hits: 1
seen: [2026-11-14]
area: splunkweb
level: pattern
---
**Symptom:** easyadmin's Classic (Simple XML) dashboard stayed light while the
owner's Splunk account was set to dark (`user-prefs` `[general] theme = dark`),
on Splunk 10.6.1. It took three attempts:
1. A page-level palette with its own Light/Dark selector only themed the
   app's panel; the rest of the dashboard stayed white. The owner wanted
   Splunk's own theme setting respected, not a second selector.
2. `[ui] supported_themes = light,dark` in `app.conf` changed nothing visible,
   even after a restart.
3. Reloading the page with `?theme=<preference>` worked (owner confirmed).

**Cause:** a Classic dashboard takes its theme from its own XML (`theme`
attribute on the root element) or from a `?theme=` URL parameter, defaulting
to light. It does not follow the user's theme preference, and
`supported_themes` does not change that. Splunk's spec only says the theme
applies "if supported by the app", without saying how. The working mechanism
came from Splunk Community threads and was confirmed by the owner in a
browser.

**Fix:** a loop-guarded reload with `?theme=<user-prefs theme>`. The recipe
now lives in the playbook: `.claude/skills/splunk-playbook/patterns/follow-user-theme.md`.

**Catch earlier:** follow that pattern for any app view. Check theme changes
with `splk shot <app>/<view> --theme dark` and the UI tests in
`tests/ui/easyadmin/`, which assert the page ends in the user's preference.
