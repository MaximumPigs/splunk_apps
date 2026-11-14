---
confirmed: 2
seen: [2026-11-14, 2026-11-14]
apps: [easyadmin]
---
# See it in a browser before claiming it works

**Use when:** a change shows only in Splunk Web: a view, a page's JavaScript,
CSS, a theme, navigation, layout. `splk search` and REST cannot observe these,
and four published claims were wrong because nobody looked
(`lessons/docs-unobserved-claims.md`).

**Recipe:**

1. Deploy (`splk dev <app> --skip-inspect`). If static files changed, bump
   `[install] build` first (again if that number was already served), or
   Splunk Web serves the old ones. If `bin/` changed behind a persist
   handler, check a label only the new code shows before trusting the page.
2. Look: `splk shot <app>/<view> [--theme dark] --wait-for "<selector>"`.
   It prints JSON with the screenshot path, the final URL, and any console
   and page errors. **Open the PNG with Read and check it shows what you
   meant.** A non-empty `page_errors` means the page's JavaScript threw.
3. Encode what you saw as a UI test in `tests/ui/<app>/` (`write-ui-test`
   skill), so it stays checked by `splk dev`. `splk ux <app>` screenshots
   every view in both themes and scans it for accessibility problems; the
   `splunk-ux-review` skill judges the result against the `splunk-ux` standard.
4. Document the behaviour only after steps 2 and 3. Ask the person to look
   only for judgement calls (does it look right, is it readable), and say what
   you already checked.

**Why this way:** a screenshot the agent reads is an observation, which turns
"should work" into "seen working", without waiting for the person.

Seen working on easyadmin 1.1.0 (2026-11-14): a `shot` per settings tab in
the UI test gave the UX review its evidence, and the probe's `-FAILED.png`
showed the role editor's real layout at once. Again on 1.2.0: the drag
test's `-FAILED.png` showed the hidden drop target in one look
(`lessons/ux-filter-hides-drop-target.md`).

`splk shot` cannot open a `#hash` state (`#` is encoded to `%23` and times
out): for tab or hash states, `shot()` inside a UI test that clicks the tab
or `page.goto(web.url(".../<view>#<hash>"))`
(`lessons/splk-shot-hash-url.md`).

**Verify:** the UI stage of `splk dev <app>` is green, and the screenshot in
`build/reports/ui/<app>/` shows the feature.

**Reference:** `tools/splk/ui.py`, `tests/ui/conftest.py`,
`tests/ui/easyadmin/test_easyadmin_ui.py`.
