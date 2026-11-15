"""Pure logic for `splk loop`: the roadmap, step results, PR verdicts.

Nothing here runs a process, reads the clock or touches the network, so all
of it is unit-tested. The supervisor in ``splk.loop`` does the side effects.

The roadmap (ROADMAP.md) is the loop's work queue. Its format:

    ## <app id>                 one section per app; "## Tooling" for repo work
    ### Done                    table of shipped versions; never an item
    ### 1. Title                an item; the number is optional
    Status: ready               ready | in-progress | blocked | proposed | done
    - [ ] question              open: the item cannot start
    - [x] question: answer      answered

An item is actionable only when its status is ready or in-progress AND it has
no open question, whatever the status line says: the loop never guesses.
"""

import datetime
import re

from splk.logs import get_logger

log = get_logger("loop_core")

STATUSES = ("ready", "in-progress", "blocked", "proposed", "done")

_APP_HEADING = re.compile(r"^##\s+(?!#)(.+?)\s*$")
_ITEM_HEADING = re.compile(r"^###\s+(?!#)(.+?)\s*$")
_STATUS = re.compile(r"^Status:\s*([a-z-]+)\s*$", re.IGNORECASE)
_OPEN_Q = re.compile(r"^\s*[-*]\s+\[ \]\s+(.+?)\s*$")
_DONE_Q = re.compile(r"^\s*[-*]\s+\[[xX]\]\s+(.+?)\s*$")
_NUMBER = re.compile(r"^\d+\.\s*")
# An indented, non-blank line that is not itself a list entry continues the
# question above it.
_CONTINUATION = re.compile(r"^\s+(?![-*]\s)\S")


class Item(object):
    """One roadmap item, as parsed. ``text`` is its whole section, heading included."""

    def __init__(self, section, title, status, open_questions, answered, text, line):
        self.section = section
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
    for line in raw["lines"][1:]:
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
                "\n".join(raw["lines"]).strip() + "\n", raw["line"])


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


def issue_body(item):
    """ASCII body listing the open questions; answers go in comments."""
    lines = ["The roadmap loop is waiting on these before it can start this item.",
             "Answer in a comment; the next groom step records the answers in ROADMAP.md.", "",
             "Item: %s / %s" % (item.section, item.title), ""]
    lines.extend("- [ ] %s" % q for q in item.open_questions)
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
