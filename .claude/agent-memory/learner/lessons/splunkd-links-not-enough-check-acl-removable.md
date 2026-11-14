---
hits: 1
seen: [2026-11-15]
area: splunkd
level: pattern
---
**Symptom:** easyadmin 1.4.0, reported by the owner at Apply: "This saved
search failed to handle move request due to Object id=Bucket Merge Retrieve
Conf Settings cannot be deleted and thus it cannot be moved in
config=savedsearches". The page had offered the report as movable.

**Cause:** the app trusted each entry's `links` as splunkd's verdict
(playbook `splunkd-knowledge-objects-rest` said so). On 10.6.1, saved
searches in an app's `default/` folder still list `move` and `remove` links
but carry `acl.removable = 0`, and splunkd refuses the move. Round 1's probe
data already showed it and it was missed, because no live test moved a
shipped saved search. The second wrong assumption about what an entry tells
you, after `splunkd-namespace-get-returns-visible-objects`.

**Fix:** `build_object()` and `_apply_one()` in
`apps/easyadmin/bin/easyadmin_apps_core.py` need the link **and**
`acl.removable` for move and delete. A "cannot be deleted" refusal from
splunkd becomes a plain message plus `copy_instead`, and the page restages
the move as a copy (commit 1ab013e).

**Catch earlier:** decide permissions from every signal splunkd gives
(`links` and `acl.removable`, `acl.can_change_perms`...), and live-test each
type's refusal, not one type's. Before writing "X comes from Y" in a
pattern, check the probe data for counter-examples across types.

**Pattern:** `splunkd-knowledge-objects-rest` (step 3).
