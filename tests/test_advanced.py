"""Tests for the shared validator, workspace, review packs, and Trust Lab."""
import io
import json
import re
from pathlib import Path

import pytest

from inkloom.checker import (
    Issue,
    check_review,
    validate_citations,
)
from inkloom.review_pack import MAX_PACK_BYTES
from inkloom.rulesets import (
    LAB_RULE_SET_ID,
    LAB_V1,
    LAB_V2,
    demo_rules,
    lab_rules_v1,
    lab_rules_v2,
)
from inkloom.simulator import EXAMPLE_TEXT, compare_rule_sets

ROOT = Path(__file__).resolve().parents[1]

DRAFT = "Our guaranteed results will disrupt the market."


def enter_guest(client, name="Asha Rao"):
    client.post("/guest/login", data={"name": name})


def flat(page):
    """Collapse template whitespace so wrapped sentences compare reliably."""
    return re.sub(rb"\s+", b" ", page)


def lab_issue(rule_id, quote, version=LAB_V1):
    return Issue(
        rule_id=rule_id,
        kind="forbidden",
        message="Candidate finding.",
        quote=quote,
        excerpt="guaranteed results",
        is_prompt=False,
        rule_set_id=LAB_RULE_SET_ID,
        rule_set_version=version,
    )


def export_pack(client, **overrides):
    data = {
        "title": "Campaign draft",
        "body": DRAFT,
        "content_type": "website copy",
        "audience": "prospective customers",
        "notes": "Guest note about this draft.",
    }
    data.update(overrides)
    response = client.post("/workspace/export", data=data)
    assert response.status_code == 200
    assert response.mimetype == "application/json"
    assert "attachment" in response.headers["Content-Disposition"]
    return json.loads(response.data)


def import_pack(client, payload):
    raw = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
    return client.post(
        "/workspace/import",
        data={"pack": (io.BytesIO(raw), "review-pack.json")},
        content_type="multipart/form-data",
    )


# --- citation validation ------------------------------------------------------


def test_valid_lab_citation_is_accepted():
    rules = lab_rules_v1()
    clause = {rule.rule_id: rule.clause_text for rule in rules}["LAB-MSG-101"]
    result = validate_citations([lab_issue("LAB-MSG-101", clause)], rules)
    assert len(result.kept) == 1
    assert not result.discarded


def test_unknown_rule_id_is_rejected():
    clause = {r.rule_id: r.clause_text for r in lab_rules_v1()}["LAB-MSG-101"]
    result = validate_citations([lab_issue("LAB-UNKNOWN-999", clause)], lab_rules_v1())
    assert not result.kept
    assert result.discarded
    assert "Unknown rule identifier." in result.rejection_reasons


def test_altered_quotation_is_rejected():
    altered = "Lab forbidden message LAB-MSG-101: Avoid using guaranteed results."
    result = validate_citations([lab_issue("LAB-MSG-101", altered)], lab_rules_v1())
    assert not result.kept
    assert "Quoted clause does not exactly match the stored rule." in result.rejection_reasons


def test_wrong_rule_set_version_is_rejected():
    clause = {r.rule_id: r.clause_text for r in lab_rules_v1()}["LAB-MSG-101"]
    result = validate_citations([lab_issue("LAB-MSG-101", clause, version=LAB_V2)],
                                lab_rules_v1())
    assert not result.kept
    assert "Rule-set identifier or version does not match." in result.rejection_reasons


def test_invalid_candidates_do_not_produce_an_all_clear(monkeypatch, db):
    bad = Issue(
        rule_id="MSG-101",
        kind="forbidden",
        message="Candidate with a fabricated clause.",
        quote="This is not the stored clause.",
        excerpt="guaranteed results",
        is_prompt=False,
    )
    monkeypatch.setattr("inkloom.checker.run_checks",
                        lambda text, content_type, rules: [bad])
    run = check_review("A clean-looking draft.", "product page", demo_rules(db))
    assert run.issues == ()
    assert not run.complete
    assert run.rejected
    assert run.warnings


# --- workspace ----------------------------------------------------------------


def test_workspace_check_returns_findings_quotes_and_coverage(client):
    enter_guest(client)
    response = client.post("/workspace", data={
        "title": "Launch copy",
        "body": DRAFT,
        "content_type": "website copy",
        "audience": "prospective customers",
        "notes": "",
    })
    page = response.data
    assert b"MSG-101" in page
    assert b"Forbidden message MSG-101:" in page
    assert b"Required phrase not found" in page
    assert b"Check coverage" in page
    assert b"terminology" in page and b"messaging" in page and b"claim-trigger" in page
    assert b"lekhani-fictional-demo" in page
    assert b"Not determined by this check" in page
    assert b"Whether every factual claim is true." in page
    assert b"Legal compliance." in page
    assert b"Visual brand consistency." in page
    assert b"Full accessibility." in page
    assert b"Tone beyond the implemented rules." in page


def test_workspace_zero_findings_message(client):
    enter_guest(client)
    response = client.post("/workspace", data={
        "title": "Clean copy",
        "body": ("We improve the product. Pricing may change before purchase. "
                 "You can cancel at any time."),
        "content_type": "website copy",
        "audience": "prospective customers",
    })
    assert b"No issues detected by the configured checks." in response.data
    assert b"This does not establish factual correctness or legal compliance." in response.data


def test_workspace_requires_a_guest(client):
    response = client.get("/workspace")
    assert response.status_code == 302


def test_editing_marks_results_outdated_in_the_page_script():
    script = (ROOT / "inkloom/static/lek.js").read_text(encoding="utf-8")
    assert "data-editor-stale" in script
    assert "markStale" in script
    assert "These results are outdated" in (
        ROOT / "inkloom/templates/workspace.html").read_text(encoding="utf-8")


def test_flow_animation_pins_selection_and_never_moves_focus():
    script = (ROOT / "inkloom/static/lek.js").read_text(encoding="utf-8")
    flow = script.split("About flowchart")[1].split("workspace: stale")[0]
    assert "pinned = true" in flow
    assert ".focus(" not in flow
    assert "document.hidden" in flow
    assert "prefersReducedMotion()" in flow


def test_reduced_motion_disables_continuous_movement():
    script = (ROOT / "inkloom/static/lek.js").read_text(encoding="utf-8")
    styles = (ROOT / "inkloom/static/lek.css").read_text(encoding="utf-8")
    assert "reduce-motion" in script
    assert "html.reduce-motion" in styles
    assert "prefers-reduced-motion" in styles
    assert "animation: none" in styles


# --- review packs -------------------------------------------------------------


def test_export_pack_has_versioned_fields_and_no_secrets(client, db):
    enter_guest(client)
    pack = export_pack(client)
    assert pack["format_version"] == 1
    assert pack["draft_text"] == DRAFT
    assert pack["content_type"] == "website copy"
    assert pack["audience"] == "prospective customers"
    assert pack["rule_set"]["id"] == "lekhani-fictional-demo"
    assert pack["rules"] and pack["findings"]
    assert pack["content_fingerprint"]["algorithm"] == "SHA-256"
    assert pack["guest_review_notes"] == "Guest note about this draft."
    assert pack["findings_status"].startswith("current")
    text = json.dumps(pack).lower()
    for forbidden in ("password", "token", "cookie", "secret", "session"):
        assert forbidden not in text


def test_export_import_preserves_supported_draft_fields(client):
    enter_guest(client)
    pack = export_pack(client)
    response = import_pack(client, pack)
    page = response.data
    assert response.status_code == 200
    assert DRAFT.encode() in page
    assert b"prospective customers" in page
    assert b"Guest note about this draft." in page
    assert b"The draft matches the exported fingerprint." in page
    assert b"Current findings below come from a fresh check" in page


def test_changed_fingerprint_is_distinguished(client):
    enter_guest(client)
    pack = export_pack(client)
    pack["draft_text"] = DRAFT + " Edited after export."
    page = import_pack(client, pack).data
    assert b"The draft differs from the exported fingerprint." in page
    assert b"does not prove who created or reviewed this file" in page


def test_unsupported_pack_version_is_rejected(client):
    enter_guest(client)
    pack = export_pack(client)
    pack["format_version"] = 99
    response = import_pack(client, pack)
    assert b"This review-pack format version is not supported." in response.data
    assert b"Draft title" in response.data


def test_oversized_pack_is_rejected(client):
    enter_guest(client)
    response = import_pack(client, b"{" + b" " * MAX_PACK_BYTES + b"}")
    assert b"Review packs are limited to" in response.data


def test_malformed_pack_is_rejected(client):
    enter_guest(client)
    assert b"This file is not valid JSON." in import_pack(client, b"{not json").data
    assert b"must be a JSON object" in import_pack(client, [1, 2, 3]).data


def test_malformed_rule_snapshot_is_rejected(client):
    enter_guest(client)
    pack = export_pack(client)
    pack["rules"][0]["matching_config"] = {"type": "expression", "value": "1+1"}
    response = import_pack(client, pack)
    assert b"matching_config is unsupported." in response.data


def test_duplicate_rule_ids_are_rejected(client):
    enter_guest(client)
    pack = export_pack(client)
    pack["rules"].append(dict(pack["rules"][0]))
    assert b"Duplicate rule identifiers are not allowed." in import_pack(client, pack).data


def test_unknown_imported_rules_cannot_become_approved_rules(client, db):
    enter_guest(client)
    pack = export_pack(client)
    pack["rules"][0]["clause_text"] = "Imported, unapproved clause text."
    before = [dict(rule) for rule in db.execute("SELECT * FROM rules")]
    response = import_pack(client, pack)
    page = flat(response.data)
    assert b"original rules could not be verified" in page
    assert b"imported findings are historical and are not current results" in page
    assert b"Current findings below come from a fresh check" not in page
    after = [dict(rule) for rule in db.execute("SELECT * FROM rules")]
    assert before == after


def test_imported_markup_is_escaped(client):
    enter_guest(client)
    pack = export_pack(client)
    pack["draft_text"] = '<script>alert("x")</script> & guaranteed results'
    page = import_pack(client, pack).data
    assert b"<script>alert" not in page
    assert b"&lt;script&gt;" in page


# --- print --------------------------------------------------------------------


def test_print_summary_is_readable_and_honest(client):
    enter_guest(client, "Asha Rao")
    response = client.post("/workspace/print", data={
        "title": "Launch summary",
        "body": DRAFT,
        "content_type": "website copy",
        "audience": "prospective customers",
        "notes": "Please review the claims.",
    })
    page = response.data
    assert response.status_code == 200
    assert b"Launch summary" in page
    assert b"Guest demo summary" in page
    assert b"Guest identity is not verified" in page
    assert b"Forbidden message MSG-101:" in page
    assert b"Not determined by this check" in page
    assert b"not an authenticated approval" in page
    assert b"Please review the claims." in page


# --- Trust Lab ----------------------------------------------------------------


def test_trust_lab_page_is_labelled_and_separate(client):
    enter_guest(client)
    page = client.get("/trust-lab").data
    assert b"Try to break the evidence." in page
    assert b"Interactive demonstration" in page and b"Fictional rules" in page
    assert b"Validate finding" in page
    assert b"Simulation" in page and b"Not an official rule update" in page
    assert b'href="/trust-lab"' in client.get("/home").data


@pytest.mark.parametrize("case,expected", [
    ("valid", b"Accepted: the identifier, clause, and version match."),
    ("unknown", b"Rejected: this rule identifier does not exist in the selected rule set."),
    ("altered", b"Rejected: the quotation does not match the stored clause."),
])
def test_trust_lab_uses_the_real_validator(client, case, expected):
    enter_guest(client)
    page = flat(client.post("/trust-lab", data={"case": case}).data)
    assert expected in page
    assert b"A valid reference does not prove that a finding is contextually correct." in page


def test_trust_lab_rejects_unknown_case_without_crashing(client):
    enter_guest(client)
    page = client.post("/trust-lab", data={"case": "does-not-exist"}).data
    assert b"Accepted: the identifier, clause, and version match." in page


def test_simulator_reports_real_differences(client, db):
    before = [dict(rule) for rule in db.execute("SELECT * FROM rules")]
    result = compare_rule_sets(EXAMPLE_TEXT, lab_rules_v1(), lab_rules_v2())
    assert result["new"]
    assert result["resolved"]
    assert result["changed"]
    ids = {change["rule_id"] for change in result["rules_changed"]}
    assert {"LAB-GLS-001", "LAB-GLS-002", "LAB-MSG-101", "LAB-MSG-201"} <= ids
    assert any(item["rule_id"] == "LAB-MSG-201" for item in result["resolved"])

    enter_guest(client)
    page = client.post("/trust-lab/simulate", data={"load_example": "1"}).data
    assert b"What changes when the rules change?" in page
    assert b"Rules changed" in page
    assert b"LAB-GLS-002" in page
    assert b"Not an official rule update" in page
    after = [dict(rule) for rule in db.execute("SELECT * FROM rules")]
    assert before == after


def test_simulator_does_not_touch_the_workspace_draft(client):
    enter_guest(client)
    client.post("/trust-lab/simulate", data={"simulation_text": EXAMPLE_TEXT})
    page = client.get("/workspace").data
    # A fresh workspace stays empty; simulation text is never persisted.
    assert EXAMPLE_TEXT.encode() not in page
    assert b'<textarea id="draft-body"' in page


def test_simulator_requires_text(client):
    enter_guest(client)
    page = client.post("/trust-lab/simulate", data={"simulation_text": "  "}).data
    assert b"Enter simulation text or load the fictional example." in page
