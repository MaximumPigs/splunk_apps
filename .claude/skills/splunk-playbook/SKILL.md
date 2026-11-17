---
name: splunk-playbook
description: Proven ways to build Splunk app features in this repo (custom pages, dashboard JavaScript, REST endpoints behind a page, theme support, search commands, checking UI in a browser). Read before building or changing one of these, and update after finding a better way.
argument-hint: "[area or feature]"
---

# Splunk playbook

How this repo builds things that work, learned by building them. Lessons
(`.claude/agent-memory/learner/`) record what went wrong; this playbook
records **what works**, so the next feature starts from the approach that
finally worked instead of rediscovering it.

## Use it

1. Find the pattern for the feature below and read it **before** writing code.
2. Follow it unless you have a reason not to. If you deviate, say why in the
   PR description.
3. After the work, the `retro` skill updates the pattern: confirm it
   (`confirmed` +1 and date), correct it, or add a new one. A pattern that
   was wrong is fixed in the same PR as the code that proved it wrong.

## Patterns

| Pattern | Use when | Confirmed |
| --- | --- | --- |
| [Custom page: Classic dashboard hosting JavaScript](patterns/custom-page-classic-js.md) | An app needs an interactive page (forms, grids, bulk edits) that Dashboard Studio cannot express. | 7 (easyadmin) |
| [REST endpoint behind a page](patterns/rest-endpoint-behind-page.md) | The page reads or writes splunkd state through the app's own Python. | 6 (easyadmin) |
| [Follow the user's light/dark theme](patterns/follow-user-theme.md) | Any app view, especially Classic dashboards with custom CSS. | 1 (easyadmin) |
| [Read and write roles through splunkd REST](patterns/splunkd-roles-rest-api.md) | Code or live tests touching `authorization/roles`: types, ordering, capabilities, throwaway roles, scoping to Splunk Web's role editor. | 2 (easyadmin) |
| [List, move and re-permission knowledge objects](patterns/splunkd-knowledge-objects-rest.md) | Code or live tests listing objects across apps, moving or copying them, changing owner/sharing/perms, deleting, an object's own settings. | 3 (easyadmin) |
| [Show which file sets a conf value](patterns/conf-precedence-from-files.md) | Attributing `.conf` values to an app and layer, clashes, btool-like views; reading conf files safely. | 2 (easyadmin) |
| [Custom search command](patterns/search-command.md) | Adding an SPL command with splunklib. | 1 (fillcontinuous) |
| [See it in a browser before claiming it works](patterns/verify-in-browser.md) | Any change whose effect is only visible in Splunk Web. | 2 (easyadmin) |
| [Observe a tool's real behaviour first](patterns/observe-tool-behaviour-first.md) | `splk` code or hooks depend on headless `claude -p` output, a guard's verdict or a git side effect. | 1 (splk) |
| [Probe a hook from a Python file](patterns/probe-a-hook-with-decide.md) | Changing or reviewing a deny rule in `.claude/hooks/`; testing both the deny corpus and the false positive. | 1 (repo hooks) |
| [Give an unattended loop its secrets and settings safely](patterns/loop-secrets-across-privilege-drop.md) | A container or supervisor starts `splk loop` steps and must pass credentials or target settings. | 1 (splk loop; unbuilt) |
| [Cap the size of one POST](patterns/request-size-cap.md) | A page sends one user-sized request (bulk Apply); needs a server 413 backstop and a page-side refusal. | 1 (easyadmin) |

## Writing a pattern

One file per pattern in `patterns/`, named for the feature, not the app.
Keep each under about 80 lines; link to the real files rather than pasting
them. Shape:

```markdown
---
confirmed: 1            # times it was followed and worked, across apps
seen: [YYYY-MM-DD]
apps: [easyadmin]       # where it is in use: the reference implementations
---
# <Pattern name>

**Use when:** the situation.
**Recipe:** the steps, in order, with the file each step touches.
**Why this way:** the constraint behind each non-obvious step, and the
alternatives that were tried and failed (with the lesson file, if any).
**Verify:** how to prove it works: unit, live and UI tests, or `splk shot`.
**Reference:** paths in this repo that implement it.
```

Write only what this repo has observed working. A pattern for something not
yet built here is a guess: leave it out.
