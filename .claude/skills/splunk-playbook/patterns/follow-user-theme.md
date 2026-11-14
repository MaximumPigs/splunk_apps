---
confirmed: 1
seen: [2026-11-14]
apps: [easyadmin]
---
# Follow the user's light/dark theme

**Use when:** an app ships a view, and above all a Classic dashboard with its
own CSS. Users set the theme in Splunk Web (account preferences), which is
stored as `user-prefs.conf [general] theme`.

**Recipe:**

1. `app.conf [ui] supported_themes = light,dark`, to declare support.
2. The page's endpoint returns the caller's preference: read
   `/servicesNS/<user>/user-prefs/data/user-prefs/general` with the caller's
   session, and normalise it to `light`, `dark` or none (`default_system_theme`
   or unset mean "leave it alone").
3. In the page JS, once the preference is known: if it is light or dark, and
   the background Splunk drew is the other one, `location.replace()` the page
   with `?theme=<preference>`. **Never reload when the URL already names that
   theme**, so a parameter Splunk ignores cannot cause a loop.
4. Style the panel from what Splunk actually drew: walk up from the container
   to the first opaque background, compute its luminance, and toggle a
   `<app>-dark` class. Do not rely on Splunk's internal DOM markers for dark
   mode; they differ between versions.

**Why this way:** Classic dashboards take their theme from the dashboard XML
or the `?theme=` URL parameter, defaulting to light. They ignore the user's
preference, and `supported_themes` alone changes nothing visible (observed on
10.6.1, even after a restart). Three attempts were needed: an in-page theme
selector (rejected: it themed only the panel, and the owner wanted Splunk's
own setting respected), `supported_themes` alone (no effect), then the reload,
which worked. Hard-coding `theme="dark"` in the XML forces it on everyone.
Reported dark-mode blockers: non-ASCII characters or an `<?xml ...?>`
declaration in the dashboard XML.

**Verify:** `splk shot <app>/<view> --theme dark` and `--theme light`, then
look at both screenshots. `tests/ui/easyadmin/test_easyadmin_ui.py` has the
reusable assertions: the page ends in the user's preference, and opening it
with the other `?theme=` corrects itself once.

**Reference:** `apps/easyadmin/appserver/static/easyadmin_roles.js`
(`matchSplunkTheme`, `splunkIsDark`), `apps/easyadmin/bin/easyadmin_rest.py`
(`_user_theme`), `easyadmin_core.theme_preference`.
History: `.claude/agent-memory/learner/lessons/splunkweb-classic-dashboard-theme.md`.
