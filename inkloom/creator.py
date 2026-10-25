"""Creator workflow: submit a draft, check it, revise it, send it for review."""
from flask import (
    Blueprint,
    flash,
    g,
    redirect,
    render_template,
    request,
    url_for,
)

from .auth import role_required, selection_required
from .checker import check_text, load_rules
from .db import get_db, utcnow

bp = Blueprint("creator", __name__, url_prefix="/drafts")

CONTENT_TYPES = ("product page", "email", "social post", "blog article", "internal memo")

# Statuses in which the creator may edit the text.
EDITABLE_STATUSES = ("draft", "changes_requested")


def _form_errors(form) -> dict:
    errors = {}
    title = form.get("title", "").strip()
    body = form.get("body", "").strip()
    content_type = form.get("content_type", "").strip()
    audience = form.get("audience", "").strip()
    if not title:
        errors["title"] = "A title is required."
    if not body:
        errors["body"] = "Draft text is required."
    if content_type not in CONTENT_TYPES:
        errors["content_type"] = "Choose one of the listed content types."
    if not audience:
        errors["audience"] = "The intended audience is required."
    return errors


def _get_own_draft(draft_id):
    """Load a draft only if it belongs to the signed-in creator (404 otherwise)."""
    draft = (
        get_db()
        .execute(
            "SELECT * FROM drafts WHERE id = ? AND author_id = ?",
            (draft_id, g.user["id"]),
        )
        .fetchone()
    )
    if draft is None:
        from flask import abort

        abort(404)
    return draft


def _latest_check(db, draft_id):
    return db.execute(
        "SELECT * FROM checks WHERE draft_id = ? ORDER BY id DESC LIMIT 1",
        (draft_id,),
    ).fetchone()


def _issues_for(check_id):
    if check_id is None:
        return []
    return (
        get_db()
        .execute("SELECT * FROM issues WHERE check_id = ? ORDER BY id", (check_id,))
        .fetchall()
    )


@bp.route("/")
@selection_required
@role_required("creator")
def draft_list():
    drafts = (
        get_db()
        .execute(
            """SELECT d.*,
                      (SELECT COUNT(*) FROM checks c WHERE c.draft_id = d.id) AS check_count
               FROM drafts d WHERE d.author_id = ? ORDER BY d.updated_at DESC, d.id DESC""",
            (g.user["id"],),
        )
        .fetchall()
    )
    return render_template("creator/draft_list.html", drafts=drafts)


@bp.route("/new", methods=("GET", "POST"))
@selection_required
@role_required("creator")
def draft_new():
    errors = {}
    values = {"title": "", "body": "", "content_type": "", "audience": ""}
    if request.method == "POST":
        values = {key: request.form.get(key, "") for key in values}
        errors = _form_errors(request.form)
        if not errors:
            db = get_db()
            now = utcnow()
            cur = db.execute(
                """INSERT INTO drafts
                   (title, body, content_type, audience, author_id, status, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, 'draft', ?, ?)""",
                (
                    values["title"].strip(),
                    values["body"].strip(),
                    values["content_type"].strip(),
                    values["audience"].strip(),
                    g.user["id"],
                    now,
                    now,
                ),
            )
            db.commit()
            flash("Draft saved.")
            return redirect(url_for("creator.draft_detail", draft_id=cur.lastrowid))
    return render_template(
        "creator/draft_form.html",
        title="New draft",
        values=values,
        errors=errors,
        content_types=CONTENT_TYPES,
        action=url_for("creator.draft_new"),
    )


@bp.route("/<int:draft_id>", methods=("GET", "POST"))
@selection_required
@role_required("creator")
def draft_detail(draft_id):
    draft = _get_own_draft(draft_id)
    db = get_db()

    errors = {}
    if request.method == "POST":
        action = request.form.get("action", "")
        if action == "revise":
            errors = _form_errors(request.form)
            if not errors:
                db.execute(
                    """UPDATE drafts SET title = ?, body = ?, content_type = ?,
                       audience = ?, updated_at = ? WHERE id = ?""",
                    (
                        request.form["title"].strip(),
                        request.form["body"].strip(),
                        request.form["content_type"].strip(),
                        request.form["audience"].strip(),
                        utcnow(),
                        draft["id"],
                    ),
                )
                db.commit()
                flash("Draft revised. Run the checks again to see new results.")
                return redirect(url_for("creator.draft_detail", draft_id=draft["id"]))
            draft = {
                **dict(draft),
                "title": request.form.get("title", draft["title"]),
                "body": request.form.get("body", draft["body"]),
                "content_type": request.form.get("content_type", draft["content_type"]),
                "audience": request.form.get("audience", draft["audience"]),
            }
        elif action == "check":
            if draft["status"] not in EDITABLE_STATUSES:
                flash("This draft is with the reviewer and cannot be checked right now.")
                return redirect(url_for("creator.draft_detail", draft_id=draft["id"]))
            now = utcnow()
            cur = db.execute(
                """INSERT INTO checks (draft_id, checked_by, created_at, content_type, body_snapshot)
                   VALUES (?, ?, ?, ?, ?)""",
                (draft["id"], g.user["id"], now, draft["content_type"], draft["body"]),
            )
            check_id = cur.lastrowid
            issues = check_text(draft["body"], draft["content_type"], load_rules(db))
            for issue in issues:
                db.execute(
                    """INSERT INTO issues
                       (check_id, rule_id, kind, message, clause_quote, excerpt, is_prompt)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        check_id,
                        issue.rule_id,
                        issue.kind,
                        issue.message,
                        issue.quote,
                        issue.excerpt,
                        1 if issue.is_prompt else 0,
                    ),
                )
            db.commit()
            flash(
                f"Checks complete: {len(issues)} issue(s) found."
                if issues
                else "Checks complete: no issues found."
            )
            return redirect(url_for("creator.draft_detail", draft_id=draft["id"]))
        elif action == "submit":
            if draft["status"] not in EDITABLE_STATUSES:
                flash("Only a draft or a returned draft can be sent for review.")
            else:
                db.execute(
                    "UPDATE drafts SET status = 'submitted', updated_at = ? WHERE id = ?",
                    (utcnow(), draft["id"]),
                )
                db.commit()
                flash("Draft sent for review.")
                return redirect(url_for("creator.draft_detail", draft_id=draft["id"]))

    latest_check = _latest_check(db, draft["id"])
    issues = _issues_for(latest_check["id"] if latest_check else None)
    history = db.execute(
        """SELECT c.id, c.created_at,
                  (SELECT COUNT(*) FROM issues i WHERE i.check_id = c.id) AS issue_count
           FROM checks c WHERE c.draft_id = ? ORDER BY c.id DESC""",
        (draft["id"],),
    ).fetchall()
    decisions = db.execute(
        """SELECT d.*, u.display_name FROM decisions d
           JOIN users u ON u.id = d.reviewer_id
           WHERE d.draft_id = ? ORDER BY d.id DESC""",
        (draft["id"],),
    ).fetchall()
    return render_template(
        "creator/draft_detail.html",
        draft=draft,
        latest_check=latest_check,
        issues=issues,
        history=history,
        decisions=decisions,
        errors=errors,
        content_types=CONTENT_TYPES,
        editable=draft["status"] in EDITABLE_STATUSES,
    )
