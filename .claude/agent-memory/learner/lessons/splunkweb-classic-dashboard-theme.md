---
hits: 1
seen: [2026-11-14]
area: splunkweb
level: lesson
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

**Fix:** easyadmin's endpoint returns the caller's `user-prefs` theme (read
with their own session; `default_system_theme` and unset mean "leave it").
The page reloads once with `?theme=<preference>` when the background Splunk
drew does not match, and never reloads if the URL already names that theme,
so an ignored parameter cannot loop. The panel's palette follows the
background Splunk drew. `supported_themes = light,dark` is kept as the app's
declaration of support. See `apps/easyadmin/appserver/static/easyadmin_roles.js`
(`matchSplunkTheme`) and `apps/easyadmin/bin/easyadmin_rest.py` (`_user_theme`).

**Catch earlier:** for any app with Classic dashboards, follow the user's
theme with the `?theme=` reload, not `supported_themes` alone and not a
second in-page selector. Hard-coding `theme="dark"` in the XML forces it on
everyone. Dark-mode blockers reported by the community: non-ASCII characters
or an `<?xml ...?>` declaration in the dashboard XML. Theme changes can only
be checked in a browser, so ask the person to look before calling it done.
