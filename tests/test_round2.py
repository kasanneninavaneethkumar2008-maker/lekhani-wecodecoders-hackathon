"""Round 2 scope: GreenLeaf sample fixture, TXT/PDF import, and the roadmap.

The sample must use the same real checker and citation validator as manual
input, must not run until explicitly loaded, and must never blend with the
workspace's own guideline library.
"""
import io
import json
import re

import pypdf
import pytest

from inkloom.checker import Issue, check_review, run_checks, validate_citations
from inkloom.file_import import (
    MAX_DRAFT_LENGTH,
    MAX_UPLOAD_BYTES,
    NO_TEXT_MESSAGE,
    validate_and_extract,
)
from inkloom.review_pack import PACK_FORMAT_VERSION
from inkloom.rulesets import (
    SAMPLE_CONTENT_TYPE,
    SAMPLE_REVISED_TEXT,
    SAMPLE_RULE_SET_ID,
    SAMPLE_RULE_SET_VERSION,
    SAMPLE_TEXT,
    demo_rules,
    sample_rules,
)
from inkloom.workbench import fingerprint


def enter_guest(client, name="Asha Rao"):
    client.post("/guest/login", data={"name": name})


def flat(page):
    return re.sub(rb"\s+", b" ", page)


def carried(page_bytes):
    """Read the hidden snapshot/review fields a browser would carry."""
    text = page_bytes.decode("utf-8")
    return {
        key: value.replace("&quot;", '"').replace("&amp;", "&")
        for key, value in re.findall(
            r'name="((?:check|review)_[^"]+)" value="([^"]*)"', text
        )
    }


SAMPLE_VALUES = {
    "title": "GreenLeaf — fictional sample draft",
    "body": SAMPLE_TEXT,
    "content_type": SAMPLE_CONTENT_TYPE,
    "audience": "Prospective customers (fictional)",
    "notes": "",
    "rule_mode": "sample",
}


def sample_check(client, **overrides):
    data = dict(SAMPLE_VALUES)
    data.update(overrides)
    return client.post("/workspace/check", data=data)


def sample_export(client, fields=None, **overrides):
    data = dict(SAMPLE_VALUES)
    data.update(fields or carried(sample_check(client).data))
    data.update(overrides)
    response = client.post("/workspace/export", data=data)
    assert response.status_code == 200
    return json.loads(response.data)


# --- PDF helpers --------------------------------------------------------------

def pdf_with_text_pages(texts):
    """A minimal, valid text PDF (one short line per page)."""
    body = []
    page_ids, content_ids = [], []
    next_id = 3
    for _ in texts:
        page_ids.append(next_id)
        content_ids.append(next_id + 1)
        next_id += 2
    font_id = next_id
    body.append((1, b"<< /Type /Catalog /Pages 2 0 R >>"))
    kids = b" ".join(b"%d 0 R" % page for page in page_ids)
    body.append((2, b"<< /Type /Pages /Kids [" + kids
                 + b"] /Count %d >>" % len(texts)))
    for index, text in enumerate(texts):
        content = (b"BT /F1 12 Tf 72 720 Td ("
                   + text.encode("latin-1") + b") Tj ET")
        body.append((page_ids[index],
                     b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                     b"/Resources << /Font << /F1 %d 0 R >> >> /Contents %d 0 R >>"
                     % (font_id, content_ids[index])))
        body.append((content_ids[index],
                     b"<< /Length %d >>\nstream\n" % len(content) + content
                     + b"\nendstream"))
    body.append((font_id,
                 b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"))
    body.sort()
    out = bytearray(b"%PDF-1.4\n")
    offsets = {}
    for oid, data in body:
        offsets[oid] = len(out)
        out += b"%d 0 obj\n" % oid + data + b"\nendobj\n"
    xref = len(out)
    size = max(offsets) + 1
    out += b"xref\n0 %d\n" % size
    out += b"0000000000 65535 f \n"
    for oid in range(1, size):
        out += b"%010d 00000 n \n" % offsets.get(oid, 0)
    out += (b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n"
            % (size, xref))
    return bytes(out)


def encrypted_pdf():
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.encrypt("secret")
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def blank_pdf(pages=1):
    writer = pypdf.PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=612, height=792)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def upload(client, raw, filename, **overrides):
    data = {
        "title": "Existing title",
        "body": "Keep this existing draft.",
        "content_type": "website copy",
        "audience": "prospective customers",
        "notes": "",
        "rule_mode": "workspace",
    }
    data.update(overrides)
    data["draft_file"] = (io.BytesIO(raw), filename)
    return client.post("/workspace/import-file", data=data,
                       content_type="multipart/form-data")


# --- fixture identity and real checker results --------------------------------

def test_sample_fixture_is_isolated_and_scoped():
    rules = sample_rules()
    assert {rule.rule_id for rule in rules} == {
        "GLOSS-01", "GLOSS-02", "MSG-01", "CLAIM-01", "CLAIM-02",
    }
    assert {rule.rule_set_id for rule in rules} == {SAMPLE_RULE_SET_ID}
    assert {rule.rule_set_version for rule in rules} == {SAMPLE_RULE_SET_VERSION}
    assert {rule.applies_to for rule in rules} == {SAMPLE_CONTENT_TYPE}
    assert {rule.kind for rule in rules} == {
        "glossary", "required", "claim",
    }


def test_sample_text_produces_exactly_the_five_expected_findings():
    run = check_review(SAMPLE_TEXT, SAMPLE_CONTENT_TYPE, sample_rules())
    assert run.complete is True
    assert run.rejected == ()
    assert [issue.rule_id for issue in run.issues] == [
        "GLOSS-01", "GLOSS-02", "MSG-01", "CLAIM-01", "CLAIM-02",
    ]
    by_id = {issue.rule_id: issue for issue in run.issues}
    assert by_id["GLOSS-01"].occurrences == ((0, 10),)   # "Green Leaf"
    assert by_id["GLOSS-02"].occurrences == ((17, 22),)  # "users"
    assert by_id["MSG-01"].occurrences == ()             # missing phrase
    assert by_id["CLAIM-01"].occurrences == ((27, 31),)  # "best"
    assert by_id["CLAIM-02"].occurrences == ((58, 68),)  # "guaranteed"
    assert by_id["CLAIM-01"].is_prompt and by_id["CLAIM-02"].is_prompt
    assert all(issue.quote == rule.clause_text
               for issue in run.issues
               for rule in sample_rules()
               if rule.rule_id == issue.rule_id)


def test_revised_sample_has_no_findings_under_the_sample_rules():
    run = check_review(SAMPLE_REVISED_TEXT, SAMPLE_CONTENT_TYPE, sample_rules())
    assert run.complete is True
    assert run.issues == ()


def test_required_sample_sentence_includes_its_terminal_full_stop():
    rules = {rule.rule_id: rule for rule in sample_rules()}
    missing_period = run_checks(
        "GreenLeaf helps customers. Explore plans on our website",
        SAMPLE_CONTENT_TYPE, [rules["MSG-01"]],
    )
    with_period = run_checks(
        SAMPLE_REVISED_TEXT, SAMPLE_CONTENT_TYPE, [rules["MSG-01"]],
    )
    assert [issue.rule_id for issue in missing_period] == ["MSG-01"]
    assert with_period == []


def test_sample_rules_are_not_applied_to_other_content_types():
    run = check_review(SAMPLE_TEXT, "website copy", sample_rules())
    assert run.issues == ()
    assert run.coverage == {
        "terminology": [], "messaging": [], "claim_patterns": [],
    }


def test_sample_rules_do_not_mix_with_the_workspace_library(db):
    workspace = demo_rules(db)
    assert {rule.rule_set_id for rule in workspace}.isdisjoint(
        {SAMPLE_RULE_SET_ID})
    assert {rule.rule_id for rule in workspace}.isdisjoint(
        {rule.rule_id for rule in sample_rules()})


def _sample_issue(rule, *, quote=None, set_id=None, version=None):
    return Issue(
        rule_id=rule.rule_id,
        kind=rule.kind,
        message=rule.message,
        quote=rule.clause_text if quote is None else quote,
        excerpt=None,
        is_prompt=rule.kind == "claim",
        rule_set_id=rule.rule_set_id if set_id is None else set_id,
        rule_set_version=(rule.rule_set_version if version is None else version),
    )


def test_sample_citations_reject_unknown_altered_and_wrong_version():
    rules = sample_rules()
    by_id = {rule.rule_id: rule for rule in rules}
    valid = _sample_issue(by_id["GLOSS-01"])
    unknown = _sample_issue(by_id["GLOSS-01"])
    object.__setattr__(unknown, "rule_id", "GLOSS-99")
    altered = _sample_issue(by_id["GLOSS-02"], quote="A rewritten clause.")
    wrong_version = _sample_issue(by_id["MSG-01"], version="demo-v2")

    result = validate_citations(
        [valid, unknown, altered, wrong_version], rules,
        rule_set_id=SAMPLE_RULE_SET_ID,
        rule_set_version=SAMPLE_RULE_SET_VERSION,
    )
    assert [issue.rule_id for issue in result.kept] == ["GLOSS-01"]
    assert len(result.discarded) == 3
    assert "Unknown rule identifier." in result.rejection_reasons
    assert "Quoted clause does not exactly match the stored rule." in result.rejection_reasons
    assert "Rule-set identifier or version does not match." in result.rejection_reasons


# --- loading the sample through the real routes ------------------------------

def test_empty_workspace_offers_three_explicit_input_methods(client):
    enter_guest(client)
    page = client.get("/workspace").data
    assert b"Start with your content" in page
    assert b"1. Write or paste" in page
    assert b"2. Import file" in page
    assert b"3. Test a sample" in page
    # The sample is never loaded automatically.
    assert SAMPLE_TEXT.encode() not in page
    assert b"Not checked" in page


def test_loading_the_sample_requires_confirmation_and_keeps_work(client):
    enter_guest(client)
    page = client.post("/workspace/sample", data={
        "title": "My work", "body": "My existing draft.",
        "content_type": "website copy", "audience": "", "notes": "",
    }).data
    assert b"Load the fictional sample?" in page
    assert b"My existing draft." in page
    assert SAMPLE_TEXT.encode() not in page
    assert b"demo-v1" in page

    page = client.post("/workspace/sample", data={
        "title": "My work", "body": "My existing draft.",
        "content_type": "website copy", "audience": "", "notes": "",
        "confirm_sample": "1",
    }).data
    assert SAMPLE_TEXT.encode() in page
    assert b"Fictional demo guidelines" in page
    assert b"demo-v1" in page
    assert b"Product promotion" in page
    assert b"Use workspace rules" in page
    assert b"Not checked" in page


def test_loaded_sample_runs_only_its_own_rules(client):
    enter_guest(client)
    page = sample_check(client).data
    for rule_id in (b"GLOSS-01", b"GLOSS-02", b"MSG-01", b"CLAIM-01", b"CLAIM-02"):
        assert rule_id in page
    assert b'data-evidence="GLS-001"' not in page
    assert b'data-evidence="MSG-101"' not in page
    assert b"5\n" in page or b"5 findings" in page
    assert b"lekhani-greenleaf-sample" in page
    assert b"demo-v1" in page
    assert b"Required phrase not found" in page
    assert b"Human review requested" in page
    # Claims are prompts, never verdicts or legal conclusions.
    assert b"does not determine whether the claim is true" in page
    assert b"legal compliance" in page


def test_revised_sample_rechecks_clean_without_overclaiming(client):
    enter_guest(client)
    page = sample_check(client, body=SAMPLE_REVISED_TEXT).data
    assert b"No issues detected by the configured checks." in page
    assert b"This does not establish factual correctness or legal compliance." in page
    assert b'data-evidence="GLOSS-01"' not in page
    assert b'data-finding="GLOSS-01"' not in page


def test_no_applicable_rules_is_stated_explicitly(client):
    enter_guest(client)
    page = sample_check(client, content_type="website copy").data
    assert b"No applicable rules exist for this content type" in page
    assert b"No issues detected by the configured checks." not in page


def test_zero_applicable_rules_keeps_the_active_rule_set_identity():
    run = check_review(SAMPLE_TEXT, "website copy", sample_rules())
    assert run.complete is True
    assert run.issues == ()
    assert (run.rule_set_id, run.rule_set_version) == (
        SAMPLE_RULE_SET_ID, SAMPLE_RULE_SET_VERSION)


def test_recheck_keeps_an_earlier_guest_review_as_outdated(client):
    enter_guest(client)
    fields = carried(sample_check(client).data)
    reviewed = client.post("/workspace/review", data={
        **SAMPLE_VALUES, **fields, "outcome": "approved",
    })
    review_fields = carried(reviewed.data)
    assert b"data-review-card" in reviewed.data

    # The normal workflow: edit and press Run checks again.
    page = client.post("/workspace/check", data={
        **SAMPLE_VALUES,
        "body": SAMPLE_REVISED_TEXT + " A new sentence.",
        **review_fields,
    }).data
    assert b"data-review-outdated" in page
    assert b"data-review-card" not in page
    assert b"A guest review was recorded earlier" not in page
    assert b"This guest review is outdated." in page


def test_switching_back_to_workspace_rules_invalidates_results(client):
    enter_guest(client)
    fields = carried(sample_check(client).data)
    assert fields["check_rule_set_id"] == SAMPLE_RULE_SET_ID
    page = client.post("/workspace/rule-mode", data={
        **SAMPLE_VALUES, **fields,
    }).data
    assert b"Changes since check" in page
    assert b'data-evidence="GLOSS-01"' not in page
    assert b"lekhani-fictional-demo" in page
    assert SAMPLE_TEXT.encode() in page  # the draft itself is kept


def test_sample_pack_exports_and_reimports_with_fresh_local_checks(client):
    enter_guest(client)
    pack = sample_export(client)
    assert pack["format_version"] == PACK_FORMAT_VERSION
    assert pack["rule_set"] == {
        "id": SAMPLE_RULE_SET_ID, "version": SAMPLE_RULE_SET_VERSION,
    }
    assert {rule["rule_id"] for rule in pack["rules"]} == {
        "GLOSS-01", "GLOSS-02", "MSG-01", "CLAIM-01", "CLAIM-02",
    }
    assert len(pack["findings"]) == 5

    raw = json.dumps(pack).encode("utf-8")
    page = client.post("/workspace/import", data={
        "pack": (io.BytesIO(raw), "sample-pack.json"),
        "title": "", "body": "", "content_type": "", "audience": "",
        "notes": "", "rule_mode": "workspace",
    }, content_type="multipart/form-data").data
    assert b"Opened review pack" in page
    assert b"checks were rerun with the local rule set" in page
    assert b'data-evidence="GLOSS-01"' in page
    assert b'data-evidence="GLS-001"' not in page
    assert b"demo-v1" in page


# --- TXT and PDF import -------------------------------------------------------

def test_txt_import_previews_then_uses_text(client):
    enter_guest(client)
    page = upload(client, b"Imported plain text.\nSecond line.",
                  "draft.txt").data
    assert b"Import preview" in page
    assert b"nothing has been replaced yet" in page
    assert b"UTF-8 text file" in page
    assert b"Imported plain text." in page
    assert b"Use this text" in page
    assert b"Cancel import" in page
    # The current draft is still in the desk until the guest confirms.
    assert b"Keep this existing draft." in page

    page = client.post("/workspace/import-file", data={
        "import_stage": "use",
        "import_text": "Imported plain text.\nSecond line.",
        "import_filename": "draft.txt",
        "title": "",
        "content_type": "website copy",
        "audience": "",
        "notes": "",
        "rule_mode": "workspace",
    }).data
    assert b"Imported plain text." in page
    assert b"Not checked" in page
    assert b'value="draft"' in page  # title taken from the filename stem


def test_pdf_import_extracts_real_text(client):
    enter_guest(client)
    raw = pdf_with_text_pages([
        "Green Leaf gives users the best planning experience, with guaranteed results."
    ])
    page = upload(client, raw, "draft.pdf").data
    assert b"Text-based PDF" in page
    assert b"1 page(s)" in page
    assert b"Green Leaf gives users" in page
    assert b"Use this text" in page


def test_text_named_as_pdf_is_rejected_and_pdf_named_as_txt_is_accepted():
    with pytest.raises(Exception) as error:
        validate_and_extract("draft.pdf", b"Just ordinary text.")
    assert "does not look like a PDF" in str(error.value)

    info = validate_and_extract(
        "notes.txt",
        pdf_with_text_pages(["Content found inside a PDF."]),
    )
    assert info["kind"] == "pdf"
    assert "Content found inside a PDF." in info["text"]


def test_import_errors_are_specific_and_keep_the_current_draft(client):
    enter_guest(client)
    cases = [
        (b"", "draft.txt", b"This file is empty."),
        (b"a\x00b", "draft.txt", b"binary document"),
        (b"\xff\xfeh\x00i\x00", "draft.txt", b"not UTF-8 text"),
        (b"\x80\x81\x82", "draft.txt", b"not UTF-8 text"),
        (b"hello", "draft.csv", b"Only UTF-8 .txt files"),
    ]
    for raw, name, expected in cases:
        page = upload(client, raw, name).data
        assert expected in page, name
        assert b"Keep this existing draft." in page
        assert b"Use this text" not in page

    page = upload(client, b"x" * (MAX_UPLOAD_BYTES + 1), "big.txt").data
    assert b"limited to 5 MB" in page
    assert b"Keep this existing draft." in page


def test_oversized_extracted_text_is_refused(client):
    enter_guest(client)
    page = upload(client, b"a" * (MAX_DRAFT_LENGTH + 1), "long.txt").data
    assert b"drafts are limited to 100,000 characters" in page
    assert b"Keep this existing draft." in page


def test_pdf_failures_are_explicit(client):
    enter_guest(client)
    page = upload(client, blank_pdf(1), "scan.pdf").data
    assert NO_TEXT_MESSAGE.encode() in page
    assert b"Keep this existing draft." in page

    page = upload(client, encrypted_pdf(), "locked.pdf").data
    assert b"password-protected" in page

    page = upload(client, blank_pdf(11), "long.pdf").data
    assert b"limited to 10 pages" in page

    page = upload(client, b"%PDF-1.4\nnot a real pdf", "broken.pdf").data
    assert b"could not be read" in page
    assert b"Keep this existing draft." in page


def test_multiple_files_are_refused(client):
    enter_guest(client)
    response = client.post("/workspace/import-file", data={
        "title": "Existing title",
        "body": "Keep this existing draft.",
        "content_type": "website copy",
        "audience": "",
        "notes": "",
        "rule_mode": "workspace",
        "draft_file": [
            (io.BytesIO(b"first file"), "one.txt"),
            (io.BytesIO(b"second file"), "two.txt"),
        ],
    }, content_type="multipart/form-data")
    page = response.data
    assert b"Choose exactly one" in page
    assert b"Keep this existing draft." in page


def test_imported_markup_is_escaped_not_rendered(client):
    enter_guest(client)
    page = upload(client, b"<script>alert(1)</script> & more", "x.txt").data
    assert b"<script>alert(1)</script>" not in page
    assert b"&lt;script&gt;alert(1)&lt;/script&gt;" in page


# --- Round 3 roadmap ----------------------------------------------------------

def test_home_round_3_cards_are_planned_not_functional(client):
    enter_guest(client)
    page = flat(client.get("/home").data)
    for text in (
        b"Coming in Round 3",
        b"Planned \xc2\xb7 Round 3",
        b"Accounts &amp; saved workspaces",
        b"Google sign-in, persistent drafts, user-specific access, and deliberate guest-work import.",
        b"Verified review requests",
        b"Assigned authorised reviewers, email notifications, recorded authenticated decisions, and approval invalidation.",
        b"Versioned brand rules &amp; evidence",
        b"Organisation-specific approved rules, preserved versions, evidence expiry, and outdated-guideline identification.",
        b"These features are planned, not available in the current guest version.",
    ):
        assert text in page, text
    assert b'id="round-3"' in page
    # No controls that look like they connect or send anything.
    for absent in (b"Sign in with Google", b"Save to cloud", b"Send email",
                   b"Connect Google", b"action=\"https://accounts.google.com"):
        assert absent not in page, absent


def test_workspace_has_a_quiet_round_3_link(client):
    enter_guest(client)
    page = flat(client.get("/workspace").data)
    assert b"What\xe2\x80\x99s coming in Round 3" in page
    assert b'href="/home#round-3"' in page


def test_guest_name_limits_and_unicode_are_enforced(client):
    client.post("/guest/login", data={"name": "नवनीत कुमार"})
    with client.session_transaction() as session:
        assert session["guest_name"] == "नवनीत कुमार"
    page = client.get("/home").data
    assert "नवनीत कुमार".encode() in page

    client.get("/guest/logout")
    long_name = "A" * 100
    client.post("/guest/login", data={"name": long_name})
    with client.session_transaction() as session:
        assert session["guest_name"] == "A" * 60
