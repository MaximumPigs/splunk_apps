---
confirmed: 1
seen: [2026-11-14]
apps: [easyadmin]
---
# Show which file sets a conf value (precedence, like btool)

**Use when:** a page or endpoint must say which app and layer
(`local`/`default`) set a `.conf` value, or which apps clash. Observed on
Splunk 10.6.1; pinned by `tests/live/easyadmin/test_easyadmin_conf_live.py`.

**Recipe:**

1. Read the files, read-only, from a persist handler (own script, per
   `rest-endpoint-behind-page`): `etc/system/local`, each
   `etc/apps/<app>/local`, each `etc/apps/<app>/default`, `etc/system/default`.
2. Order, highest first (btool's global context): system/local, app locals in
   **ASCII** order of directory name (uppercase before lowercase), app
   defaults in ASCII order, system/default (`precedence_order()` in
   `easyadmin_conf_core.py`). Live-verified: `launcher/local` beats
   `search/local`.
3. List only layers that have the file: `etc/system/default` has no
   `macros.conf` (`lessons/conf-system-default-not-every-file.md`).
4. For search-time files (props, transforms, macros, eventtypes, tags,
   savedsearches, fields...) the app a search runs in decides, not the global
   order: show the order without calling a value "in effect", in words **and**
   styling (`SEARCH_TIME_CONFS`; `lessons/ux-label-meaning-needs-matching-style.md`).
5. Hardening, all passed `splunk-security-review` (20:45:31, nothing above LOW):
   - `restmap.conf` `capability = admin_all_objects`, re-checked in core from
     `current-context` (403 otherwise);
   - conf name allow-list ending in `\Z`, never `$`; `passwords` excluded;
   - app names only from `os.listdir`, never from the request; `realpath`
     must stay inside `etc/`;
   - per-file and total character caps (read at most cap + 1), total over
     cap returns 413; long values truncated;
   - secrets masked by name **suffix** (`\Z`) plus an exact-name list
     (`SECRET_RE`, `SECRET_NAMES`), unit-tested both ways
     (`lessons/security-secret-name-match-anchored.md`);
   - one audit log line per read (user, conf, count).

**Why this way:** splunkd's `configs/conf-<name>` under `/servicesNS/-/-`
returns one entry per (app, stanza), but its content is the merged result in
that app's context: the Monitoring Console's `[scheduler]` props entry held
`EXTRACT-fields`, which only the search app sets, plus every `[default]`
value. REST cannot attribute a value to an app or layer; only the files can
(docstring of `easyadmin_conf_core.py`). Reading files from a persist handler
passed the full untagged local AppInspect run with no new findings or manual
checks. **Not yet vetted by the AppInspect API** (CI runs only on PRs):
confirm on the PR before claiming Cloud-ready.

**Verify:** unit tests over order, masking and name checks
(`tests/test_easyadmin_conf_core.py`); live tests that a clash between two
`local` folders is reported in order, secrets never returned, bad and
excluded names refused, a user without `admin_all_objects` refused; UI tests
in `tests/ui/easyadmin/test_easyadmin_conf_ui.py`.

**Reference:** `apps/easyadmin/bin/easyadmin_conf_core.py`,
`apps/easyadmin/bin/easyadmin_conf_rest.py`,
`apps/easyadmin/default/restmap.conf` (`[script:easyadmin_conf]`).
