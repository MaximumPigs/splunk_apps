"""Pure logic for `splk loop`: the roadmap, step results, PR verdicts.

Nothing here runs a process, reads the clock or touches the network, so all
of it is unit-tested. The supervisor in ``splk.loop`` does the side effects.

The roadmap (ROADMAP.md) is the loop's work queue. Its format:

    ## <app id>                 one section per app; "## Tooling" for repo work
    ### Done                    table of shipped versions; never an item
    ### 1. Title                an item; the number is optional
    Status: ready               ready | in-progress | blocked | proposed |
                                interactive | done
    - [ ] question              open: the item cannot start
    - [x] question: answer      answered

An item is actionable only when its status is ready or in-progress AND it has
no open question, whatever the status line says: the loop never guesses.
``interactive`` marks agreed work the loop may not do itself (it changes the
loop, hooks, prompts or settings, which steps are barred from editing): it
waits for the owner's interactive session instead of being picked and parked.
"""

import datetime
import re

from splk.logs import get_logger

log = get_logger("loop_core")

STATUSES = ("ready", "in-progress", "blocked", "proposed", "interactive", "done")

_APP_HEADING = re.compile(r"^##\s+(?!#)(.+?)\s*$")
_ITEM_HEADING = re.compile(r"^###\s+(?!#)(.+?)\s*$")
_STATUS = re.compile(r"^Status:\s*([a-z-]+)\s*$", re.IGNORECASE)
_OPEN_Q = re.compile(r"^\s*[-*]\s+\[ \]\s+(.+?)\s*$")
_DONE_Q = re.compile(r"^\s*[-*]\s+\[[xX]\]\s+(.+?)\s*$")
_NUMBER = re.compile(r"^\d+\.\s*")
_CONTEXT = re.compile(r"^Context:\s*(.*?)\s*$")
# An indented, non-blank line that is not itself a list entry continues the
# question above it.
_CONTINUATION = re.compile(r"^\s+(?![-*]\s)\S")


class Item(object):
    """One roadmap item, as parsed. ``text`` is its whole section, heading included."""

    def __init__(self, section, title, status, open_questions, answered, text, line, context=""):
        self.section = section
        # The item's "Context:" paragraph: a short summary for the owner,
        # shown above the questions in its GitHub issue.
        self.context = context
        self.title = title
        self.status = status
        self.open_questions = open_questions
        self.answered = answered
        self.text = text
        self.line = line

    @property
    def app(self):
        """The app id the item belongs to, or None for repo-wide work (## Tooling)."""
        name = self.section.strip()
        return None if name.lower() in ("tooling", "repo", "repository") else name

    @property
    def key(self):
        """Stable identity across edits: section and title without its number."""
        return "%s/%s" % (self.section, _NUMBER.sub("", self.title))

    @property
    def actionable(self):
        return self.status in ("ready", "in-progress") and not self.open_questions

    def __repr__(self):
        return "Item(%r, %r, %r, open=%d)" % (self.section, self.title, self.status, len(self.open_questions))


def parse_roadmap(text):
    """Every item in roadmap order. Unknown or missing status reads as blocked."""
    items, section, current = [], None, None

    def close():
        if current is not None:
            items.append(_finish(current))

    for number, line in enumerate(text.splitlines(), start=1):
        app = _APP_HEADING.match(line)
        if app:
            close()
            section, current = app.group(1), None
            continue
        heading = _ITEM_HEADING.match(line)
        if heading:
            close()
            title = heading.group(1)
            # "Done" holds the shipped-versions table; anything outside an app
            # section (the preamble) is not work either.
            current = None if (section is None or title.lower() == "done") else {
                "section": section, "title": title, "lines": [line], "line": number}
            continue
        if current is not None:
            current["lines"].append(line)
    close()
    return items


def _finish(raw):
    status, open_q, answered = None, [], []
    # The list the last question went into: groom wraps a question (options,
    # recommendation) over indented lines, and only reading the first line
    # sent the owner issues with half a question.
    last = None
    context, in_context = [], False
    for line in raw["lines"][1:]:
        if in_context:
            # The paragraph runs to the next blank line or list entry.
            if line.strip() and not _OPEN_Q.match(line) and not _DONE_Q.match(line):
                context.append(line.strip())
                continue
            in_context = False
        match = _CONTEXT.match(line)
        if match and not context:
            context, in_context, last = [match.group(1)], True, None
            continue
        match = _STATUS.match(line.strip())
        if match and status is None:
            status = match.group(1).lower()
            last = None
            continue
        match = _OPEN_Q.match(line)
        if match:
            open_q.append(match.group(1))
            last = open_q
            continue
        match = _DONE_Q.match(line)
        if match:
            answered.append(match.group(1))
            last = answered
            continue
        if last is not None and _CONTINUATION.match(line):
            last[-1] += " " + line.strip()
        else:
            last = None
    if status not in STATUSES:
        # A missing or misspelt status must not make an item look ready.
        log.warning("Roadmap item %r (line %d) has status %r; treating it as blocked",
                    raw["title"], raw["line"], status)
        status = "blocked"
    return Item(raw["section"], raw["title"], status, open_q, answered,
                "\n".join(raw["lines"]).strip() + "\n", raw["line"], " ".join(c for c in context if c))


def next_item(items):
    """The item to work on: a resumed in-progress one first, else the first ready one."""
    for wanted in ("in-progress", "ready"):
        for item in items:
            if item.status == wanted and item.actionable:
                return item
    return None


def awaiting_owner(items):
    """Items that cannot start until the owner answers something."""
    return [item for item in items if item.status != "done" and item.open_questions]


def awaiting_session(items):
    """Agreed items only the owner's interactive session can build."""
    return [item for item in items if item.status == "interactive" and not item.open_questions]


def should_audit(items):
    """Run the improvement audit only when nothing is ready and no earlier
    proposal is still waiting for the owner, so audits never pile up."""
    if next_item(items) is not None:
        return False
    return not any(item.status == "proposed" and item.open_questions for item in items)


def slug(text, limit=40):
    """Branch-safe slug: lower case ASCII, hyphens, no number prefix."""
    text = _NUMBER.sub("", text).lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return (text[:limit].rstrip("-")) or "item"


def branch_for(item):
    prefix = item.app or "repo"
    return "feature/%s-%s" % (slug(prefix, 20), slug(item.title))


def issue_title(item):
    return issue_title_for(item.section, item.title)


def issue_title_for(section, title):
    return "Roadmap question: %s / %s" % (section, _NUMBER.sub("", title))


# Owner's rule: no AI tool or model names and no attribution trailers in PR
# titles or descriptions. Models are told so; this enforces it.
_AI_LINE = re.compile(r"co-authored-by|generated with|\b(claude|anthropic|copilot|chatgpt|openai|"
                      r"gemini|codex|sonnet|opus|haiku|llm)\b", re.IGNORECASE)


def clean_pr_text(text):
    """Drop every line that names an AI tool or carries an attribution trailer."""
    kept = [line for line in text.splitlines() if not _AI_LINE.search(line)]
    return "\n".join(kept).strip()


def first_paragraph(item, limit=400):
    """The item's first paragraph of prose, cut at a sentence end within ``limit``.

    The fallback context for an item groom has not yet given a Context line.
    """
    paragraph = []
    for line in item.text.splitlines()[1:]:
        text = line.strip()
        if not text:
            if paragraph:
                break
            continue
        if _STATUS.match(text) or _CONTEXT.match(text) or text.startswith(("-", "*", "|", "#")):
            if paragraph:
                break
            continue
        paragraph.append(text)
    text = " ".join(paragraph)
    if len(text) <= limit:
        return text
    cut = text[:limit]
    end = max(cut.rfind(". "), cut.rfind(": "), cut.rfind("; "))
    return cut[:end + 1] if end > limit // 3 else cut.rsplit(" ", 1)[0] + " ..."


def issue_body(item):
    """ASCII body: a short context, then the open questions; answers go in comments.

    The owner reads these on GitHub, often on a phone, without ROADMAP.md
    open: the context says what the item is and why the questions matter,
    so a question can be answered from the issue alone.
    """
    context = item.context or first_paragraph(item)
    lines = ["The roadmap loop is waiting on these before it can start this item.",
             "Answer in a comment; the next groom step records the answers in ROADMAP.md.", "",
             "Item: %s / %s" % (item.section, item.title), ""]
    if context:
        lines += ["Context: %s" % context, ""]
    lines += ["Questions:", ""]
    lines.extend("- [ ] %s" % q for q in item.open_questions)
    lines += ["", "Full item: ROADMAP.md, line %d." % item.line]
    return "\n".join(lines) + "\n"


def findings_entry(section, title, pr_url, text):
    """One PR's left-over review findings, as groom reads them.

    The review step leaves findings for the owner in the PR body; this copy
    is what puts them in the roadmap, so they are not forgotten once merged.
    """
    text = (text or "").strip()
    if not text:
        return ""
    return "## %s / %s (%s)\n\n%s\n" % (section, title, pr_url or "no PR", text)


# ------------------------------------------------------------ loop log digest

_STEP_FILE = re.compile(r"^(\d{8}-\d{6})-([a-z_]+)\.json$")


def steps_since_last_groom(names):
    """Step record file names after the newest groom record, oldest first.

    Names sort by their local-time stamp. The groom about to run reviews
    what happened since the previous one; with no groom yet, everything.
    """
    records = sorted(n for n in names if _STEP_FILE.match(n))
    grooms = [i for i, n in enumerate(records) if _STEP_FILE.match(n).group(2) == "groom"]
    return records[grooms[-1] + 1:] if grooms else records


def loop_digest(records, notifications, limit=60):
    """Markdown summary of step records and supervisor notifications for groom.

    ``records`` are (file name, parsed record) pairs. Identical stderr is
    shown once: the same warning on every step would otherwise drown the rest.
    """
    if not records and not notifications:
        return "Nothing happened in the loop since the last groom.\n"
    lines = ["# Loop activity since the last groom", ""]
    skipped = max(0, len(records) - limit)
    if skipped:
        lines += ["(%d older step records not shown; read them in .agent/loop/steps/.)" % skipped, ""]
    seen_stderr = set()
    for name, rec in records[skipped:]:
        # A corrupt record must not stop every groom from running.
        rec = rec if isinstance(rec, dict) else {"detail": "step record is not an object"}
        out = rec.get("output") if isinstance(rec.get("output"), dict) else {}
        try:
            cost = float(rec.get("cost_usd") or 0)
        except (TypeError, ValueError):
            cost = 0.0
        lines.append("## %s: %s (%s), %s, exit %s, %ss, $%.2f" % (
            name, rec.get("step"), rec.get("model"), rec.get("kind"), rec.get("exit"),
            rec.get("seconds"), cost))
        if out:
            lines.append("Status %s: %s" % (out.get("status"), out.get("summary", "")))
        if rec.get("detail"):
            lines.append("Detail: %s" % str(rec["detail"])[:500])
        stderr = str(rec.get("stderr") or "").strip()
        if stderr:
            if stderr in seen_stderr:
                lines.append("Stderr: same as above.")
            else:
                seen_stderr.add(stderr)
                lines.append("Stderr: %s" % stderr[-500:])
        lines.append("")
    if notifications:
        lines += ["## Notifications to the owner", ""] + ["- %s" % n for n in notifications]
    return "\n".join(lines).rstrip() + "\n"


def trust_key(path):
    """The ~/.claude.json project key a headless CLI run looks up for ``path``.

    Observed on Windows (CLI 2.1.325): the working directory with forward
    slashes and the drive letter's case kept ("d:/GitHub/x" for d:\\GitHub\\x).
    The key an interactive session writes ("D:\\GitHub\\x") never matches it.
    """
    return path.replace("\\", "/")


def with_trust(config, key):
    """Mark ``key`` trusted in a parsed ~/.claude.json. True if it changed."""
    project = config.setdefault("projects", {}).setdefault(key, {})
    if project.get("hasTrustDialogAccepted") is True:
        return False
    project["hasTrustDialogAccepted"] = True
    return True


# --------------------------------------------------------------- step results

RATE_LIMIT_TEXT = re.compile(
    r"usage limit|rate limit|rate_limit|limit reached|too many requests|overloaded|"
    r"out of (extra )?usage|credit balance|quota", re.IGNORECASE)


def classify_result(exit_code, data, stderr=""):
    """Turn one `claude -p --output-format json` run into (kind, detail).

    kind is ok | rate_limit | error. Observed on a success: is_error false,
    subtype "success", api_error_status null, structured_output set. A usage
    limit has not been observed yet, so it is recognised by HTTP 429/529 or
    by its wording; anything else that fails is a plain error.
    """
    data = data or {}
    status = data.get("api_error_status")
    text = " ".join(str(part) for part in (data.get("result") or "", data.get("subtype") or "", stderr or ""))
    if status in (429, 529, "429", "529") or (
            (exit_code != 0 or data.get("is_error")) and RATE_LIMIT_TEXT.search(text)):
        return "rate_limit", text.strip()[:500]
    if exit_code != 0 or data.get("is_error") or data.get("subtype") not in (None, "success"):
        return "error", (text.strip() or "exit code %s" % exit_code)[:500]
    return "ok", ""


def backoff_seconds(attempt, base=300, cap=3600):
    """Wait before retrying a rate-limited step: 5, 10, 20, 40, then 60 min."""
    return min(cap, base * (2 ** max(0, attempt)))


# ---------------------------------------------------------------- PR verdicts

FAILED_CHECKS = ("FAILURE", "CANCELLED", "TIMED_OUT", "ERROR", "ACTION_REQUIRED", "STARTUP_FAILURE")
PENDING_CHECKS = ("PENDING", "QUEUED", "IN_PROGRESS", "EXPECTED", "WAITING", "REQUESTED")


def _parse_ts(value):
    if not value:
        return None
    try:
        return datetime.datetime.strptime(value[:19], "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        return None


# Appended to every comment the supervisor posts. It posts with the owner's
# login, so without this its own replies would read back as owner feedback.
LOOP_MARKER = "<!-- splk-loop -->"


def touches_app_code(paths):
    """True when any repo-relative path is under apps/: such a change needs a review."""
    return any(p.replace("\\", "/").startswith("apps/") for p in paths)


def valid_app(name, known_apps):
    """A roadmap section names an app only if it is a plain id of an existing app."""
    return bool(re.match(r"^[a-z0-9_]+$", name or "")) and name in known_apps


def owner_feedback(pr, owner, since):
    """The owner's comments and reviews on the PR newer than ``since`` (ISO UTC).

    Only the owner's words count: anyone else's comment is untrusted input
    and must never steer the loop.
    """
    cutoff = _parse_ts(since)
    found = []
    for entry in list(pr.get("comments") or []) + list(pr.get("reviews") or []):
        login = ((entry.get("author") or {}).get("login") or "")
        if login.lower() != (owner or "").lower():
            continue
        when = _parse_ts(entry.get("createdAt") or entry.get("submittedAt"))
        body = (entry.get("body") or "").strip()
        state = entry.get("state") or ""
        if not body and state != "CHANGES_REQUESTED":
            continue
        if LOOP_MARKER in body:
            continue
        if cutoff is not None and (when is None or when <= cutoff):
            continue
        found.append({"at": entry.get("createdAt") or entry.get("submittedAt"),
                      "state": state, "body": body})
    return found


def pr_verdict(pr, owner, feedback_since):
    """merged | closed | feedback | ci_failed | ci_pending | waiting.

    Feedback outranks CI: the owner's request may be the reason CI is red.
    """
    state = (pr.get("state") or "").upper()
    if state == "MERGED":
        return "merged"
    if state == "CLOSED":
        return "closed"
    if owner_feedback(pr, owner, feedback_since):
        return "feedback"
    checks = pr.get("statusCheckRollup") or []
    outcomes = [((c.get("conclusion") or c.get("state") or c.get("status") or "")).upper() for c in checks]
    if any(o in FAILED_CHECKS for o in outcomes):
        return "ci_failed"
    if not checks or any(o in PENDING_CHECKS or o == "" for o in outcomes):
        return "ci_pending"
    return "waiting"


def parse_porcelain_z(output):
    """Paths from `git status --porcelain -z`, in order.

    Each entry is "XY path" with a two-character status (the first may be a
    space, so the output must never be stripped). -z gives paths verbatim,
    without quoting, and a rename or copy is followed by its source path as a
    separate entry. The source is reported too, so a rename onto ROADMAP.md
    cannot hide the file it came from from the groom check.
    """
    entries = output.split("\0")
    paths, skip = [], False
    for entry in entries:
        if skip:
            skip = False
            if entry:
                paths.append(entry)
            continue
        if len(entry) < 4:
            continue
        status, path = entry[:2], entry[3:]
        paths.append(path)
        if "R" in status or "C" in status:
            skip = True
    return paths


def render_prompt(template, values):
    """Fill {{name}} placeholders; an unknown name is left visible, not blanked."""
    def sub(match):
        key = match.group(1)
        return str(values[key]) if key in values else match.group(0)
    return re.sub(r"\{\{\s*([a-z_]+)\s*\}\}", sub, template)
