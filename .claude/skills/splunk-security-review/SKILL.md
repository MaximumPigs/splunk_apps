---
name: splunk-security-review
description: Security review of new or changed code (app Python, REST handlers, dashboard JavaScript, conf and metadata, splk and hooks), reporting findings for fixing. Use after writing or changing code, before opening a PR, when the Stop hook asks, or when the person asks for a security review.
argument-hint: "[app-id | path | --all]"
context: fork
agent: security-reviewer
---

# Security review: `$ARGUMENTS`

Scope: empty = everything changed on this branch; an app id = `apps/<app>/`
in full; a path = that path; `--all` = every app.

Changed files on this branch:

!`git diff --name-only origin/main...HEAD`

Uncommitted and untracked:

!`git status --porcelain`

## Steps

1. List the files in scope. Skip `apps/*/lib/` (vendored, verified by hash)
   unless the change touched it. Read each file in full, not only the diff:
   a safe-looking change can expose an unsafe path elsewhere.
2. For every entry point (REST handler, search command, page script, scripted
   input, CLI command), trace attacker-controlled input to every sink.
3. Work through the checklist below. Check every item that applies.
4. Record the outcome in the run log, one `--detail` per finding:

   ```bash
   splk review security <scope> fail --summary "1 high, 2 low" \
       --detail "[HIGH] apps/x/bin/x_rest.py:88 role name not quoted in path" \
       --detail "[LOW] ..."
   ```

   Use `pass` when nothing Critical, High or Medium remains, `fail`
   otherwise. `<scope>` is the app id when the review covered one app, else
   `branch`. The Stop hook treats code as reviewed from this moment, and a
   `fail` later followed by a `pass` on the same scope is picked up by
   `retro` as a fixed failure.
5. Return the report (format below) as your final answer.

## Checklist

**REST handlers (`restmap.conf`, `bin/*_rest.py`)**
- `requireAuthentication = true`. `passSystemAuth` false, or a written reason:
  the system token lets any caller act as splunkd.
- Authorisation is enforced by splunkd (calls made with the caller's own
  session token) or checked explicitly with capabilities. Never by role name.
- Every name placed in a splunkd path is URL-quoted with `safe=""`; no `..`
  or `/` reaches a path; field names are checked against an allow-list.
- Request bodies: size and count limits, JSON errors handled, types checked.
- Errors returned to the browser do not include tokens, stack traces or
  other users' data. Logs record who changed what, but no secrets.
- `web.conf [expose:]` patterns are as narrow as possible, with only the
  methods used.

**Page JavaScript and dashboards**
- Server or event data reaches the DOM only through `.text()`, `.val()`,
  `.attr()` (not `href`/`src` with user data), or `textContent`. Flag
  `.html()`, `.append(string)`, `innerHTML`, `document.write`, `eval`,
  `new Function`, `setTimeout(string)`, and building selectors from data.
- State-changing requests send `X-Splunk-Form-Key`; nothing changes state on GET.
- No inline `<script>`, no external scripts, styles or fonts, no secrets in
  JS or XML.
- Simple XML tokens in `<html>` panels or drilldown URLs: check escaping
  (`$token|h$`, `|u$`).

**Searches and search commands**
- No user or event data concatenated into SPL that is then run (SPL
  injection), into `| rest` paths, or into shell commands.
- Resource bounds: row counts, expansion products, recursion, regex on
  attacker data (ReDoS). See `.claude/rules/search-commands.md`.
- `commands.conf` does not set `requires_srinfo` or `passauth` unless needed.

**Permissions and packaging (`metadata/default.meta`, `app.conf`)**
- `write` lists hold only admin roles (`admin`, `sc_admin`); no `*` writes.
- `export = system` only for objects other apps must see.
- No `local/`, `local.meta`, `.env`, keys, tokens or test credentials in the
  package (check `scripts/package_app.py` exclusions if paths changed).

**Python generally**
- No `subprocess` with `shell=True` on data, no `eval`/`exec`, `pickle`,
  `yaml.load` without SafeLoader, `tempfile.mktemp`, or `os.system`.
- File paths from input are resolved and confined to the app directory.
- TLS verification is on except where a target explicitly disables it for a
  local self-signed certificate.
- Credentials come from `storage/passwords` (apps) or the environment
  (tooling), never from conf files or source.
- Broad `except` blocks do not hide authentication or authorisation failures.

**Repository tooling (`tools/splk`, `.claude/hooks`, workflows)**
- Secrets masked in logs (`splk.logs.SecretMaskingFilter`); `.env` never read
  into output; hook deny lists not weakened.
- Workflows: actions pinned to SHAs; secrets not echoed; `pull_request_target`
  not combined with checking out PR code.

## Report format

```markdown
# Security review: <scope>, <YYYY-MM-DD HH:MM>
Files reviewed: <n> (<list or summary>)

## Findings
### [HIGH] <short title>
- **Where:** path:line
- **Issue:** what is wrong.
- **Attack:** who controls what input, the path to the sink, what they gain.
- **Fix:** the concrete change (code if short).
- **Confidence:** verified by tracing <...> | inferred because <...>

## Checked, no issues
- <checklist areas that applied and passed, one line each>
```

Order findings most severe first. If there are none, write "No findings"
under Findings and keep the "Checked" list, so the reader knows what was covered.

## After the review (main agent)

Fix Critical and High findings before finishing, then run this skill again
on the same scope. Medium and lower: fix, or list them for the person with
the reason they remain. Each fixed finding is a candidate lesson for the
`retro` skill (area `security`), so the same class of bug gets a rule.
