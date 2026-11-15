"""`splk loop`: work through ROADMAP.md unattended, one PR at a time.

The supervisor is plain Python. It never decides anything a model should,
and a model never decides anything a script can check: every judgement step
(groom, audit, plan, implement, review, retro, fix) is one headless
`claude -p` run with a fresh context and its own model, and every check
(is `splk dev` green, did the PR merge, did CI fail) is done here.

State lives in .agent/loop/state.json and is saved after every phase, so
Ctrl+C, a crash, a reboot or a usage limit loses at most the step that was
running; `splk loop run` carries on from the saved phase.

Phases:

    groom -> plan -> implement -> verify -> review -> verify -> retro -> publish -> await
          \\-> audit -> publish (roadmap PR)          await -> fix -> verify -> push -> await
          \\-> blocked (waiting for answers)          await -> merged -> groom

Only the owner merges. The supervisor pushes feature branches and opens PRs;
steps may do neither. Three layers keep it that way: steps run with
SPLK_LOOP=1, which turns on the hooks' loop rules (no push, merge, PR or
GitHub API calls, no edits to hooks, settings or the loop itself); the CLI
gets --disallowedTools for the same commands; and a ruleset on GitHub must
protect main, because hooks are a client-side check and a step can run code.
"""

import datetime
import glob
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request

try:  # Python 3.11+
    import tomllib
except ImportError:  # pragma: no cover - exercised on the 3.9 CI leg
    import tomli as tomllib

from splk import config, loop_core, paths, runlog
from splk.logs import get_logger

log = get_logger("loop")

LOOP_DIR = os.path.join(paths.AGENT_DIR, "loop")
STATE_FILE = os.path.join(LOOP_DIR, "state.json")
PAUSE_FILE = os.path.join(LOOP_DIR, "PAUSE")
LOCK_FILE = os.path.join(LOOP_DIR, "lock")
STEPS_DIR = os.path.join(LOOP_DIR, "steps")
NOTIFY_LOG = os.path.join(LOOP_DIR, "notifications.log")
# The supervisor's inputs to steps (the item and the owner's words) live in
# inbox/, which the file guard protects; steps write their outputs to
# handoff/, the only folder of .agent/ they may write.
INBOX_DIR = os.path.join(LOOP_DIR, "inbox")
HANDOFF_DIR = os.path.join(LOOP_DIR, "handoff")
ITEM_FILE = os.path.join(INBOX_DIR, "item.md")
ANSWERS_FILE = os.path.join(INBOX_DIR, "answers.md")
FEEDBACK_FILE = os.path.join(INBOX_DIR, "feedback.md")
PLAN_FILE = os.path.join(HANDOFF_DIR, "plan.md")
PR_TITLE_FILE = os.path.join(HANDOFF_DIR, "pr-title.txt")
PR_BODY_FILE = os.path.join(HANDOFF_DIR, "pr-body.md")

CONFIG_FILE = os.path.join(paths.CONFIG_DIR, "loop.toml")
PROMPTS_DIR = os.path.join(paths.REPO_ROOT, ".claude", "loop", "prompts")
ROADMAP_FILE = os.path.join(paths.REPO_ROOT, "ROADMAP.md")
PACKAGES_DIR = os.path.join(paths.REPO_ROOT, "packages")
QUESTION_LABEL = "loop-question"

# Second layer behind the bash guard's SPLK_LOOP rules: the CLI itself refuses
# these tools in a step. The supervisor pushes and handles PRs.
DISALLOWED_TOOLS = ["Bash(git push:*)", "Bash(gh pr merge:*)", "Bash(gh pr create:*)",
                    "Bash(gh pr comment:*)", "Bash(gh api:*)", "Bash(gh issue:*)", "Bash(gh repo:*)"]

STEP_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["done", "blocked", "failed"]},
        "summary": {"type": "string"},
    },
    "required": ["status", "summary"],
}


class LoopError(Exception):
    """A step the loop cannot get past without the owner."""


# ------------------------------------------------------------------ settings

def load_settings(path=CONFIG_FILE):
    with open(path, "rb") as handle:
        return tomllib.load(handle)


def find_claude(settings):
    """The CLI to run. The VS Code extension bundles one that is not on PATH."""
    candidates = [settings.get("claude", {}).get("path") or "", os.environ.get("SPLK_CLAUDE", ""),
                  shutil.which("claude") or ""]
    for candidate in candidates:
        if candidate and os.path.isfile(candidate):
            return candidate
    pattern = os.path.join(os.path.expanduser("~"), ".vscode", "extensions", "anthropic.claude-code-*",
                           "resources", "native-binary", "claude*")
    bundled = [p for p in glob.glob(pattern) if os.path.basename(p) in ("claude", "claude.exe")]
    if bundled:
        return max(bundled, key=os.path.getmtime)
    raise LoopError("Claude Code CLI not found: set [claude] path in config/loop.toml or SPLK_CLAUDE")


# --------------------------------------------------------------------- state

def utc_now():
    # Same shape as GitHub's createdAt, so the two compare correctly as text.
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return {"phase": "groom", "item": None, "parked": {}}


def save_state(state):
    os.makedirs(LOOP_DIR, exist_ok=True)
    state["updated"] = utc_now()
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2)
    # Atomic on both platforms: a crash mid-write never leaves half a state.
    os.replace(tmp, STATE_FILE)


def write_file(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def step_environment():
    """The environment for a step: without .env's secrets, with SPLK_LOOP=1.

    `splk` loads .env into os.environ for every command, so without this each
    step could print the Splunk token and password into its transcript. The
    splk commands a step runs reload .env themselves.
    """
    env = dict(os.environ)
    from_env_file = {}
    config.load_env_file(environ=from_env_file)
    for key in from_env_file:
        if env.get(key) == from_env_file[key]:
            env.pop(key, None)
    # Read by the hooks: stricter rules for unattended steps.
    env["SPLK_LOOP"] = "1"
    # Steps never push, so git gets no stored credentials (fetching a public
    # repo needs none). Without this a step could push as the owner.
    # Appended after any GIT_CONFIG_* entries already set, not replacing them.
    try:
        index = int(env.get("GIT_CONFIG_COUNT", "0"))
    except ValueError:
        index = 0
    env["GIT_CONFIG_COUNT"] = str(index + 1)
    env["GIT_CONFIG_KEY_%d" % index] = "credential.helper"
    env["GIT_CONFIG_VALUE_%d" % index] = ""
    # With a read-only token (fine-grained: this repo, read access), steps
    # can read CI results but GitHub itself refuses any merge or write.
    # Without one they use the owner's gh login and only the hooks stand
    # between a step and a merge.
    read_only = from_env_file.get("SPLK_LOOP_GH_TOKEN") or os.environ.get("SPLK_LOOP_GH_TOKEN")
    if read_only:
        env.pop("SPLK_LOOP_GH_TOKEN", None)
        env["GH_TOKEN"] = read_only
        env["GH_CONFIG_DIR"] = os.path.join(LOOP_DIR, "gh-readonly")
        os.makedirs(env["GH_CONFIG_DIR"], exist_ok=True)
    return env


def clear_handoff():
    """Start an item with no plan, PR text or feedback left from the previous one."""
    for path in (PLAN_FILE, PR_TITLE_FILE, PR_BODY_FILE, FEEDBACK_FILE):
        if os.path.exists(path):
            os.remove(path)


def read_file(path, default=""):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return handle.read()
    except OSError:
        return default


class SingleInstance(object):
    """An OS file lock, released by the OS if the process dies.

    A pid file would need a liveness check, and on Windows os.kill(pid, 0)
    terminates the process instead of probing it.
    """

    def __enter__(self):
        os.makedirs(LOOP_DIR, exist_ok=True)
        self.handle = open(LOCK_FILE, "a+")
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.handle.close()
            raise LoopError("Another `splk loop run` is already running")
        return self

    def __exit__(self, *exc):
        self.handle.close()


# ------------------------------------------------------------ git, gh, notify

def run(cmd, check=True, timeout=600):
    log.debug("Running %s", " ".join(cmd))
    proc = subprocess.run(cmd, cwd=paths.REPO_ROOT, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout)
    if check and proc.returncode != 0:
        raise LoopError("%s failed: %s" % (" ".join(cmd[:3]), (proc.stderr or proc.stdout).strip()[:800]))
    return proc


def git(*args, **kwargs):
    return run(["git"] + list(args), **kwargs).stdout.strip()


def gh(*args, **kwargs):
    return run(["gh"] + list(args), **kwargs).stdout.strip()


def changed_files():
    """Tracked files with changes plus untracked ones, repo-relative."""
    # Not git(): it strips the output, and the leading space of " M path" is
    # part of the format (stripping it read ROADMAP.md as OADMAP.md).
    out = run(["git", "status", "--porcelain", "-z"]).stdout
    return loop_core.parse_porcelain_z(out)


def new_branch(name):
    """Create (or reset) a work branch at HEAD that tracks nothing.

    A branch tracking main is one Sync click in an editor away from pushing
    to main: VS Code ran `git push origin <branch>:main` for exactly that
    reason (2026-11-15). The branch gets its own upstream on first push.
    """
    git("checkout", "-q", "--no-track", "-B", name)
    # -B keeps the upstream of a branch that already existed; drop it.
    git("branch", "--unset-upstream", check=False)


def commit_all(message):
    """Commit everything as the owner (git's configured identity). False if nothing changed."""
    if not changed_files():
        return False
    git("add", "-A")
    path = os.path.join(LOOP_DIR, "commit-msg.txt")
    write_file(path, message.strip() + "\n")
    git("commit", "-q", "-F", path)
    return True


def notify(state, message, settings):
    """Tell the owner: log, notifications file, run log and (if set up) ntfy."""
    log.warning("NOTIFY: %s", message)
    os.makedirs(LOOP_DIR, exist_ok=True)
    with open(NOTIFY_LOG, "a", encoding="utf-8") as handle:
        handle.write("%s %s\n" % (utc_now(), message))
    item = state.get("item") or {}
    runlog.record("loop", item.get("app") or "repo", "loop-notify", True, message)
    topic = os.environ.get("SPLK_NTFY_TOPIC")
    if not topic:
        return
    server = settings.get("notify", {}).get("server", "https://ntfy.sh").rstrip("/")
    headers = {"Title": "splunk_apps loop"}
    if os.environ.get("SPLK_NTFY_TOKEN"):
        # Access-controlled topic (self-hosted ntfy, or ntfy.sh reserved topics):
        # without it, anyone who learns the topic name can read the messages.
        headers["Authorization"] = "Bearer " + os.environ["SPLK_NTFY_TOKEN"]
    request = urllib.request.Request("%s/%s" % (server, topic), data=message.encode("utf-8"), headers=headers)
    try:
        urllib.request.urlopen(request, timeout=20).read()
    except Exception as exc:  # A failed notification must not stop the loop.
        log.warning("ntfy failed: %s", exc)


def owner_login(state):
    if not state.get("owner"):
        state["owner"] = gh("api", "user", "--jq", ".login")
    return state["owner"]


# --------------------------------------------------------------------- steps

def run_step(name, state, settings, model_key=None, extra=None):
    """Run one headless Claude step. Returns (kind, structured_output).

    kind is ok | rate_limit | error (loop_core.classify_result).
    """
    template = read_file(os.path.join(PROMPTS_DIR, name + ".md"))
    if not template:
        raise LoopError("Missing prompt %s.md in .claude/loop/prompts" % name)
    common = read_file(os.path.join(PROMPTS_DIR, "_common.md"))
    item = state.get("item") or {}
    values = {
        "item_file": paths.display(ITEM_FILE), "answers_file": paths.display(ANSWERS_FILE),
        "feedback_file": paths.display(FEEDBACK_FILE), "plan_file": paths.display(PLAN_FILE),
        "pr_title_file": paths.display(PR_TITLE_FILE), "pr_body_file": paths.display(PR_BODY_FILE),
        "app": item.get("app") or "(none: repo-wide work)", "title": item.get("title", ""),
        "branch": item.get("branch", ""), "attempt": state.get("attempt", 0) + 1,
        "last_failure": state.get("last_failure") or "(none)",
    }
    values.update(extra or {})
    prompt = loop_core.render_prompt(common + "\n\n" + template, values)

    claude_cfg, models, effort = settings["claude"], settings["models"], settings.get("effort", {})
    model = models[model_key or name]
    cmd = [find_claude(settings), "-p", prompt, "--model", model,
           "--output-format", "json", "--json-schema", json.dumps(STEP_SCHEMA),
           "--permission-mode", claude_cfg.get("permission_mode", "auto"),
           "--permission-prompts", "none", "--name", "loop-%s" % name,
           "--disallowedTools"] + DISALLOWED_TOOLS
    if effort.get(name):
        cmd += ["--effort", effort[name]]
    log.info("Step %s (%s) for %s", name, model, item.get("title") or "roadmap")
    started = time.time()
    try:
        proc = subprocess.run(cmd, cwd=paths.REPO_ROOT, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", env=step_environment(),
                              timeout=int(claude_cfg.get("step_timeout_hours", 4) * 3600))
        code, stdout, stderr = proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired:
        code, stdout, stderr = -1, "", "step timed out"
    try:
        data = json.loads(stdout) if stdout.strip() else {}
    except ValueError:
        data = {"result": stdout[-2000:]}
    kind, detail = loop_core.classify_result(code, data, stderr)
    output = data.get("structured_output") or {}

    os.makedirs(STEPS_DIR, exist_ok=True)
    record = {"step": name, "model": model, "exit": code, "kind": kind, "detail": detail,
              "seconds": round(time.time() - started), "output": output,
              "cost_usd": data.get("total_cost_usd"), "session_id": data.get("session_id"),
              "stderr": (stderr or "")[-2000:]}
    write_file(os.path.join(STEPS_DIR, "%s-%s.json" % (time.strftime("%Y%m%d-%H%M%S"), name)),
               json.dumps(record, indent=2))
    ok = kind == "ok" and output.get("status") == "done"
    runlog.record("loop", item.get("app") or "repo", "loop-" + name, ok,
                  output.get("summary") or detail or kind, [kind, model])
    return kind, output


# ---------------------------------------------------------- roadmap & issues

def roadmap_items():
    return loop_core.parse_roadmap(read_file(ROADMAP_FILE))


def question_issues():
    raw = gh("issue", "list", "--label", QUESTION_LABEL, "--state", "open", "--limit", "100",
             "--json", "number,title,url")
    return json.loads(raw or "[]")


def sync_question_issues(state, items, settings):
    """One open issue per item waiting on the owner; close the rest. Returns new issue URLs.

    A parked item's questions live on its branch, not in the roadmap being
    read, so its issue is kept open explicitly.
    """
    gh("label", "create", QUESTION_LABEL, "--color", "D93F0B", "--force",
       "--description", "The roadmap loop needs an answer", check=False)
    existing = {issue["title"]: issue for issue in question_issues()}
    wanted = {loop_core.issue_title(item): item for item in loop_core.awaiting_owner(items)}
    keep = set(wanted) | {p.get("issue_title") for p in (state.get("parked") or {}).values()}
    created = []
    for title, item in wanted.items():
        if title in existing:
            continue
        body_path = os.path.join(LOOP_DIR, "issue-body.md")
        write_file(body_path, loop_core.issue_body(item))
        url = gh("issue", "create", "--title", title, "--label", QUESTION_LABEL, "--body-file", body_path)
        created.append(url)
    for title, issue in existing.items():
        if title not in keep:
            gh("issue", "close", str(issue["number"]), "--comment",
               "Answers recorded in ROADMAP.md on branch %s." % git("branch", "--show-current"), check=False)
    return created


def collect_answers(state, since=None):
    """Write the owner's comments on question issues to ANSWERS_FILE.

    Returns {issue title: number of owner comments newer than ``since``}.
    Only the owner's comments are copied: anyone else's text is untrusted and
    must not reach a model as an answer.
    """
    owner = owner_login(state)
    cutoff = since or ""
    lines, new = [], {}
    for issue in question_issues():
        raw = gh("issue", "view", str(issue["number"]), "--json", "title,comments")
        data = json.loads(raw or "{}")
        answers = [c for c in data.get("comments") or []
                   if ((c.get("author") or {}).get("login") or "").lower() == owner.lower()]
        if not answers:
            continue
        lines.append("## %s (#%s)\n" % (data.get("title"), issue["number"]))
        for comment in answers:
            # ISO-8601 UTC strings compare correctly as text.
            if comment.get("createdAt", "") > cutoff:
                new[data.get("title")] = new.get(data.get("title"), 0) + 1
            lines.append("%s\n\n%s\n" % (comment.get("createdAt"), comment.get("body", "").strip()))
    write_file(ANSWERS_FILE, "\n".join(lines) if lines else "No answers from the owner yet.\n")
    return new


def stages_apps():
    from splk import stages
    return stages.discover_apps()


# -------------------------------------------------------------------- phases

def phase_groom(state, settings):
    dirty = [f for f in changed_files() if not f.startswith(".agent/")]
    if dirty:
        raise LoopError("Working tree has uncommitted changes (%s); commit or stash them" % ", ".join(dirty[:5]))
    git("checkout", "-q", "main")
    git("pull", "-q", "--ff-only")
    collect_answers(state)

    # A parked item (it hit an owner question mid-work) resumes first once answered.
    for key, parked in list((state.get("parked") or {}).items()):
        if collect_answers(state, since=parked["since"]).get(parked.get("issue_title")):
            log.info("Resuming parked item %s", key)
            git("checkout", "-q", parked["branch"])
            git("merge", "-q", "--no-edit", "main")
            state["item"] = parked["item"]
            state["parked"].pop(key)
            state.update(phase="implement", attempt=0, last_failure="Resumed after the owner answered")
            return

    kind, out = run_step("groom", state, settings)
    if kind != "ok":
        return _step_failed(state, settings, kind, out)
    stray = [f for f in changed_files() if f != "ROADMAP.md" and not f.startswith(".agent/")]
    if stray:
        raise LoopError("Groom may only edit ROADMAP.md but changed %s" % ", ".join(stray))

    items = roadmap_items()
    created = sync_question_issues(state, items, settings)
    parked = set((state.get("parked") or {}).keys())
    item = loop_core.next_item([i for i in items if i.key not in parked])
    stamp = time.strftime("%Y%m%d")
    if item is not None and item.app is not None and not loop_core.valid_app(item.app, stages_apps()):
        # The heading becomes an argument to splk and a glob in packages/.
        raise LoopError("Roadmap section %r is not an app under apps/ (or `## Tooling`)" % item.app)
    if item is not None:
        branch = loop_core.branch_for(item)
        state["item"] = {"key": item.key, "section": item.section, "title": item.title,
                         "app": item.app, "branch": branch, "kind": "feature"}
        new_branch(branch)
        commit_all("Roadmap: groom before %s" % item.title)
        clear_handoff()
        write_file(ITEM_FILE, item.text)
        state.update(phase="plan", attempt=0, fix_attempts=0, last_failure="")
    elif loop_core.should_audit([i for i in items if i.key not in parked]):
        state["item"] = {"key": "audit", "section": "Roadmap", "title": "Proposals from a code review",
                         "app": None, "branch": "roadmap/audit-%s" % stamp, "kind": "roadmap"}
        new_branch(state["item"]["branch"])
        commit_all("Roadmap: groom")
        state["phase"] = "audit"
    elif changed_files():
        state["item"] = {"key": "groom", "section": "Roadmap", "title": "Roadmap answers and questions",
                         "app": None, "branch": "roadmap/groom-%s" % stamp, "kind": "roadmap"}
        new_branch(state["item"]["branch"])
        commit_all("Roadmap: record answers and open questions")
        state["phase"] = "publish"
    else:
        state.update(phase="blocked", item=None, blocked_since=utc_now(),
                     main_sha=git("rev-parse", "origin/main"))
        waiting = [i.title for i in loop_core.awaiting_owner(items)]
        notify(state, "Loop waiting on your answers: %s. %s" % (
            "; ".join(waiting) or "nothing to do", " ".join(created)), settings)
    if created and state["phase"] != "blocked":
        notify(state, "New roadmap questions: %s" % " ".join(created), settings)


def phase_audit(state, settings):
    kind, out = run_step("audit", state, settings)
    if kind != "ok":
        return _step_failed(state, settings, kind, out)
    commit_all("Roadmap: proposals from a code review")
    sync_question_issues(state, roadmap_items(), settings)
    state["phase"] = "publish"


def phase_plan(state, settings):
    kind, out = run_step("plan", state, settings)
    if kind != "ok":
        return _step_failed(state, settings, kind, out)
    if out.get("status") == "blocked":
        return _park(state, settings, out)
    commit_all("%s: start %s" % (state["item"].get("app") or "repo", state["item"]["title"]))
    state["phase"] = "implement"


def phase_implement(state, settings):
    limits = settings["limits"]
    escalated = state.get("attempt", 0) >= limits.get("escalate_after", 2)
    kind, out = run_step("implement", state, settings,
                         model_key="implement_escalated" if escalated else "implement")
    if kind != "ok":
        return _step_failed(state, settings, kind, out)
    if out.get("status") == "blocked":
        return _park(state, settings, out)
    commit_all("WIP %s" % state["item"]["title"])
    state.update(phase="verify", after_verify="review")


def phase_verify(state, settings):
    """`splk dev` decides, not the model's summary."""
    app = state["item"].get("app")
    cmd = [sys.executable, "-m", "splk", "--json"]
    cmd += ["dev", app, "--restart"] if app else ["test"]
    proc = run(cmd, check=False, timeout=3 * 3600)
    if proc.returncode == 0:
        state.update(phase=state.get("after_verify", "review"), last_failure="")
        return
    failure = proc.stderr.strip()[-1500:]
    try:
        stages = json.loads(proc.stdout)
        failure = "; ".join("%s: %s %s" % (s.get("stage"), s.get("summary"), " | ".join(s.get("details", [])[:5]))
                            for s in stages if not s.get("ok")) or failure
    except ValueError:
        pass
    state["attempt"] = state.get("attempt", 0) + 1
    state["last_failure"] = failure
    limit = settings["limits"]["max_attempts"]
    if state["attempt"] >= limit:
        raise LoopError("splk dev still red after %d attempts: %s" % (limit, failure[:300]))
    # A red verify after a PR fix goes back to fix; otherwise to implement.
    state["phase"] = "fix" if state.get("after_verify") == "push" else "implement"


def phase_review(state, settings):
    kind, out = run_step("review", state, settings)
    if kind != "ok":
        return _step_failed(state, settings, kind, out)
    commit_all("Review fixes for %s" % state["item"]["title"])
    state.update(phase="verify", after_verify="retro")


def phase_retro(state, settings):
    kind, out = run_step("retro", state, settings)
    if kind != "ok":
        return _step_failed(state, settings, kind, out)
    commit_all("Retro: %s" % state["item"]["title"])
    state["phase"] = "publish"


def package_app(app):
    """Build the app's .spl into packages/, replacing older versions of it."""
    proc = run([sys.executable, os.path.join(paths.SCRIPTS_DIR, "package_app.py"), app,
                "--outdir", PACKAGES_DIR])
    built = [p for p in glob.glob(os.path.join(PACKAGES_DIR, "%s-*.spl" % app))]
    newest = max(built, key=os.path.getmtime) if built else None
    for path in built:
        if path != newest:
            os.remove(path)
    log.info("Packaged %s: %s", app, proc.stdout.strip() or newest)
    return newest


def phase_publish(state, settings):
    item = state["item"]
    if item.get("kind") == "feature" and item.get("app"):
        package_app(item["app"])
        commit_all("%s: package" % item["app"])
    git("push", "-q", "-u", "origin", item["branch"])
    title = read_file(PR_TITLE_FILE).strip() or item["title"]
    body = read_file(PR_BODY_FILE).strip() or "Roadmap item: %s / %s\n" % (item["section"], item["title"])
    body_path = os.path.join(LOOP_DIR, "pr-body-clean.md")
    write_file(body_path, loop_core.clean_pr_text(body) + "\n")
    existing = gh("pr", "list", "--head", item["branch"], "--state", "open", "--json", "number,url")
    prs = json.loads(existing or "[]")
    if prs:
        number, url = prs[0]["number"], prs[0]["url"]
    else:
        url = gh("pr", "create", "--base", "main", "--head", item["branch"],
                 "--title", loop_core.clean_pr_text(title), "--body-file", body_path)
        number = int(url.rstrip("/").rsplit("/", 1)[-1])
    for path in (PR_TITLE_FILE, PR_BODY_FILE):
        if os.path.exists(path):
            os.remove(path)
    state.update(phase="await", pr=number, pr_url=url, feedback_since=utc_now(), fix_attempts=0)
    notify(state, "PR #%s ready to merge: %s %s" % (number, title, url), settings)


def phase_await(state, settings):
    data = json.loads(gh("pr", "view", str(state["pr"]), "--json",
                         "state,headRefOid,statusCheckRollup,comments,reviews") or "{}")
    verdict = loop_core.pr_verdict(data, owner_login(state), state.get("feedback_since"))
    log.info("PR #%s: %s", state["pr"], verdict)
    if verdict == "merged":
        git("checkout", "-q", "main")
        git("pull", "-q", "--ff-only")
        git("branch", "-D", state["item"]["branch"], check=False)
        state.update(phase="groom", item=None, pr=None, pr_url=None, attempt=0, last_failure="")
        return
    if verdict == "closed":
        pause("PR #%s was closed without merging" % state["pr"])
        state.update(phase="groom", item=None, pr=None)
        notify(state, "PR closed without merging; loop paused. Update ROADMAP.md, then `splk loop resume`.", settings)
        return
    if verdict == "feedback":
        feedback = loop_core.owner_feedback(data, owner_login(state), state.get("feedback_since"))
        write_file(FEEDBACK_FILE, "# Owner feedback on PR #%s\n\n%s\n" % (
            state["pr"], "\n\n".join("%s %s\n%s" % (f["at"], f["state"], f["body"]) for f in feedback)))
        state["feedback_since"] = max(f["at"] for f in feedback)
        state.update(phase="fix", fix_reason="feedback")
        return
    if verdict == "ci_failed" and data.get("headRefOid") != state.get("ci_fixed_for"):
        state["ci_fixed_for"] = data.get("headRefOid")
        write_file(FEEDBACK_FILE, "# CI failed on PR #%s at %s\n\nRead the failing job with "
                   "`gh pr checks %s` and `gh run view <run-id> --log-failed`.\n" % (
                       state["pr"], data.get("headRefOid"), state["pr"]))
        state.update(phase="fix", fix_reason="ci")
        return
    sleep_unless_paused(settings["limits"]["poll_seconds"])


def phase_fix(state, settings):
    state["fix_attempts"] = state.get("fix_attempts", 0) + 1
    if state["fix_attempts"] > settings["limits"]["max_fix_attempts"]:
        raise LoopError("PR #%s still needs fixes after %d rounds" % (state["pr"], state["fix_attempts"] - 1))
    kind, out = run_step("fix", state, settings, extra={"pr": state.get("pr"),
                                                        "fix_reason": state.get("fix_reason", "")})
    if kind != "ok":
        return _step_failed(state, settings, kind, out)
    commit_all("Address %s on #%s" % ("review" if state.get("fix_reason") == "feedback" else "CI", state["pr"]))
    state.update(phase="verify", after_verify="push")


def phase_push(state, settings):
    item = state["item"]
    if item.get("kind") == "feature" and item.get("app"):
        package_app(item["app"])
        commit_all("%s: package" % item["app"])
    git("push", "-q", "origin", item["branch"])
    reply = read_file(PR_BODY_FILE).strip()
    if reply:
        # The fix step answers the owner's questions here instead of guessing a change.
        path = os.path.join(LOOP_DIR, "pr-comment.md")
        # Posted with the owner's login, so it would read back as owner feedback
        # without the marker owner_feedback skips.
        write_file(path, loop_core.clean_pr_text(reply) + "\n\n" + loop_core.LOOP_MARKER + "\n")
        gh("pr", "comment", str(state["pr"]), "--body-file", path)
        os.remove(PR_BODY_FILE)
    state["phase"] = "await"


def phase_blocked(state, settings):
    """Wait for an owner answer or a new commit on main, then groom again."""
    git("fetch", "-q", "origin")
    if git("rev-parse", "origin/main") != state.get("main_sha") or any(collect_answers(
            state, since=state.get("blocked_since")).values()):
        state["phase"] = "groom"
        return
    sleep_unless_paused(settings["limits"]["poll_seconds"])


def phase_stuck(state, settings):
    """Resumed after being stuck: retry the phase that failed, with fresh counters."""
    state.update(phase=state.get("stuck_phase") or "groom", attempt=0, fix_attempts=0, step_errors=0)


PHASES = {
    "groom": phase_groom, "audit": phase_audit, "plan": phase_plan, "implement": phase_implement,
    "verify": phase_verify, "review": phase_review, "retro": phase_retro, "publish": phase_publish,
    "await": phase_await, "fix": phase_fix, "push": phase_push, "blocked": phase_blocked,
    "stuck": phase_stuck,
}


def _park(state, settings, out):
    """The step found a question only the owner can answer: park the item, work on another."""
    item = state["item"]
    commit_all("WIP %s (waiting on the owner)" % item["title"])
    git("push", "-q", "-u", "origin", item["branch"])
    state.setdefault("parked", {})[item["key"]] = {
        "item": item, "branch": item["branch"], "since": utc_now(),
        "issue_title": loop_core.issue_title_for(item["section"], item["title"])}
    created = sync_question_issues(state, roadmap_items(), settings)
    notify(state, "Parked %s: %s %s" % (item["title"], out.get("summary", "")[:120], " ".join(created)), settings)
    git("checkout", "-q", "main")
    state.update(phase="groom", item=None)


def _step_failed(state, settings, kind, out):
    """Rate limits wait and retry the same phase forever; other errors a few times."""
    if kind == "rate_limit":
        state["rate_attempt"] = state.get("rate_attempt", 0) + 1
        wait = loop_core.backoff_seconds(state["rate_attempt"] - 1)
        if state["rate_attempt"] == settings["limits"].get("notify_rate_limit_after", 3):
            notify(state, "Usage limit reached; retrying every %d min until it resets." % (wait // 60), settings)
        log.warning("Usage limit; retrying %s in %d min", state["phase"], wait // 60)
        save_state(state)
        sleep_unless_paused(wait)
        return
    state["step_errors"] = state.get("step_errors", 0) + 1
    detail = out.get("summary") if out else ""
    if state["step_errors"] > settings["limits"].get("max_step_errors", 2) or (out or {}).get("status") == "failed":
        raise LoopError("Step %s failed: %s" % (state["phase"], detail or kind))
    log.warning("Step %s errored (%d); retrying", state["phase"], state["step_errors"])


# ----------------------------------------------------------- pause / control

def paused():
    return os.path.exists(PAUSE_FILE)


def pause(reason="paused by the owner"):
    write_file(PAUSE_FILE, "%s %s\n" % (utc_now(), reason))


def resume():
    if os.path.exists(PAUSE_FILE):
        os.remove(PAUSE_FILE)


def sleep_unless_paused(seconds):
    """Sleep in short slices so pause and Ctrl+C take effect quickly."""
    end = time.time() + seconds
    while time.time() < end and not paused():
        time.sleep(min(15, max(0, end - time.time())))


def run_loop(settings, once=False):
    """The supervisor. Returns when paused (with --once: after one phase)."""
    with SingleInstance():
        state = load_state()
        while True:
            if paused():
                log.info("Paused (%s). `splk loop resume` to continue.", read_file(PAUSE_FILE).strip())
                return 0
            phase = state.get("phase", "groom")
            try:
                PHASES[phase](state, settings)
                if state.get("phase") != phase:
                    state["rate_attempt"] = 0
                    state["step_errors"] = 0
            except LoopError as exc:
                state.update(stuck_phase=phase, phase="stuck", stuck_reason=str(exc))
                save_state(state)
                pause("stuck: %s" % exc)
                notify(state, "Loop stuck in %s: %s" % (phase, str(exc)[:150]), settings)
                return 1
            save_state(state)
            if once:
                return 0


def status():
    state = load_state()
    return {"phase": state.get("phase"), "paused": paused(), "pause_reason": read_file(PAUSE_FILE).strip(),
            "item": (state.get("item") or {}).get("title"), "branch": (state.get("item") or {}).get("branch"),
            "pr": state.get("pr_url"), "attempt": state.get("attempt", 0),
            "parked": sorted((state.get("parked") or {}).keys()), "stuck_reason": state.get("stuck_reason"),
            "updated": state.get("updated")}
