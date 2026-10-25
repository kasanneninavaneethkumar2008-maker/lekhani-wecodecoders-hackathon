"""Versioned, untrusted JSON review-pack validation for guest export/import."""
import hashlib
import re
from datetime import datetime, timezone

from .checker import RULE_KINDS, Rule, load_rules

PACK_FORMAT_VERSION = 1
MAX_PACK_BYTES = 1_000_000
MAX_FINDINGS = 2_000


class ReviewPackError(ValueError):
    pass


def content_fingerprint(text: str) -> dict:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return {"algorithm": "SHA-256", "subject": "UTF-8 draft text", "value": digest}


def rule_snapshot(rule: Rule) -> dict:
    matching = {"type": "regex", "source": rule.pattern} if rule.kind == "claim" else {
        "type": "literal", "value": rule.pattern
    }
    return {
        "rule_id": rule.rule_id,
        "kind": rule.kind,
        "pattern": rule.pattern,
        "matching_config": matching,
        "replacement": rule.replacement,
        "applies_to": rule.applies_to,
        "message": rule.message,
        "clause_text": rule.clause_text,
        "active": rule.active,
        "rule_set_id": rule.rule_set_id,
        "rule_set_version": rule.rule_set_version,
    }


def rule_set_identity(rules):
    """The single (id, version) shared by the rules being exported."""
    pairs = {(rule.rule_set_id, rule.rule_set_version) for rule in rules}
    if len(pairs) != 1:
        raise ReviewPackError(
            "A review pack can only carry rules from a single rule-set version."
        )
    return next(iter(pairs))


def sorted_rule_snapshots(rules):
    """Deterministic snapshot order, used for export and exact comparison."""
    return sorted((rule_snapshot(rule) for rule in rules),
                  key=lambda item: item["rule_id"])


def make_review_pack(*, draft_text, content_type, audience, rules, findings,
                     guest_review_notes="", title="", check=None,
                     guest_review=None, findings_status=None) -> dict:
    set_id, set_version = rule_set_identity(rules)
    return {
        "format_version": PACK_FORMAT_VERSION,
        "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "title": title,
        "draft_text": draft_text,
        "content_type": content_type,
        "audience": audience,
        "rule_set": {"id": set_id, "version": set_version},
        "rules": sorted_rule_snapshots(rules),
        "findings": findings,
        "findings_status": findings_status or "historical; rerun checks after import",
        "check": check,
        "guest_review_notes": guest_review_notes,
        "guest_review": guest_review,
        "guest_status": {
            "identity_verified": False,
            "label": "Guest work — identity not verified",
            "note": ("This pack may contain a guest-review demonstration. It is not an "
                     "authorised organisational approval, a verified reviewer decision, "
                     "or proof of legal compliance."),
        },
        "limits": {
            "does_not_determine": [
                "Whether every factual claim is true.",
                "Legal compliance.",
                "Visual brand consistency.",
                "Full accessibility.",
                "Tone beyond the implemented rules.",
            ],
            "note": "A content fingerprint detects change; it is not a signature "
                    "and does not prove who created or reviewed this file.",
        },
        "content_fingerprint": content_fingerprint(draft_text),
    }


def _text(value, key, maximum, allow_empty=False):
    if not isinstance(value, str) or len(value) > maximum or (not allow_empty and not value.strip()):
        raise ReviewPackError(f"{key} must be text of at most {maximum:,} characters.")
    return value


def _validate_rule_snapshot(value, index):
    label = f"rules[{index}]"
    if not isinstance(value, dict):
        raise ReviewPackError(f"{label} must be an object.")
    required = ("rule_id", "kind", "pattern", "matching_config", "replacement",
                "applies_to", "message", "clause_text", "active",
                "rule_set_id", "rule_set_version")
    if any(key not in value for key in required):
        raise ReviewPackError(f"{label} is missing required fields.")
    rule_id = _text(value["rule_id"], f"{label}.rule_id", 100)
    kind = value["kind"]
    if kind not in RULE_KINDS:
        raise ReviewPackError(f"{label}.kind is unsupported.")
    pattern = _text(value["pattern"], f"{label}.pattern", 500)
    config = value["matching_config"]
    expected_type = "regex" if kind == "claim" else "literal"
    if not isinstance(config, dict) or config.get("type") != expected_type:
        raise ReviewPackError(f"{label}.matching_config is unsupported.")
    expected_value_key = "source" if kind == "claim" else "value"
    if config.get(expected_value_key) != pattern or len(config) != 2:
        raise ReviewPackError(f"{label}.matching_config does not match its pattern.")
    if kind == "claim":
        try:
            re.compile(pattern, re.IGNORECASE)
        except re.error as exc:
            raise ReviewPackError(f"{label} has an invalid claim pattern.") from exc
    replacement = value["replacement"]
    if replacement is not None:
        _text(replacement, f"{label}.replacement", 500, allow_empty=True)
    if not isinstance(value["active"], bool):
        raise ReviewPackError(f"{label}.active must be boolean.")
    clean = {
        "rule_id": rule_id,
        "kind": kind,
        "pattern": pattern,
        "matching_config": {"type": expected_type, expected_value_key: pattern},
        "replacement": replacement,
        "applies_to": _text(value["applies_to"], f"{label}.applies_to", 100),
        "message": _text(value["message"], f"{label}.message", 1000),
        "clause_text": _text(value["clause_text"], f"{label}.clause_text", 3000),
        "active": value["active"],
        "rule_set_id": _text(value["rule_set_id"], f"{label}.rule_set_id", 100),
        "rule_set_version": _text(value["rule_set_version"], f"{label}.rule_set_version", 100),
    }
    return clean


def _validate_check_snapshot(value):
    """Validate the optional check metadata without trusting its conclusions."""
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ReviewPackError("check must be an object when supplied.")
    clean = {}
    for key, maximum in (("status", 60), ("source", 60), ("checked_at", 40),
                         ("note", 500)):
        item = value.get(key, "")
        if not isinstance(item, str) or len(item) > maximum:
            raise ReviewPackError(f"check.{key} must be text of at most {maximum} characters.")
        clean[key] = item
    for key in ("content_type", "audience"):
        item = value.get(key, "")
        if not isinstance(item, str) or len(item) > 300:
            raise ReviewPackError(f"check.{key} is malformed.")
        clean[key] = item
    fingerprint = value.get("fingerprint")
    if fingerprint is not None and (
            not isinstance(fingerprint, str)
            or not re.fullmatch(r"[a-f0-9]{64}", fingerprint)):
        raise ReviewPackError("check.fingerprint is malformed.")
    clean["fingerprint"] = fingerprint
    if "complete" in value and not isinstance(value["complete"], bool):
        raise ReviewPackError("check.complete must be boolean.")
    clean["complete"] = bool(value.get("complete"))
    for key in ("finding_count", "rejected_count"):
        item = value.get(key, 0)
        if not isinstance(item, int) or isinstance(item, bool) or not 0 <= item <= 100_000:
            raise ReviewPackError(f"check.{key} must be a whole number.")
        clean[key] = item
    return clean


def validate_review_pack(payload, db):
    """Validate imported data and report whether its snapshot is locally known.

    Imported snapshots are never activated. Imported approval labels and
    findings are never trusted as current: only an exact match to the local
    recognized rule set can trigger a fresh check using local rules.
    """
    if not isinstance(payload, dict):
        raise ReviewPackError("The review pack must be a JSON object.")
    if payload.get("format_version") != PACK_FORMAT_VERSION:
        raise ReviewPackError("This review-pack format version is not supported.")
    title = payload.get("title", "")
    if not isinstance(title, str) or len(title) > 200:
        raise ReviewPackError("title must be text of at most 200 characters.")
    draft_text = _text(payload.get("draft_text"), "draft_text", 100_000, allow_empty=True)
    content_type = _text(payload.get("content_type"), "content_type", 100)
    audience = _text(payload.get("audience"), "audience", 300)
    notes = _text(payload.get("guest_review_notes", ""), "guest_review_notes", 5_000, allow_empty=True)
    rule_set = payload.get("rule_set")
    if not isinstance(rule_set, dict):
        raise ReviewPackError("rule_set must identify the exported rule set.")
    pack_id = _text(rule_set.get("id"), "rule_set.id", 100)
    pack_version = _text(rule_set.get("version"), "rule_set.version", 100)
    raw_rules = payload.get("rules")
    if not isinstance(raw_rules, list) or len(raw_rules) > 500:
        raise ReviewPackError("rules must be a list containing at most 500 entries.")
    snapshots = [_validate_rule_snapshot(rule, i) for i, rule in enumerate(raw_rules)]
    ids = [rule["rule_id"] for rule in snapshots]
    if len(ids) != len(set(ids)):
        raise ReviewPackError("Duplicate rule identifiers are not allowed.")
    findings = payload.get("findings")
    if not isinstance(findings, list) or len(findings) > MAX_FINDINGS:
        raise ReviewPackError(f"findings must be a list containing at most {MAX_FINDINGS:,} entries.")
    clean_findings = []
    for i, item in enumerate(findings):
        if not isinstance(item, dict):
            raise ReviewPackError(f"findings[{i}] must be an object.")
        if not all(isinstance(item.get(key), str) for key in ("rule_id", "kind", "message", "quote")):
            raise ReviewPackError(f"findings[{i}] is missing text fields.")
        if len(item["message"]) > 2000 or len(item["quote"]) > 3000:
            raise ReviewPackError(f"findings[{i}] contains oversized text.")
        clean_findings.append({key: item.get(key) for key in (
            "rule_id", "kind", "message", "quote", "excerpt", "is_prompt",
            "start_offset", "end_offset", "rule_set_id", "rule_set_version")})
    check = _validate_check_snapshot(payload.get("check"))
    # A carried guest review is evidence of what the file says, never of an
    # authorised decision. It is validated loosely and never applied.
    imported_review = payload.get("guest_review")
    imported_review_present = imported_review is not None
    if imported_review is not None:
        if not isinstance(imported_review, dict):
            raise ReviewPackError("guest_review must be an object when supplied.")
        for key in ("outcome", "recorded_at"):
            item = imported_review.get(key, "")
            if not isinstance(item, str) or len(item) > 200:
                raise ReviewPackError(f"guest_review.{key} is malformed.")
        note = imported_review.get("note", "")
        if not isinstance(note, str) or len(note) > 5_000:
            raise ReviewPackError("guest_review.note is malformed.")
    fingerprint = payload.get("content_fingerprint")
    if fingerprint is not None:
        if (not isinstance(fingerprint, dict)
                or fingerprint.get("algorithm") != "SHA-256"
                or fingerprint.get("subject") != "UTF-8 draft text"
                or not isinstance(fingerprint.get("value"), str)
                or not re.fullmatch(r"[a-f0-9]{64}", fingerprint["value"])):
            raise ReviewPackError("content_fingerprint is malformed.")
    # Locally recognised sets: the workspace's own rules and the bundled
    # GreenLeaf sample. Imported rules are still never activated as approved
    # or organisation rules; a match only lets us re-check with local rules.
    from .rulesets import sample_rules

    candidates = {
        "workspace": load_rules(db),
        "sample": sample_rules(),
    }
    known_mode = None
    current_rules = []
    for mode, local_rules in candidates.items():
        try:
            local_id, local_version = rule_set_identity(local_rules)
        except ReviewPackError:
            continue
        if (pack_id == local_id and pack_version == local_version
                and snapshots == sorted_rule_snapshots(local_rules)):
            known_mode = mode
            current_rules = local_rules
            break
    known = known_mode is not None
    supplied_fingerprint = fingerprint.get("value") if fingerprint else None
    fingerprint_matches = (supplied_fingerprint == content_fingerprint(draft_text)["value"]
                           if supplied_fingerprint else None)
    return {
        "title": title,
        "draft_text": draft_text,
        "content_type": content_type,
        "audience": audience,
        "guest_review_notes": notes,
        "findings": clean_findings,
        "check": check,
        "imported_review_present": imported_review_present,
        "known_rule_set": known,
        "rule_mode": known_mode or "workspace",
        "fingerprint_matches": fingerprint_matches,
        "current_rules": current_rules if known else [],
        "rule_set": {"id": pack_id, "version": pack_version},
    }
