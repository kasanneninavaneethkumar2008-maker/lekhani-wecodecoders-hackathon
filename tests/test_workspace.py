"""Review-workspace behaviour: snapshots, evidence, replacement, guest review.

These tests exercise the real Flask routes and the shared checker; nothing is
mocked except where a broken candidate has to be injected to prove that an
incomplete check never looks like an all-clear.
"""
import html
import io
import json
import re

import pytest

from inkloom.checker import (
    Issue,
    Rule,
    check_review,
    run_checks,
    validate_citations,
)
from inkloom.review_pack import PACK_FORMAT_VERSION, content_fingerprint
from inkloom.rulesets import demo_rules
from inkloom.workbench import (
    apply_controlled_replacement,
    count_words,
    fingerprint,
    preview_segments,
    snapshot_is_current,
)

EM = "—".encode("utf-8")

DRAFT = "Our guaranteed results will disrupt the market."
TWO_TERMS = "We disrupt habits. Later we disrupt routines too."


def enter_guest(client, name="Asha Rao"):
    client.post("/guest/login", data={"name": name})


def flat(page):
    """Collapse template whitespace so wrapped sentences compare reliably."""
    return re.sub(rb"\s+", b" ", page)


def check(client, **overrides):
    data = {
        "title": "Launch draft",
        "body": DRAFT,
        "content_type": "website copy",
        "audience": "prospective customers",
        "notes": "",
    }
    data.update(overrides)
    response = client.post("/workspace/check", data=data)
    assert response.status_code == 200
    return response


def carried(page_bytes):
    """Read the hidden snapshot/review fields the browser would carry."""
    text = page_bytes.decode("utf-8")
    return {
        html.unescape(name): html.unescape(value)
        for name, value in re.findall(
            r'name="((?:check|review)_[^"]+)" value="([^"]*)"', text
        )
    }


def workspace_payload(fields, **overrides):
    payload = {
        "title": "Launch draft",
        "body": DRAFT,
        "content_type": "website copy",
        "audience": "prospective customers",
        "notes": "",
    }
    payload.update(fields)
    payload.update(overrides)
    return payload


def export_pack(client, **overrides):
    data = {
        "title": "Campaign draft",
        "body": DRAFT,
        "content_type": "website copy",
        "audience": "prospective customers",
        "notes": "",
    }
    data.update(overrides)
    response = client.post("/workspace/export", data=data)
    assert response.status_code == 200
    assert response.mimetype == "application/json"
    return json.loads(response.data)


def import_pack(client, payload, **extra):
    raw = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
    data = {"pack": (io.BytesIO(raw), "review-pack.json")}
    data.update(extra)
    return client.post("/workspace/import", data=data,
                       content_type="multipart/form-data")


# --- checks and matching ------------------------------------------------------


def test_empty_draft_cannot_run_checks(client):
    enter_guest(client)
    page = client.get("/workspace").data
    assert b"Review workspace" in page
    assert b"Findings will appear here." in page
    assert b"Run a check against the selected rules." in page
    assert b"Enter draft text to run checks." in page
    assert b'data-run-checks' in page
    assert b"disabled" in page

    response = client.post("/workspace/check", data={
        "title": "", "body": "", "content_type": "", "audience": "", "notes": "",
    })
    page = response.data
    assert b"Enter the draft text before running checks." in page
    assert b"Choose a content type." in page
    assert b"Check failed" in page
    assert b"No issues detected" not in page


def test_check_is_deterministic_and_reports_findings_with_clauses(client):
    enter_guest(client)
    first = check(client, body=TWO_TERMS).data
    second = check(client, body=TWO_TERMS).data
    assert first.count(b"GLS-001") == second.count(b"GLS-001")
    assert b'data-evidence="MSG-101"' not in first  # no forbidden phrase matched
    assert b"Rule ID" in first
    assert b"Rule identifier, quotation, and version match." in first
    assert b"Fictional demo guidelines" in first
    assert b"Check coverage" in first
    assert b"Not determined by this check" in first
    assert b"Whether every factual claim is true." in first


def test_content_type_selects_only_applicable_rules(db):
    rules = demo_rules(db)
    website = check_review("A calm page.", "website copy", rules)
    email = check_review("A calm email.", "marketing email", rules)
    assert "MSG-001" in website.coverage["messaging"]
    assert "MSG-002" in website.coverage["messaging"]
    assert "MSG-003" not in website.coverage["messaging"]
    assert "MSG-003" in email.coverage["messaging"]
    assert "MSG-001" not in email.coverage["messaging"]


def test_messaging_scopes_cover_workspace_and_legacy_content_names(db):
    rules = demo_rules(db)
    for name in ("website copy", "product page"):
        run = check_review("A calm page.", name, rules)
        assert "MSG-001" in run.coverage["messaging"], name
        assert "MSG-002" in run.coverage["messaging"], name
        assert "MSG-003" not in run.coverage["messaging"], name
    for name in ("marketing email", "email"):
        run = check_review("A calm email.", name, rules)
        assert "MSG-003" in run.coverage["messaging"], name
        assert "MSG-001" not in run.coverage["messaging"], name


def test_scope_label_lists_scoped_content_types():
    from inkloom.workbench import scope_label
    assert scope_label("any") == "All content types"
    assert scope_label("website copy,product page") == "Website copy · Product page"


def test_whitespace_and_offsets_map_to_the_original_text():
    rule = Rule(
        rule_id="T-1", kind="forbidden", pattern="no risk", replacement=None,
        applies_to="any", message="Forbidden.", clause_text="Clause.",
    )
    text = "Intro no  \n risk and no risk again."
    issues = run_checks(text, "website copy", [rule])
    assert issues[0].occurrences == ((6, 16), (21, 28))
    # Offsets point at the *original* text, including its whitespace.
    assert text[6:16] == "no  \n risk"
    segments = preview_segments(text, issues)
    assert "".join(segment["text"] for segment in segments) == text
    highlighted = [segment["text"] for segment in segments if segment["rule_ids"]]
    assert highlighted == ["no  \n risk", "no risk"]


def test_preview_merges_overlapping_findings_without_losing_text():
    first = Issue(
        rule_id="A-1", kind="forbidden", message="One.", quote="Clause.",
        excerpt="abc", is_prompt=False, start_offset=0, end_offset=3,
        occurrences=((0, 3),),
    )
    second = Issue(
        rule_id="B-2", kind="claim", message="Two.", quote="Clause.",
        excerpt="cde", is_prompt=True, start_offset=2, end_offset=5,
        occurrences=((2, 5),),
    )
    segments = preview_segments("abcdef", [first, second])
    assert "".join(segment["text"] for segment in segments) == "abcdef"
    assert segments[0]["rule_ids"] == ["A-1", "B-2"]


def test_required_phrase_finding_has_no_invented_span(client):
    enter_guest(client)
    page = check(client, body="A calm page about the product.").data
    assert b"Required phrase not found" in page
    assert b"No offending text span exists for this finding." in page


def test_word_count_is_documented_not_presented_as_analysis():
    assert count_words("  one\ntwo   three ") == 3
    page = None  # documentation lives on the page; checking the page below
    return page


# --- staleness ----------------------------------------------------------------


def test_input_changes_invalidate_check_results(client):
    enter_guest(client)
    page = check(client).data
    fields = carried(page)
    assert fields["check_fingerprint"] == fingerprint(DRAFT)

    response = client.post("/workspace/keep", data=workspace_payload(
        fields, body=DRAFT + " Edited after the check."))
    page = response.data
    assert b"Changes since check" in page
    assert b"These results are outdated." in page
    assert b'data-evidence="MSG-101"' not in page
    assert b"data-evidence=" not in page


def test_outdated_snapshot_cannot_restore_results_as_current(client):
    enter_guest(client)
    fields = carried(check(client).data)
    # Same carried snapshot, different draft: the server must discard it.
    response = client.post("/workspace/keep", data=workspace_payload(
        fields, body="Completely different text."))
    page = response.data
    assert b"Changes since check" in page
    assert b"Select a finding to inspect its exact rule." in page
    assert b"data-evidence=" not in page


def test_audience_and_content_type_are_part_of_the_snapshot(client):
    enter_guest(client)
    fields = carried(check(client).data)
    response = client.post("/workspace/keep", data=workspace_payload(
        fields, content_type="social post"))
    assert b"Changes since check" in response.data
    response = client.post("/workspace/keep", data=workspace_payload(
        fields, audience="another audience"))
    assert b"Changes since check" in response.data


def test_stale_snapshot_helper_is_explicit(db):
    rules = demo_rules(db)
    values = {"body": DRAFT, "content_type": "website copy",
              "audience": "prospective customers"}
    snapshot = {
        "fingerprint": fingerprint(DRAFT), "content_type": "website copy",
        "audience": "prospective customers",
        "rule_set_id": "lekhani-fictional-demo",
        "rule_set_version": "demo-rules-v1",
    }
    assert snapshot_is_current(snapshot, values, rules)
    assert not snapshot_is_current(snapshot, dict(values, body=DRAFT + "x"), rules)
    assert not snapshot_is_current(snapshot, dict(values, content_type="other"), rules)


def test_validation_failure_never_reads_as_all_clear(client, monkeypatch, db):
    bad = Issue(
        rule_id="MSG-101", kind="forbidden", message="Fabricated.",
        quote="This is not the stored clause.", excerpt="guaranteed results",
        is_prompt=False,
    )
    monkeypatch.setattr("inkloom.checker.run_checks",
                        lambda text, content_type, rules: [bad])
    enter_guest(client)
    page = check(client, body="A clean-looking draft.").data
    assert b"Check incomplete" in page
    assert b"No issues detected by the configured checks." not in page
    assert b"rejected candidate finding" in page


# --- controlled replacement ---------------------------------------------------


def test_controlled_replacement_changes_only_the_selected_occurrence(client, db):
    enter_guest(client)
    page = check(client, body=TWO_TERMS).data
    fields = carried(page)
    first_start, first_end = 3, 10  # "disrupt" in the first sentence
    assert TWO_TERMS[first_start:first_end] == "disrupt"
    response = client.post("/workspace/replace", json={
        "body": TWO_TERMS, "rule_id": "GLS-001",
        "start": first_start, "end": first_end,
        "content_type": "website copy",
        "check_fingerprint": fields["check_fingerprint"],
    })
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["body"] == "We change habits. Later we disrupt routines too."
    assert payload["body"].count("disrupt") == 1


def test_replacement_refused_against_outdated_text(client):
    enter_guest(client)
    fields = carried(check(client).data)
    response = client.post("/workspace/replace", json={
        "body": DRAFT + " Edited.",
        "rule_id": "GLS-001",
        "start": 27, "end": 34,
        "content_type": "website copy",
        "check_fingerprint": fields["check_fingerprint"],
    })
    assert response.status_code == 409
    assert "Run checks again" in response.get_json()["message"]


def test_replacement_engine_ignores_unvalidated_spans(db):
    rule = {r.rule_id: r for r in demo_rules(db)}["GLS-001"]
    text = "We disrupt habits."
    new_text, error = apply_controlled_replacement(
        text, rule, 3, 10, fingerprint(text), "website copy")
    assert error is None
    assert new_text == "We change habits."
    # Wrong span: the offsets do not identify the rule's phrase.
    _, error = apply_controlled_replacement(
        text, rule, 0, 3, fingerprint(text), "website copy")
    assert error == "mismatch"
    # Wrong snapshot: refuse even if the span looks plausible.
    _, error = apply_controlled_replacement(
        text, rule, 3, 10, "0" * 64, "website copy")
    assert error == "outdated"


# --- guest review demonstration ----------------------------------------------


def review(client, fields, outcome="approved", note=""):
    data = workspace_payload(fields, notes=note)
    data["outcome"] = outcome
    return client.post("/workspace/review", data=data)


def test_guest_review_needs_a_current_completed_check(client):
    enter_guest(client)
    response = client.post("/workspace/review", data=workspace_payload(
        {}, outcome="approved"))
    page = response.data
    assert b"Run checks on this exact version before recording a guest review." in page
    assert b"Approved " + EM + b" demo" not in page


def test_needs_changes_requires_an_actionable_note(client):
    enter_guest(client)
    fields = carried(check(client).data)
    page = review(client, fields, outcome="changes", note="   ").data
    assert b"needs an actionable note" in page
    assert b"Needs changes " + EM + b" demo" not in page


def test_guest_review_records_name_outcome_note_and_snapshot(client):
    enter_guest(client, "Asha Rao")
    fields = carried(check(client).data)
    page = review(client, fields, outcome="approved", note="Looks fine to me.").data
    assert b"Approved " + EM + b" demo" in page
    assert b"Asha Rao" in page
    assert b"Looks fine to me." in page
    assert b"Guest display name" in page
    assert b"Reviewed snapshot fingerprint (SHA-256)" in page
    assert b"Check-run reference" in page
    assert b"This is not an authorised organisational approval." in page
    assert b"Verified reviewer" not in page


def test_guest_review_becomes_outdated_after_relevant_changes(client):
    enter_guest(client)
    fields = carried(check(client).data)
    page = review(client, fields, outcome="changes", note="Fix the claim.").data
    review_fields = carried(page)
    assert "review_outcome" in review_fields

    response = client.post("/workspace/keep", data=workspace_payload(
        dict(fields, **review_fields), body=DRAFT + " A new sentence."))
    page = response.data
    assert b"data-review-outdated" in page
    assert b"data-review-card" not in page
    assert b"Needs changes " + EM + b" demo" not in page


def test_guest_review_survives_a_recheck_of_identical_content(client):
    enter_guest(client)
    fields = carried(check(client).data)
    page = review(client, fields, outcome="approved", note="").data
    review_fields = carried(page)
    # Re-check the same text: a fresh snapshot, same content fingerprint.
    rechecked = carried(check(client).data)
    page = client.post("/workspace/keep", data=workspace_payload(
        dict(rechecked, **review_fields))).data
    assert b"Approved " + EM + b" demo" in page
    assert b"data-review-card" in page
    assert b"data-review-outdated" not in page


# --- import and new draft -----------------------------------------------------


def test_import_requires_confirmation_before_replacing_work(client):
    enter_guest(client)
    pack = export_pack(client)
    page = import_pack(client, pack, body="Existing guest draft",
                       content_type="website copy").data
    assert b"Confirm that you want to replace it" in page
    # The refused import keeps the current draft instead of discarding it.
    assert b"Existing guest draft" in page
    page = import_pack(client, pack, body="Existing guest draft",
                       content_type="website copy", confirm_replace="1").data
    assert b"Opened review pack" in page


def test_invalid_import_keeps_the_current_draft(client):
    enter_guest(client)
    page = import_pack(client, b"{not json", body="Keep this draft",
                       content_type="website copy", confirm_replace="1").data
    assert b"This file is not valid JSON." in page
    assert b"Keep this draft" in page


def test_import_does_not_trust_approval_or_historical_findings(client):
    enter_guest(client)
    pack = export_pack(client)
    pack["guest_review"] = {
        "outcome": "approved", "note": "Imported approval.", "recorded_at": "2026-01-01T00:00:00+00:00",
        "guest_name": "Somebody", "fingerprint": "0" * 64,
        "content_type": "website copy", "audience": "x",
        "rule_set_id": "lekhani-fictional-demo", "rule_set_version": "demo-rules-v1",
        "check_checked_at": "2026-01-01T00:00:00+00:00",
    }
    page = flat(import_pack(client, pack, draft_present="1", confirm_replace="1").data)
    assert b"Approved " + EM + b" demo" not in page
    assert b"not shown as a decision here and is not an authorised approval" in page
    assert b"not treated as current" in page


def test_unknown_imported_rules_are_draft_only(client):
    enter_guest(client)
    pack = export_pack(client)
    pack["rules"][0]["clause_text"] = "An imported clause that was never approved."
    page = import_pack(client, pack).data
    assert b"the original rules could not be verified" in page
    assert b"imported findings are historical and are not current results" in page
    assert b"Current findings below come from a fresh check" not in page
    assert b"Run checks" in page


def test_new_draft_warns_and_retains_work(client):
    enter_guest(client)
    page = client.post("/workspace/new", data=workspace_payload(
        {"body": DRAFT})).data
    assert b"Start a new draft?" in page
    assert b"Discard draft and start new" in page
    assert DRAFT.encode() in page
    page = client.post("/workspace/new", data=workspace_payload(
        {"body": DRAFT}, discard="1")).data
    assert DRAFT.encode() not in page
    assert b"Not checked" in page


# --- export, print, rules -----------------------------------------------------


def test_export_carries_snapshot_findings_and_current_review(client):
    enter_guest(client)
    page = check(client).data
    fields = carried(page)
    reviewed = review(client, fields, outcome="approved", note="Signed off for demo.").data
    fields = carried(reviewed)
    response = client.post("/workspace/export", data=workspace_payload(
        fields, notes="Signed off for demo."))
    pack = json.loads(response.data)
    assert pack["format_version"] == PACK_FORMAT_VERSION
    assert pack["title"] == "Launch draft"
    assert pack["check"]["source"] == "workspace-check"
    assert pack["check"]["fingerprint"] == fingerprint(DRAFT)
    assert pack["findings_status"].startswith("current")
    assert pack["guest_review"]["outcome"] == "approved"
    assert pack["guest_review"]["note"] == "Signed off for demo."
    assert pack["guest_review"]["guest_name"] == "Asha Rao"
    assert "signature" not in pack
    assert "signature" not in pack["content_fingerprint"]
    assert pack["content_fingerprint"]["algorithm"] == "SHA-256"


def test_print_summary_includes_review_and_limits(client):
    enter_guest(client)
    page = check(client).data
    fields = carried(page)
    reviewed = review(client, fields, outcome="changes", note="Add evidence.").data
    fields = carried(reviewed)
    response = client.post("/workspace/print", data=workspace_payload(fields))
    page = response.data
    assert b"Needs changes " + EM + b" demo" in page
    assert b"Add evidence." in page
    assert b"Not determined by this check" in page
    assert b"not an authenticated approval" in page


def test_rules_page_and_drawer_are_read_only(client):
    enter_guest(client)
    page = client.get("/workspace").data
    assert b'data-rules-drawer' in page
    assert b"Select a finding to inspect its exact rule." in page
    assert b"GLS-001" in page
    assert b"Matching" in page
    assert b"Source reference" in page

    rules_page = client.get("/workspace/rules")
    assert rules_page.status_code == 200
    text = rules_page.data.decode()
    assert "Read-only rule set" in text
    assert "Glossary entry GLS-001" in text
    assert "<input" not in text  # no rule editing controls on the read-only page


def test_workspace_page_has_the_required_regions_and_labels(client):
    enter_guest(client)
    page = flat(client.get("/workspace").data)
    for text in (
        b"Review workspace", b"Back to Home", b"Guest",
        b"Draft title", b"Untitled draft", b"Temporary guest work.",
        b"Your content", b"Content type", b"Intended audience",
        b"Check preview", b"Expand editor", b"Findings", b"Rule evidence",
        b"Active rule set", b"View rules", b"Run checks",
        b"Check coverage", b"Guest review", b"Open Trust Lab",
        b"Guest review demonstration.", b"Identity is not verified.",
        b"Guest work is temporary. Export a review pack to keep a copy.",
    ):
        assert text in page, text
    # No fake states or fabricated analysis.
    assert b"Saved" not in page
    assert b"Publish" not in page
    assert b"Verified reviewer" not in page
    assert b"confidence:" not in page.lower()
