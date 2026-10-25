"""Lekhani public pages: Home, About, Contact, workspace, and Trust Lab.

The workspace keeps a guest's draft in the request/response only. Pages that
need the checker use the single shared implementation in `checker.py`; the
Trust Lab and the Rule Change Simulator use isolated fictional rule sets from
`rulesets.py`. Nothing here persists a draft, activates imported rules, or
delivers contact/issue messages.

Workspace checks are synchronous. Every set of findings on the page is
produced by running the shared checker over the submitted text — a hidden
"snapshot" sent by the browser is only used to decide whether those results
still describe the current draft, never to restore findings. That makes an
out-of-date or forged result impossible to present as current.
"""
import json
import os
from datetime import datetime, timezone

from flask import (
    Blueprint,
    Response,
    jsonify,
    render_template,
    request,
    session,
)

from .checker import (
    MAX_DRAFT_LENGTH,
    RULE_SET_ID,
    RULE_SET_VERSION,
    Issue,
    check_review,
    validate_citations,
)
from .file_import import (
    MAX_PDF_PAGES,
    MAX_UPLOAD_BYTES,
    FileImportError,
    validate_and_extract,
)
from .guest import guest_required
from .review_pack import (
    MAX_PACK_BYTES,
    ReviewPackError,
    make_review_pack,
    validate_review_pack,
)
from .rulesets import (
    LAB_RULE_SET_ID,
    LAB_V1,
    SAMPLE_AUDIENCE,
    SAMPLE_BRAND,
    SAMPLE_CONTENT_TYPE,
    SAMPLE_LANGUAGE,
    SAMPLE_RULE_SET_ID,
    SAMPLE_RULE_SET_LABEL,
    SAMPLE_RULE_SET_VERSION,
    SAMPLE_TEXT,
    SAMPLE_TITLE,
    demo_rules,
    lab_rules_v1,
    lab_rules_v2,
    sample_rules,
)
from .simulator import EXAMPLE_TEXT, compare_rule_sets
from .workbench import (
    CATEGORY_FILTERS,
    CATEGORY_LABELS,
    CATEGORY_OF_KIND,
    CONTENT_TYPES,
    CONTENT_TYPE_LABELS,
    MAX_AUDIENCE_LENGTH,
    MAX_NOTE_LENGTH,
    MAX_TITLE_LENGTH,
    REVIEW_LABELS,
    REVIEW_OUTCOMES,
    STATUS_LABELS,
    active_rule_set,
    apply_controlled_replacement,
    count_words,
    finding_payload,
    fingerprint,
    make_review,
    make_snapshot,
    normalize_text,
    now_iso,
    preview_segments,
    review_from_form,
    review_is_current,
    rule_views,
    scope_label,
    snapshot_from_form,
    snapshot_is_current,
    status_for,
)

bp = Blueprint("site", __name__)

RULE_SET_NAME = "Fictional demo guidelines"

# Which rule set is explicitly active in this workspace page. The workspace's
# own (seeded) guideline library is the default; the bundled GreenLeaf sample
# is only active after the guest loads it, and the page always says so.
WORKSPACE_RULE_MODE = "workspace"
SAMPLE_RULE_MODE = "sample"
RULE_MODES = (WORKSPACE_RULE_MODE, SAMPLE_RULE_MODE)

TRUST_CASES = (
    ("valid", "Valid citation"),
    ("unknown", "Unknown rule ID"),
    ("altered", "Altered quotation"),
)


@bp.route("/home")
@guest_required
def home():
    return render_template("home.html")


@bp.route("/about")
@guest_required
def about():
    return render_template("about.html")


@bp.route("/contact")
@guest_required
def contact():
    return render_template("contact.html")


@bp.route("/report-issue")
@guest_required
def report_issue():
    return render_template("report_issue.html")


# ---------------------------------------------------------------------------
# Review workspace
# ---------------------------------------------------------------------------


def _rule_mode_from_form(form):
    """Only the sample mode can be requested; anything else is the default."""
    return (SAMPLE_RULE_MODE if form.get("rule_mode") == SAMPLE_RULE_MODE
            else WORKSPACE_RULE_MODE)


def _values_from_form(form):
    """Read workspace fields, normalising line endings at the boundary."""
    return {
        "title": normalize_text(form.get("title") or "").strip()[:MAX_TITLE_LENGTH],
        "body": normalize_text(form.get("body") or ""),
        "content_type": (form.get("content_type") or "").strip().casefold(),
        "audience": normalize_text(form.get("audience") or "").strip()[:MAX_AUDIENCE_LENGTH],
        "notes": normalize_text(form.get("notes") or ""),
        "rule_mode": _rule_mode_from_form(form),
    }


def _empty_values():
    return {"title": "", "body": "", "content_type": "", "audience": "",
            "notes": "", "rule_mode": WORKSPACE_RULE_MODE}


def _rules_for_mode(mode):
    """Resolve the explicitly active rule set. The database is never altered."""
    if mode == SAMPLE_RULE_MODE:
        return sample_rules()
    return demo_rules(_db())


def _rules_for(values):
    return _rules_for_mode(values.get("rule_mode", WORKSPACE_RULE_MODE))


def _rule_set_context(values):
    """Label the rule set honestly, including the fictional sample details."""
    if values.get("rule_mode") == SAMPLE_RULE_MODE:
        return {
            "sample_mode": True,
            "rule_set_name": SAMPLE_RULE_SET_LABEL,
            "rule_set_detail": (f"{SAMPLE_BRAND} sample · {SAMPLE_LANGUAGE} · "
                                f"Product promotion · version {SAMPLE_RULE_SET_VERSION}"),
        }
    return {"sample_mode": False, "rule_set_name": RULE_SET_NAME,
            "rule_set_detail": "Workspace guideline library"}


def _has_work(values):
    return bool(values["body"].strip() or values["title"].strip()
                or values["notes"].strip())


def _draft_errors(values):
    """Validate only what a check actually needs; title and audience are optional."""
    errors = {}
    if not values["body"].strip():
        errors["body"] = "Enter the draft text before running checks."
    elif len(values["body"]) > MAX_DRAFT_LENGTH:
        errors["body"] = f"Drafts are limited to {MAX_DRAFT_LENGTH:,} characters."
    if values["content_type"] not in CONTENT_TYPES:
        errors["content_type"] = "Choose a content type."
    if len(values["notes"]) > MAX_NOTE_LENGTH:
        errors["notes"] = f"Review notes are limited to {MAX_NOTE_LENGTH:,} characters."
    return errors


def _issue_payload(issue):
    return {
        "rule_id": issue.rule_id,
        "kind": issue.kind,
        "message": issue.message,
        "quote": issue.quote,
        "excerpt": issue.excerpt,
        "is_prompt": issue.is_prompt,
        "start_offset": issue.start_offset,
        "end_offset": issue.end_offset,
        "rule_set_id": issue.rule_set_id,
        "rule_set_version": issue.rule_set_version,
        "title": issue.title,
        "occurrences": [{"start": start, "end": end}
                        for start, end in issue.occurrences],
    }


def _render_workspace(values, *, result=None, snapshot=None, review=None,
                      errors=None, check_error=None, export_error=None,
                      import_error=None, review_error=None, import_report=None,
                      file_import_error=None, file_preview=None,
                      confirm_new=False, confirm_sample=False,
                      sample_loaded=False, just_checked=False):
    """Render the desk from submitted values plus a *verified* snapshot.

    `result` is only trusted when `snapshot` still matches the current
    values and active rule set. Otherwise the findings are discarded with an
    understandable notice rather than shown as current.
    """
    rules = _rules_for(values)
    set_context = _rule_set_context(values)
    active = active_rule_set(rules) or (RULE_SET_ID, RULE_SET_VERSION)
    check_current = snapshot_is_current(snapshot, values, rules)
    status = status_for(snapshot, values, rules, failed=bool(errors))
    if check_current and result is None:
        # Deterministic: re-running the same inputs reproduces the same check.
        result = check_review(values["body"], values["content_type"], rules)
    if not check_current:
        result = None

    review_current = review_is_current(review, snapshot, values, rules) and check_current
    review_outdated = bool(review) and not review_current

    rules_by_id = {rule.rule_id: rule for rule in rules}
    evidence = []
    findings = []
    counts = {key: 0 for key in ("terms", "messages", "claims")}
    segments = []
    if result is not None:
        for issue in result.issues:
            category = CATEGORY_OF_KIND.get(issue.kind, "messages")
            counts[category] += 1
            rule = rules_by_id.get(issue.rule_id)
            evidence.append({
                "issue": issue,
                "rule": rule,
                "category": category,
                "category_label": CATEGORY_LABELS[category],
                "applies_label": scope_label(rule.applies_to) if rule else "—",
            })
            findings.append(finding_payload(issue, rules_by_id))
        segments = preview_segments(values["body"], result.issues)

    return render_template(
        "workspace.html",
        values=values,
        errors=errors or {},
        result=result,
        status=status,
        status_label=STATUS_LABELS[status],
        snapshot=snapshot if check_current else None,
        carried_snapshot=snapshot,
        check_current=check_current,
        review=review,
        review_current=review_current,
        review_outdated=review_outdated,
        review_label=REVIEW_LABELS.get(review["outcome"]) if review else "",
        evidence=evidence,
        findings_data=findings,
        preview_segments=segments,
        counts=counts,
        finding_count=len(result.issues) if result is not None else 0,
        content_types=[(value, CONTENT_TYPE_LABELS[value]) for value in CONTENT_TYPES],
        categories=CATEGORY_FILTERS,
        review_outcomes=REVIEW_OUTCOMES,
        rule_views=rule_views(rules),
        active_rule_set={"id": active[0], "version": active[1]},
        rule_set_name=set_context["rule_set_name"],
        rule_set_detail=set_context["rule_set_detail"],
        sample_mode=set_context["sample_mode"],
        sample_meta={
            "brand": SAMPLE_BRAND,
            "language": SAMPLE_LANGUAGE,
            "version": SAMPLE_RULE_SET_VERSION,
            "rule_set_id": SAMPLE_RULE_SET_ID,
            "content_type": SAMPLE_CONTENT_TYPE,
        },
        max_draft_length=MAX_DRAFT_LENGTH,
        max_pack_kb=MAX_PACK_BYTES // 1024,
        max_upload_mb=MAX_UPLOAD_BYTES // (1024 * 1024),
        max_pdf_pages=MAX_PDF_PAGES,
        word_count=count_words(values["body"]),
        char_count=len(values["body"]),
        has_work=_has_work(values),
        check_error=check_error,
        export_error=export_error,
        import_error=import_error,
        review_error=review_error,
        import_report=import_report,
        file_import_error=file_import_error,
        file_preview=file_preview,
        confirm_new=confirm_new,
        confirm_sample=confirm_sample,
        sample_loaded=sample_loaded,
        just_checked=just_checked,
    )


def _check_response():
    values = _values_from_form(request.form)
    errors = _draft_errors(values)
    if errors:
        return _render_workspace(
            values, errors=errors,
            check_error="The check did not run. Fix the highlighted fields and try again.",
        )
    rules = _rules_for(values)
    result = check_review(values["body"], values["content_type"], rules)
    snapshot = make_snapshot(values, result)
    # Carry an earlier guest review forward so a re-check either keeps it
    # current (identical snapshot) or shows it explicitly as outdated. It must
    # never simply vanish because the guest pressed Run checks again.
    return _render_workspace(values, result=result, snapshot=snapshot,
                             review=review_from_form(request.form),
                             just_checked=True)


@bp.route("/workspace", methods=("GET", "POST"))
@guest_required
def workspace():
    if request.method == "POST":
        return _check_response()
    return _render_workspace(_empty_values())


@bp.post("/workspace/check")
@guest_required
def workspace_check():
    return _check_response()


@bp.post("/workspace/keep")
@guest_required
def workspace_keep():
    """Return to the desk carrying the submitted values and snapshot."""
    values = _values_from_form(request.form)
    return _render_workspace(
        values,
        snapshot=snapshot_from_form(request.form),
        review=review_from_form(request.form),
    )


@bp.post("/workspace/new")
@guest_required
def workspace_new():
    """Start an empty draft, warning first when there is unsaved work."""
    values = _values_from_form(request.form)
    work_present = _has_work(values)
    if work_present and request.form.get("discard") != "1":
        return _render_workspace(
            values,
            snapshot=snapshot_from_form(request.form),
            review=review_from_form(request.form),
            confirm_new=True,
        )
    return _render_workspace(_empty_values())


@bp.post("/workspace/sample")
@guest_required
def workspace_sample():
    """Load the bundled fictional sample only when the guest explicitly asks.

    Existing work is never replaced without confirmation, and loading the
    sample does not run checks by itself. It activates the sample's own rule
    set (``demo-v1``), clearly labelled and separate from the workspace rules.
    """
    values = _values_from_form(request.form)
    if _has_work(values) and request.form.get("confirm_sample") != "1":
        return _render_workspace(
            values,
            snapshot=snapshot_from_form(request.form),
            review=review_from_form(request.form),
            confirm_sample=True,
        )
    sample_values = {
        "title": SAMPLE_TITLE,
        "body": SAMPLE_TEXT,
        "content_type": SAMPLE_CONTENT_TYPE,
        "audience": SAMPLE_AUDIENCE,
        "notes": "",
        "rule_mode": SAMPLE_RULE_MODE,
    }
    return _render_workspace(sample_values, sample_loaded=True)


@bp.post("/workspace/rule-mode")
@guest_required
def workspace_rule_mode():
    """Return from the sample rule set to the workspace's own rules.

    The draft and its metadata are kept; the active rule-set version changes,
    so any earlier check and guest review become explicitly outdated.
    """
    values = _values_from_form(request.form)
    values["rule_mode"] = WORKSPACE_RULE_MODE
    return _render_workspace(
        values,
        snapshot=snapshot_from_form(request.form),
        review=review_from_form(request.form),
    )


@bp.post("/workspace/import-file")
@guest_required
def workspace_import_file():
    """Validate a .txt/.pdf upload, then let the guest confirm the text.

    Nothing replaces the current draft until the guest presses “Use this
    text”. Every failure re-renders the desk with the current work intact.
    """
    values = _values_from_form(request.form)

    if request.form.get("import_stage") == "use":
        text = normalize_text(request.form.get("import_text") or "")
        filename = (request.form.get("import_filename") or "")[:200]
        kind = "pdf" if request.form.get("import_kind") == "pdf" else "txt"
        raw_pages = request.form.get("import_pages", "")
        pages = int(raw_pages) if raw_pages.isdigit() else None
        preview = {"kind": kind, "filename": filename, "text": text, "pages": pages}
        if not text.strip():
            return _render_workspace(
                values, file_preview=preview,
                file_import_error="The imported text is empty. Add some text or cancel the import.",
            )
        if len(text) > MAX_DRAFT_LENGTH:
            return _render_workspace(
                values, file_preview=preview,
                file_import_error=(f"Imported text is limited to {MAX_DRAFT_LENGTH:,} "
                                   "characters. Shorten it before using it."),
            )
        values["body"] = text
        if not values["title"].strip():
            stem = os.path.splitext(os.path.basename(
                filename.replace("\\", "/")))[0].strip()
            values["title"] = (stem or "Imported draft")[:MAX_TITLE_LENGTH]
        # A note written for the previous draft cannot describe this one.
        values["notes"] = ""
        return _render_workspace(values)

    uploads = request.files.getlist("draft_file")
    if len(uploads) != 1 or not uploads[0].filename:
        return _render_workspace(
            values,
            file_import_error="Choose exactly one .txt or PDF file to import.",
        )
    upload = uploads[0]
    try:
        raw = upload.read(MAX_UPLOAD_BYTES + 1)
        info = validate_and_extract(upload.filename, raw)
    except FileImportError as exc:
        return _render_workspace(values, file_import_error=str(exc))
    return _render_workspace(values, file_preview=info)


@bp.post("/workspace/review")
@guest_required
def workspace_review():
    """Record a clearly labelled guest review demonstration.

    This is not an approval: identity is unverified and nothing is persisted
    beyond the form that carries the record until the page is closed.
    """
    values = _values_from_form(request.form)
    errors = _draft_errors(values)
    snapshot = snapshot_from_form(request.form)
    review = review_from_form(request.form)
    rules = _rules_for(values)

    if errors:
        return _render_workspace(
            values, errors=errors, snapshot=snapshot, review=review,
            review_error="The guest review was not recorded. Fix the highlighted fields.",
        )
    if not snapshot or not snapshot_is_current(snapshot, values, rules):
        return _render_workspace(
            values, snapshot=snapshot, review=review,
            review_error=("Run checks on this exact version before recording a guest "
                          "review. The last check does not match the current draft."),
        )
    run = check_review(values["body"], values["content_type"], rules)
    if not run.complete or not snapshot["complete"]:
        return _render_workspace(
            values, snapshot=snapshot, review=review,
            review_error=("The current check was incomplete, so a guest review cannot "
                          "be recorded. Resolve the checking problem and run checks again."),
        )
    outcome = request.form.get("outcome", "")
    note = values["notes"].strip()
    if outcome not in REVIEW_OUTCOMES:
        return _render_workspace(
            values, snapshot=snapshot, review=review,
            review_error="Choose “Needs changes” or “Mark approved — demo”.",
        )
    if outcome == "changes" and not note:
        return _render_workspace(
            values, snapshot=snapshot, review=review,
            review_error=("“Needs changes” needs an actionable note explaining what must "
                          "change. Add a note, then record the review again."),
        )
    recorded = make_review(values, outcome, note,
                           guest_name=session.get("guest_name", ""))
    recorded["rule_set_id"] = snapshot["rule_set_id"]
    recorded["rule_set_version"] = snapshot["rule_set_version"]
    recorded["check_checked_at"] = snapshot["checked_at"]
    return _render_workspace(values, snapshot=snapshot, review=recorded)


@bp.post("/workspace/replace")
@guest_required
def workspace_replace():
    """Apply one validated terminology replacement to the checked text.

    The replacement text comes from the stored rule, never from the request.
    """
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(ok=False, message="Expected a JSON request."), 400
    body = data.get("body")
    rule_id = data.get("rule_id")
    start = data.get("start")
    end = data.get("end")
    content_type = data.get("content_type")
    expected_fingerprint = data.get("check_fingerprint")
    rule_mode = data.get("rule_mode", WORKSPACE_RULE_MODE)
    if (not isinstance(body, str) or len(body) > MAX_DRAFT_LENGTH
            or not isinstance(rule_id, str) or len(rule_id) > 100
            or not isinstance(start, int) or not isinstance(end, int)
            or not isinstance(content_type, str)
            or not isinstance(expected_fingerprint, str)
            or rule_mode not in RULE_MODES):
        return jsonify(ok=False, message="The replacement request was malformed."), 400
    body = normalize_text(body)
    rules = _rules_for_mode(rule_mode)
    rule = {item.rule_id: item for item in rules}.get(rule_id)
    new_body, error = apply_controlled_replacement(
        body, rule, start, end, expected_fingerprint, content_type,
    )
    if error == "outdated":
        return jsonify(
            ok=False,
            message=("The draft no longer matches the checked snapshot. Run checks "
                     "again before replacing text."),
        ), 409
    if error == "mismatch":
        return jsonify(
            ok=False,
            message=("That text no longer matches the rule occurrence that was "
                     "checked. Run checks again."),
        ), 400
    if error:
        return jsonify(ok=False, message="This rule has no safe exact replacement."), 400
    return jsonify(
        ok=True,
        body=new_body,
        message="Replaced one occurrence. Run checks again to refresh the findings.",
    )


@bp.post("/workspace/export")
@guest_required
def workspace_export():
    values = _values_from_form(request.form)
    errors = _draft_errors(values)
    if errors:
        return _render_workspace(
            values, errors=errors,
            snapshot=snapshot_from_form(request.form),
            review=review_from_form(request.form),
            export_error="Fix the highlighted fields before exporting a review pack.",
        )
    rules = _rules_for(values)
    result = check_review(values["body"], values["content_type"], rules)
    prior = snapshot_from_form(request.form)
    prior_current = snapshot_is_current(prior, values, rules)
    review = review_from_form(request.form)
    review_current = (review_is_current(review, prior, values, rules)
                      and prior_current)
    check = {
        "status": "current",
        "source": "workspace-check" if prior_current else "export",
        "checked_at": prior["checked_at"] if prior_current else now_iso(),
        "fingerprint": fingerprint(values["body"]),
        "content_type": values["content_type"],
        "audience": values["audience"],
        "complete": result.complete,
        "finding_count": len(result.issues),
        "rejected_count": len(result.rejected),
        "note": ("" if prior_current else
                 "Checks were rerun when this review pack was exported."),
    }
    pack = make_review_pack(
        title=values["title"] or "Untitled draft",
        draft_text=values["body"],
        content_type=values["content_type"],
        audience=values["audience"],
        rules=rules,
        findings=[_issue_payload(issue) for issue in result.issues],
        check=check,
        guest_review=review if review_current else None,
        guest_review_notes=values["notes"],
        findings_status=("current; from the workspace check" if prior_current
                         else "current; checked when this pack was exported"),
    )
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    response = Response(
        json.dumps(pack, ensure_ascii=False, indent=2),
        mimetype="application/json",
        headers={
            "Content-Disposition":
                f'attachment; filename="lekhani-review-pack-{stamp}.json"',
        },
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@bp.post("/workspace/import")
@guest_required
def workspace_import():
    # The import form carries a copy of the draft so any problem can re-render
    # the desk without discarding work. It is still just request state.
    current = _values_from_form(request.form)
    current_snapshot = snapshot_from_form(request.form)
    current_review = review_from_form(request.form)
    work_present = _has_work(current)

    def failed(message):
        return _render_workspace(
            current, snapshot=current_snapshot, review=current_review,
            import_error=message,
        )

    if work_present and request.form.get("confirm_replace") != "1":
        return failed("Opening a review pack replaces the current draft. Confirm "
                      "that you want to replace it, then open the pack again.")
    upload = request.files.get("pack")
    if upload is None or not upload.filename:
        return failed("Choose a review-pack JSON file to open.")
    raw = upload.read(MAX_PACK_BYTES + 1)
    if len(raw) > MAX_PACK_BYTES:
        return failed(f"Review packs are limited to {MAX_PACK_BYTES // 1024:,} KB.")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return failed("This file is not valid JSON.")
    try:
        info = validate_review_pack(payload, _db())
    except ReviewPackError as exc:
        return failed(str(exc))

    content_type = (info["content_type"] or "").strip().casefold()
    import_note = None
    if content_type not in CONTENT_TYPES:
        content_type = "other"
        import_note = ("The pack's content type was not recognised, so it was imported "
                       "as “Other”. Choose a content type and run checks again.")
    values = {
        "title": info["title"][:MAX_TITLE_LENGTH],
        "body": normalize_text(info["draft_text"]),
        "content_type": content_type,
        "audience": info["audience"],
        "notes": info["guest_review_notes"],
    }
    values["rule_mode"] = info["rule_mode"] if info["known_rule_set"] else WORKSPACE_RULE_MODE
    result = None
    snapshot = None
    if info["known_rule_set"] and values["body"].strip():
        rules = _rules_for_mode(info["rule_mode"])
        result = check_review(values["body"], values["content_type"], rules)
        snapshot = make_snapshot(values, result, source="import")
    report = {
        "known_rule_set": info["known_rule_set"],
        "fingerprint_matches": info["fingerprint_matches"],
        "rule_set": info["rule_set"],
        "imported_findings": info["findings"],
        "notes": info["guest_review_notes"],
        "imported_review_present": info["imported_review_present"],
        "import_note": import_note,
        "title": info["title"],
    }
    return _render_workspace(
        values, result=result, snapshot=snapshot, import_report=report,
        just_checked=bool(result),
    )


@bp.post("/workspace/print")
@guest_required
def workspace_print():
    values = _values_from_form(request.form)
    errors = _draft_errors(values)
    if errors:
        return _render_workspace(
            values, errors=errors,
            snapshot=snapshot_from_form(request.form),
            review=review_from_form(request.form),
            export_error="Fix the highlighted fields before printing a summary.",
        )
    rules = _rules_for(values)
    set_context = _rule_set_context(values)
    result = check_review(values["body"], values["content_type"], rules)
    prior = snapshot_from_form(request.form)
    check_current = snapshot_is_current(prior, values, rules)
    review = review_from_form(request.form)
    review_current = (review_is_current(review, prior, values, rules)
                      and check_current)
    return render_template(
        "print_summary.html",
        values=values,
        result=result,
        guest_name=session.get("guest_name", ""),
        rule_set_name=set_context["rule_set_name"],
        rule_set_detail=set_context["rule_set_detail"],
        checked_at=(prior["checked_at"] if check_current else now_iso()),
        check_source=("workspace check" if check_current else
                      "check made when this summary was created"),
        review=review if review_current else None,
        review_outdated=bool(review) and not review_current,
    )


@bp.route("/workspace/rules")
@guest_required
def workspace_rules():
    mode = SAMPLE_RULE_MODE if request.args.get("mode") == SAMPLE_RULE_MODE \
        else WORKSPACE_RULE_MODE
    values = {"rule_mode": mode}
    rules = _rules_for_mode(mode)
    set_context = _rule_set_context(values)
    active = active_rule_set(rules) or (RULE_SET_ID, RULE_SET_VERSION)
    return render_template(
        "workspace_rules.html",
        rule_views=rule_views(rules),
        active_rule_set={"id": active[0], "version": active[1]},
        rule_set_name=set_context["rule_set_name"],
        rule_set_detail=set_context["rule_set_detail"],
        sample_mode=set_context["sample_mode"],
        rule_mode=mode,
    )


# ---------------------------------------------------------------------------
# Trust Lab
# ---------------------------------------------------------------------------


def _trust_cases():
    rule = {r.rule_id: r for r in lab_rules_v1()}["LAB-MSG-101"]
    return {
        "valid": {
            "key": "valid",
            "label": "Valid citation",
            "rule_id": rule.rule_id,
            "quote": rule.clause_text,
            "stored_clause": rule.clause_text,
            "description": "A candidate that reuses the stored identifier and clause exactly.",
        },
        "unknown": {
            "key": "unknown",
            "label": "Unknown rule ID",
            "rule_id": "LAB-UNKNOWN-999",
            "quote": rule.clause_text,
            "stored_clause": None,
            "description": "A candidate that cites an identifier the rule set does not contain.",
        },
        "altered": {
            "key": "altered",
            "label": "Altered quotation",
            "rule_id": rule.rule_id,
            "quote": rule.clause_text.replace("Never use", "Avoid using"),
            "stored_clause": rule.clause_text,
            "description": "A candidate whose identifier exists but whose quotation was rewritten.",
        },
    }


def _validate_trust_case(key):
    """Run a lab candidate through the real shared validator."""
    cases = _trust_cases()
    case = cases[key]
    rules = lab_rules_v1()
    by_id = {rule.rule_id: rule for rule in rules}
    rule = by_id.get(case["rule_id"])
    issue = Issue(
        rule_id=case["rule_id"],
        kind="forbidden",
        message="Lab candidate finding, used only inside the Trust Lab.",
        quote=case["quote"],
        excerpt="guaranteed results" if rule is not None else None,
        is_prompt=False,
        rule_set_id=LAB_RULE_SET_ID,
        rule_set_version=LAB_V1,
    )
    validation = validate_citations([issue], rules)
    accepted = bool(validation.kept)
    if accepted:
        code = "accepted"
        message = "Accepted: the identifier, clause, and version match."
    elif rule is None:
        code = "unknown"
        message = ("Rejected: this rule identifier does not exist in the "
                   "selected rule set.")
    elif case["quote"] != rule.clause_text:
        code = "altered"
        message = "Rejected: the quotation does not match the stored clause."
    else:
        code = "version"
        message = ("Rejected: the finding references a different rule-set "
                   "version.")
    return {
        "case": case,
        "accepted": accepted,
        "code": code,
        "message": message,
        "stored_clause": case["stored_clause"],
        "rejection_reasons": validation.rejection_reasons,
    }


def _render_lab(**overrides):
    cases = _trust_cases()
    context = {
        "cases": cases,
        "case_order": TRUST_CASES,
        "selected": "valid",
        "outcome": None,
        "simulation_text": "",
        "simulation_loaded_example": False,
        "comparison": None,
        "sim_error": None,
        "max_draft_length": MAX_DRAFT_LENGTH,
        "example_text": EXAMPLE_TEXT,
        "v1_version": lab_rules_v1()[0].rule_set_version,
        "v2_version": lab_rules_v2()[0].rule_set_version,
    }
    context.update(overrides)
    return render_template("trust_lab.html", **context)


@bp.route("/trust-lab", methods=("GET", "POST"))
@guest_required
def trust_lab():
    if request.method == "POST":
        key = request.form.get("case", "valid")
        if key not in _trust_cases():
            key = "valid"
        return _render_lab(selected=key, outcome=_validate_trust_case(key))
    return _render_lab()


@bp.post("/trust-lab/simulate")
@guest_required
def trust_lab_simulate():
    text = request.form.get("simulation_text", "")
    load_example = request.form.get("load_example") == "1"
    if load_example:
        return _render_lab(simulation_text=EXAMPLE_TEXT,
                           simulation_loaded_example=True,
                           comparison=compare_rule_sets(EXAMPLE_TEXT,
                                                        lab_rules_v1(),
                                                        lab_rules_v2()))
    if not text.strip():
        return _render_lab(sim_error="Enter simulation text or load the fictional example.")
    if len(text) > MAX_DRAFT_LENGTH:
        return _render_lab(
            simulation_text=text,
            sim_error=f"Simulation text is limited to {MAX_DRAFT_LENGTH:,} characters.",
        )
    return _render_lab(simulation_text=text,
                       comparison=compare_rule_sets(text, lab_rules_v1(),
                                                    lab_rules_v2()))


def _db():
    from .db import get_db

    return get_db()
