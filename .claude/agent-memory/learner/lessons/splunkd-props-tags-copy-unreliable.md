---
hits: 1
seen: [2026-11-14]
area: splunkd
level: pattern
---
**Symptom:** easyadmin 1.4.0, copying props-based objects (field
extractions, aliases, calculated fields, automatic lookups, sourcetype
renames) and tags into another app. Live runs 22:22:07 to 22:41:40 failed
`test_props_extraction_is_copied_through_props_conf` (`assert 'system' ==
'launcher'`) and `test_tag_is_copied_through_tags_conf`. Observed on 10.6.1:
- `POST /servicesNS/nobody/launcher/configs/conf-props` creating
  `[access_combined]` returned 409 "already exists", though only
  `etc/system/default` has that stanza;
- `GET .../launcher/configs/conf-props/<stanza>` then reported
  `acl.app = launcher` (the merged view, see
  `conf-precedence-from-files`);
- the fallback update returned success but nothing reached
  `launcher/local/props.conf` (checked with the app's own conf-reading
  endpoint);
- `saved/fvtags` reports a tag as belonging to whichever app asks.

**Cause:** `configs/conf-*` and `saved/fvtags` present a merged, per-app
view, so neither "does it exist here" nor "did the write land here" can be
answered through them. Any feature that writes props or tags into a chosen
app through REST has this problem.

**Fix:** those types have `"copy": None` in `TYPES`
(`apps/easyadmin/bin/easyadmin_apps_core.py`); the page says why they cannot
be copied; live test `test_props_objects_and_tags_are_not_offered_for_copying`.

**Catch earlier:** verify where a write landed by reading the file
(`conf-precedence-from-files` endpoint), not by REST read-back.

**Pattern:** `splunkd-knowledge-objects-rest` (Copy).
