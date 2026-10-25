"""Review-workspace state: snapshots, staleness, replacement, guest reviews.

Nothing here persists anything. The workspace carries the *metadata* of its
last check and guest review in hidden form fields; this module decides whether
that metadata still describes the draft in front of the reader. Draft text is
never written to a cookie, localStorage, IndexedDB, or the database.

Two rules matter for honesty:

* A check result is only ever produced by running the shared deterministic
  checker over the submitted text. A client-supplied "snapshot" is never used
  to restore findings, so an out-of-date or forged result cannot be presented
  as current.
* A guest review is a demonstration record, not an approval. It is shown only
  while its own snapshot still matches the draft, the content type, the
  audience, and the active rule set.
"""
import re
from datetime import datetime, timezone

from .checker import literal_pattern, rule_applies
from .review_pack import content_fingerprint

CONTENT_TYPES = ("social post", "marketing email", "website copy",
                 "product promotion", "other")
CONTENT_TYPE_LABELS = {
    "social post": "Social post",
    "marketing email": "Marketing email",
    "website copy": "Website copy",
    # Explicit mapping for the bundled GreenLeaf sample rules.
    "product promotion": "Product promotion",
    "other": "Other",
}

CATEGORY_OF_KIND = {
    "glossary": "terms",
    "required": "messages",
    "forbidden": "messages",
    "claim": "claims",
}
CATEGORY_LABELS = {
    "terms": "Terms",
    "messages": "Messages",
    "claims": "Claims",
}
CATEGORY_FILTERS = (
    ("all", "All"),
    ("terms", "Terms"),
    ("messages", "Messages"),
    ("claims", "Claims"),
)

REVIEW_OUTCOMES = {
    "changes": "Needs changes",
    "approved": "Mark approved — demo",
}
REVIEW_LABELS = {
    "changes": "Needs changes — demo",
    "approved": "Approved — demo",
}

MAX_TITLE_LENGTH = 200
MAX_AUDIENCE_LENGTH = 300
MAX_NOTE_LENGTH = 5_000

STATUS_LABELS = {
    "not-checked": "Not checked",
    "checking": "Checking",
    "checked": "Checked",
    "changes": "Changes since check",
    "incomplete": "Check incomplete",
    "failed": "Check failed",
}

FINGERPRINT_RE = re.compile(r"[a-f0-9]{64}")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalize_text(value) -> str:
    """Normalise line endings so client offsets and server fingerprints agree.

    Browsers submit textarea line breaks as CRLF; the reader's textarea and the
    check preview both use LF. Normalising once at the boundary keeps character
    offsets, fingerprints, and the visible draft on the same footing.
    """
    if not isinstance(value, str):
        return ""
    return value.replace("\r\n", "\n").replace("\r", "\n")


def fingerprint(text: str) -> str:
    """SHA-256 of the UTF-8 draft text (the algorithm already used by packs)."""
    return content_fingerprint(normalize_text(text))["value"]


def count_words(text: str) -> int:
    """Words are runs of non-whitespace characters. This is not NLP analysis."""
    return len(re.findall(r"\S+", normalize_text(text)))


def active_rule_set(rules):
    """The single (id, version) shared by the active rules, or None."""
    pairs = {
        (rule.rule_set_id, rule.rule_set_version)
        for rule in rules
        if rule.active
    }
    if len(pairs) == 1:
        return next(iter(pairs))
    return None


def make_snapshot(values, run, *, checked_at=None, source="check") -> dict:
    """Describe exactly what a completed check looked at."""
    return {
        "fingerprint": fingerprint(values["body"]),
        "content_type": values["content_type"],
        "audience": values["audience"],
        "rule_set_id": run.rule_set_id,
        "rule_set_version": run.rule_set_version,
        "checked_at": checked_at or now_iso(),
        "complete": bool(run.complete),
        "finding_count": len(run.issues),
        "rejected_count": len(run.rejected),
        "source": source,
    }


def snapshot_from_form(form):
    """Read the carried check snapshot, treating every value as untrusted."""
    raw_fingerprint = form.get("check_fingerprint", "")
    if not FINGERPRINT_RE.fullmatch(raw_fingerprint):
        return None

    def text(name, maximum):
        value = form.get(name, "")
        return value[:maximum] if isinstance(value, str) else ""

    def number(name):
        raw = form.get(name, "0")
        return int(raw) if isinstance(raw, str) and raw.isdigit() else 0

    checked_at = text("check_checked_at", 40)
    if not checked_at:
        return None
    return {
        "fingerprint": raw_fingerprint,
        "content_type": text("check_content_type", 100),
        "audience": text("check_audience", MAX_AUDIENCE_LENGTH),
        "rule_set_id": text("check_rule_set_id", 100),
        "rule_set_version": text("check_rule_set_version", 100),
        "checked_at": checked_at,
        "complete": form.get("check_complete") == "1",
        "finding_count": number("check_finding_count"),
        "rejected_count": number("check_rejected_count"),
        "source": text("check_source", 40) or "check",
    }


def snapshot_is_current(snapshot, values, rules) -> bool:
    """Whether this carried snapshot still describes the current workspace."""
    if not snapshot:
        return False
    if fingerprint(values["body"]) != snapshot["fingerprint"]:
        return False
    if values["content_type"] != snapshot["content_type"]:
        return False
    if values["audience"] != snapshot["audience"]:
        return False
    current = active_rule_set(rules)
    if current is None:
        return False
    return current == (snapshot["rule_set_id"], snapshot["rule_set_version"])


def status_for(snapshot, values, rules, *, failed=False) -> str:
    """One of the six honest workspace statuses."""
    if failed:
        return "failed"
    if not snapshot:
        return "not-checked"
    if not snapshot_is_current(snapshot, values, rules):
        return "changes"
    if not snapshot["complete"]:
        return "incomplete"
    return "checked"


def review_from_form(form):
    """Read a carried guest review; values are display data, never authority."""
    outcome = form.get("review_outcome", "")
    if outcome not in REVIEW_OUTCOMES:
        return None
    raw_fingerprint = form.get("review_fingerprint", "")
    if not FINGERPRINT_RE.fullmatch(raw_fingerprint):
        return None
    recorded_at = form.get("review_recorded_at", "")
    if not isinstance(recorded_at, str) or not recorded_at or len(recorded_at) > 40:
        return None
    note = form.get("review_note", "")
    if not isinstance(note, str) or len(note) > MAX_NOTE_LENGTH:
        return None
    return {
        "outcome": outcome,
        "note": note,
        "recorded_at": recorded_at,
        "guest_name": (form.get("review_guest_name") or "")[:60],
        "fingerprint": raw_fingerprint,
        "content_type": (form.get("review_content_type") or "")[:100],
        "audience": (form.get("review_audience") or "")[:MAX_AUDIENCE_LENGTH],
        "rule_set_id": (form.get("review_rule_set_id") or "")[:100],
        "rule_set_version": (form.get("review_rule_set_version") or "")[:100],
        "check_checked_at": (form.get("review_check_checked_at") or "")[:40],
    }


def review_is_current(review, snapshot, values, rules) -> bool:
    """A review only applies to the exact snapshot it was recorded against."""
    if not review or not snapshot:
        return False
    if not snapshot_is_current(snapshot, values, rules):
        return False
    # The review stays valid across a re-check of identical content, but not
    # across any change to the draft, its metadata, or the active rules. The
    # check-run reference recorded with the review is kept for the record.
    return (
        review["fingerprint"] == snapshot["fingerprint"]
        and review["content_type"] == snapshot["content_type"]
        and review["audience"] == snapshot["audience"]
        and review["rule_set_id"] == snapshot["rule_set_id"]
        and review["rule_set_version"] == snapshot["rule_set_version"]
    )


def make_review(values, outcome, note, guest_name=""):
    """Build a demonstration review record for the current snapshot."""
    return {
        "outcome": outcome,
        "note": note,
        "recorded_at": now_iso(),
        "guest_name": guest_name[:60],
        "fingerprint": fingerprint(values["body"]),
        "content_type": values["content_type"],
        "audience": values["audience"],
        "rule_set_id": None,
        "rule_set_version": None,
        "check_checked_at": None,
    }


def apply_controlled_replacement(text, rule, start, end, expected_fingerprint,
                                 content_type):
    """Replace exactly one validated occurrence of a terminology rule.

    Returns ``(new_text, error)`` where ``error`` is ``None`` on success, or a
    short machine-readable code: ``outdated`` (the text no longer matches the
    check snapshot), ``mismatch`` (the offsets do not identify the rule's
    phrase), or ``unsupported`` (the rule has no safe exact substitution).
    """
    if (rule is None or not rule.active or rule.kind != "glossary"
            or not rule.replacement):
        return None, "unsupported"
    if not rule_applies(rule, content_type):
        return None, "unsupported"
    text = normalize_text(text)
    if fingerprint(text) != expected_fingerprint:
        return None, "outdated"
    if not isinstance(start, int) or not isinstance(end, int):
        return None, "mismatch"
    if start < 0 or end > len(text) or start >= end:
        return None, "mismatch"
    span = text[start:end]
    try:
        exact = re.fullmatch(literal_pattern(rule.pattern), span, re.IGNORECASE)
    except re.error:
        return None, "mismatch"
    if exact is None:
        return None, "mismatch"
    return text[:start] + rule.replacement + text[end:], None


def finding_payload(issue, rules_by_id):
    """Data the page script needs for preview, replacement, and evidence."""
    rule = rules_by_id.get(issue.rule_id)
    occurrences = [
        {"start": start, "end": end}
        for start, end in issue.occurrences
        if 0 <= start < end
    ]
    return {
        "rule_id": issue.rule_id,
        "kind": issue.kind,
        "category": CATEGORY_OF_KIND.get(issue.kind, "messages"),
        "title": issue.title or issue.message,
        "replacement": rule.replacement if rule is not None else None,
        "occurrences": occurrences,
    }


def preview_segments(text, issues):
    """Split the checked text into plain and highlighted segments.

    Overlapping or repeated matches are merged so the preview always shows the
    original text exactly once, in order. Each highlighted segment carries the
    rule IDs whose validated matches cover it.
    """
    text = normalize_text(text)
    ranges = []
    for issue in issues:
        spans = issue.occurrences
        if not spans and issue.start_offset is not None and issue.end_offset is not None:
            spans = ((issue.start_offset, issue.end_offset),)
        for start, end in spans:
            if 0 <= start < end <= len(text):
                ranges.append((start, end, issue.rule_id))

    merged = []
    for start, end, rule_id in sorted(ranges):
        if merged and start <= merged[-1][1]:
            previous = merged[-1]
            previous_ids = previous[2]
            if rule_id not in previous_ids:
                previous_ids.append(rule_id)
            merged[-1] = (previous[0], max(previous[1], end), previous_ids)
        else:
            merged.append((start, end, [rule_id]))

    segments = []
    cursor = 0
    for start, end, rule_ids in merged:
        if start > cursor:
            segments.append({"text": text[cursor:start], "rule_ids": []})
        segments.append({"text": text[start:end], "rule_ids": sorted(rule_ids)})
        cursor = end
    if cursor < len(text):
        segments.append({"text": text[cursor:], "rule_ids": []})
    return segments


def rule_title(rule) -> str:
    if rule.kind == "glossary":
        if rule.replacement:
            return f'Terminology: use “{rule.replacement}” instead of “{rule.pattern}”'
        return f'Terminology: “{rule.pattern}”'
    if rule.kind == "required":
        return f'Required phrase: “{rule.pattern}”'
    if rule.kind == "forbidden":
        return f'Forbidden phrase: “{rule.pattern}”'
    return f'Claim trigger pattern: {rule.pattern}'


def rule_matching_description(rule) -> str:
    if rule.kind == "claim":
        return ("Regular-expression trigger, case-insensitive. A match prompts a "
                "human to check evidence; it is not a verdict.")
    return ("Literal phrase, case-insensitive, whole-word boundaries, and any run "
            "of whitespace between words.")


def scope_label(applies_to: str) -> str:
    """Human label for a comma-separated content-type scope."""
    if not applies_to or applies_to.strip().casefold() == "any":
        return "All content types"
    parts = [part.strip().capitalize() for part in applies_to.split(",") if part.strip()]
    return " · ".join(parts)


def rule_views(rules):
    """Presentation rows for the read-only rule list and drawer."""
    views = []
    for rule in rules:
        category = CATEGORY_OF_KIND.get(rule.kind, "messages")
        views.append({
            "rule": rule,
            "category": category,
            "category_label": CATEGORY_LABELS[category],
            "title": rule_title(rule),
            "matching": rule_matching_description(rule),
            "applies_to": rule.applies_to or "any",
            "applies_to_label": scope_label(rule.applies_to),
            "search_text": " ".join((
                rule.rule_id, rule.kind, rule.pattern, rule.message,
                rule.clause_text, rule.applies_to or "any",
            )).lower(),
        })
    return views
