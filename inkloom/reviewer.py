"""Reviewer workflow: read submitted drafts and record Approved / Needs changes."""
from flask import (
    Blueprint,
    abort,
    flash,
    g,
    redirect,
    render_template,
    request,
    url_for,
)

from .auth import role_required
from .db import get_db, utcnow

bp = Blueprint("reviewer", __name__, url_prefix="/review")

DECISIONS = {"approved": "Approved", "needs_changes": "Needs changes"}


@bp.route("/")
@role_required("reviewer")
def queue():
    db = get_db()
    submitted = db.execute(
        """SELECT d.*, u.display_name AS author_name FROM drafts d
           JOIN users u ON u.id = d.author_id
           WHERE d.status = 'submitted'
           ORDER BY d.updated_at, d.id""",
    ).fetchall()
    recently_decided = db.execute(
        """SELECT d.*, u.display_name AS author_name,
                  dec.decision, dec.created_at AS decided_at,
                  ru.display_name AS reviewer_name
           FROM drafts d
           JOIN users u ON u.id = d.author_id
           JOIN decisions dec ON dec.id = (
               SELECT id FROM decisions WHERE draft_id = d.id ORDER BY id DESC LIMIT 1)
           JOIN users ru ON ru.id = dec.reviewer_id
           WHERE d.status IN ('approved', 'changes_requested')
           ORDER BY dec.id DESC LIMIT 20""",
    ).fetchall()
    return render_template(
        "reviewer/queue.html",
        submitted=submitted,
        recently_decided=recently_decided,
        decisions=DECISIONS,
    )


@bp.route("/<int:draft_id>", methods=("GET", "POST"))
@role_required("reviewer")
def review_draft(draft_id):
    db = get_db()
    draft = db.execute(
        """SELECT d.*, u.display_name AS author_name FROM drafts d
           JOIN users u ON u.id = d.author_id WHERE d.id = ?""",
        (draft_id,),
    ).fetchone()
    if draft is None:
        abort(404)

    if request.method == "POST":
        if draft["status"] != "submitted":
            flash("Only a submitted draft can receive a decision.")
            return redirect(url_for("reviewer.review_draft", draft_id=draft_id))
        decision = request.form.get("decision", "")
        if decision not in DECISIONS:
            flash("Choose Approved or Needs changes.")
            return redirect(url_for("reviewer.review_draft", draft_id=draft_id))
        comment = request.form.get("comment", "").strip()
        now = utcnow()
        db.execute(
            """INSERT INTO decisions (draft_id, reviewer_id, decision, comment, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (draft_id, g.user["id"], decision, comment, now),
        )
        new_status = "approved" if decision == "approved" else "changes_requested"
        db.execute(
            "UPDATE drafts SET status = ?, updated_at = ? WHERE id = ?",
            (new_status, now, draft_id),
        )
        db.commit()
        flash(f"Decision recorded: {DECISIONS[decision]}.")
        return redirect(url_for("reviewer.queue"))

    # Latest completed check and its citation-validated issues, for context.
    latest_check = db.execute(
        "SELECT * FROM checks WHERE draft_id = ? ORDER BY id DESC LIMIT 1",
        (draft_id,),
    ).fetchone()
    issues = []
    if latest_check:
        issues = db.execute(
            "SELECT * FROM issues WHERE check_id = ? ORDER BY id",
            (latest_check["id"],),
        ).fetchall()
    decisions = db.execute(
        """SELECT d.*, u.display_name AS reviewer_name FROM decisions d
           JOIN users u ON u.id = d.reviewer_id
           WHERE d.draft_id = ? ORDER BY d.id DESC""",
        (draft_id,),
    ).fetchall()
    return render_template(
        "reviewer/review_detail.html",
        draft=draft,
        latest_check=latest_check,
        issues=issues,
        decisions=decisions,
        decision_labels=DECISIONS,
        can_decide=draft["status"] == "submitted",
    )
