"""Rule Change Simulator: compare two bundled rule sets with the shared checker.

Everything here is a pure function over supplied rule sets. It never reads or
writes the database, never touches the active rules, and never modifies the
workspace draft. Differences are computed from actual checker output and
matched by rule ID plus finding location, not by totals.
"""
from dataclasses import asdict

from .checker import check_review

EXAMPLE_TEXT = (
    "Our best team will disrupt the market with guaranteed results and a "
    "risk-free trial. Synergy matters."
)

RULE_CHANGE_FIELDS = {
    "pattern": "Matching configuration changed",
    "clause_text": "Approved clause text changed",
    "applies_to": "Applicable content types changed",
    "replacement": "Preferred wording changed",
    "message": "Explanation changed",
    "kind": "Rule category changed",
    "active": "Rule active state changed",
}


def _finding_key(finding):
    return (finding.rule_id, finding.kind, finding.start_offset, finding.end_offset)


def _finding_dict(finding):
    data = asdict(finding)
    data["category"] = finding.category
    return data


def _rule_dict(rule):
    return {
        "rule_id": rule.rule_id,
        "kind": rule.kind,
        "pattern": rule.pattern,
        "replacement": rule.replacement,
        "applies_to": rule.applies_to,
        "message": rule.message,
        "clause_text": rule.clause_text,
        "active": rule.active,
    }


def _rule_changes(v1_rules, v2_rules):
    old = {rule.rule_id: rule for rule in v1_rules}
    new = {rule.rule_id: rule for rule in v2_rules}
    changes = []
    for rule_id in sorted(set(old) | set(new)):
        before, after = old.get(rule_id), new.get(rule_id)
        if before is None:
            changes.append({
                "rule_id": rule_id,
                "kind": "added",
                "labels": ["Rule added in v2"],
                "old": None,
                "new": _rule_dict(after),
            })
            continue
        if after is None:
            changes.append({
                "rule_id": rule_id,
                "kind": "removed",
                "labels": ["Rule removed in v2"],
                "old": _rule_dict(before),
                "new": None,
            })
            continue
        labels = [
            label for field, label in RULE_CHANGE_FIELDS.items()
            if getattr(before, field) != getattr(after, field)
        ]
        if labels:
            changes.append({
                "rule_id": rule_id,
                "kind": "changed",
                "labels": labels,
                "old": _rule_dict(before),
                "new": _rule_dict(after),
            })
    return changes


def compare_rule_sets(text, v1_rules, v2_rules, content_type="any"):
    """Run both rule sets on the same text and describe the differences."""
    run1 = check_review(text, content_type, v1_rules)
    run2 = check_review(text, content_type, v2_rules)
    changes = _rule_changes(v1_rules, v2_rules)
    change_map = {change["rule_id"]: change["labels"] for change in changes}

    findings1 = list(run1.issues)
    findings2 = list(run2.issues)
    used1 = set()
    used2 = set()

    unchanged, changed, new, resolved = [], [], [], []

    # Exact matches by rule ID + location: unchanged or details changed.
    map1 = {_finding_key(f): f for f in findings1}
    for finding in findings2:
        key = _finding_key(finding)
        before = map1.get(key)
        if before is None:
            continue
        used1.add(key)
        used2.add(key)
        details = ("message", "quote", "excerpt", "is_prompt")
        differs = any(getattr(before, field) != getattr(finding, field) for field in details)
        entry = {
            "rule_id": finding.rule_id,
            "old": _finding_dict(before),
            "new": _finding_dict(finding),
            "labels": change_map.get(finding.rule_id, []),
        }
        if differs:
            changed.append(entry)
        else:
            unchanged.append(entry)

    # Same rule ID but a different location: treat the first pair as a
    # "details changed" finding, so pattern edits are explained rather than
    # reported as unrelated new/resolved findings.
    remaining1 = [f for f in findings1 if _finding_key(f) not in used1]
    remaining2 = [f for f in findings2 if _finding_key(f) not in used2]
    for finding in list(remaining2):
        for before in remaining1:
            if before.rule_id == finding.rule_id and before.kind == finding.kind:
                if _finding_key(before) not in used1:
                    used1.add(_finding_key(before))
                    remaining1.remove(before)
                    used2.add(_finding_key(finding))
                    remaining2.remove(finding)
                    changed.append({
                        "rule_id": finding.rule_id,
                        "old": _finding_dict(before),
                        "new": _finding_dict(finding),
                        "labels": change_map.get(finding.rule_id, []),
                    })
                break

    for finding in remaining2:
        new.append({
            "rule_id": finding.rule_id,
            "finding": _finding_dict(finding),
            "labels": change_map.get(finding.rule_id, []),
        })
    for finding in remaining1:
        resolved.append({
            "rule_id": finding.rule_id,
            "finding": _finding_dict(finding),
            "labels": change_map.get(finding.rule_id, []),
        })

    unmapped = []
    for finding in new + resolved + changed:
        if not finding.get("labels"):
            unmapped.append(
                f"Rule {finding['rule_id']}: the difference could not be reliably "
                "mapped to a rule change."
            )

    return {
        "text": text,
        "rules_changed": changes,
        "new": new,
        "resolved": resolved,
        "unchanged": unchanged,
        "changed": changed,
        "unmapped_notes": unmapped,
        "v1_status": {
            "complete": run1.complete,
            "rejected": len(run1.rejected),
            "rule_set_id": run1.rule_set_id,
            "version": run1.rule_set_version,
        },
        "v2_status": {
            "complete": run2.complete,
            "rejected": len(run2.rejected),
            "rule_set_id": run2.rule_set_id,
            "version": run2.rule_set_version,
        },
    }
