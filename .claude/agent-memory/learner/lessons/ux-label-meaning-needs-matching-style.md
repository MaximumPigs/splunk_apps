---
hits: 1
seen: [2026-11-14]
area: ux
level: pattern
---
**Symptom:** easyadmin 1.3.0 precedence tab; `splunk-ux-review` failed twice
on one root cause. 20:35:54 Major: "'in effect' is asserted from the global
order for search-time files (macros, props, eventtypes, tags,
savedsearches); app/user context and sharing decide those". The first fix
changed only the words. 20:43:55 Major: "search-time files still strike
through and mute every value after the first (and give the first a green
pill), the visual signal for overridden; contradicts the new notice and
labels". Passed at 20:51:59 after the styling followed.

**Cause:** the meaning was carried by styling as well as by text (green
"in effect" pill, strikethrough and muting on later values). Changing the
label without the classes left the page still saying "this one wins".
Any page where a status is shown by badge colour, strikethrough or icons
has the same trap.

**Fix:** `renderSetting(setting, searchTime)` in
`apps/easyadmin/appserver/static/easyadmin_apps.js` applies the winner and
`ea-prec-overridden` classes only when `!searchTime`, with neutral "first /
later in global order" badges; the core sends `search_time` per conf
(`SEARCH_TIME_CONFS` in `easyadmin_conf_core.py`). The UI test asserts
`getComputedStyle(n).textDecorationLine` (`test_easyadmin_conf_ui.py`).

**Catch earlier:** when a label's meaning changes, grep for every class and
style tied to the old meaning and change them together; assert the computed
style in a UI test, not just the text. Playbook `custom-page-classic-js`.

**Pattern:** `custom-page-classic-js` (step 8).
