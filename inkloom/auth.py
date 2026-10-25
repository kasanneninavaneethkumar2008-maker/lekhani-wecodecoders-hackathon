"""Local demo role selection and server-side role enforcement.

IMPORTANT: choosing a role here is NOT authentication and NOT a security
boundary. It only switches this browser session to a demo account (created
on first use) so the creator and reviewer workflows can be demonstrated
locally. There is no password sign-in in this demo.

The selected role is still enforced on the server for every request: the
user is re-read from the database and checked against the route's allowed
role (wrong role => HTTP 403), so each role sees and uses its own pages.
"""
import functools

from flask import (
    Blueprint,
    abort,
    flash,
    g,
    redirect,
    request,
    session,
    url_for,
)

from .db import get_db, utcnow

bp = Blueprint("auth", __name__)

ROLES = ("creator", "reviewer")
DEMO_EMAILS = {
    "creator": "creator@inkloom.test",
    "reviewer": "reviewer@inkloom.test",
}
# Placeholder stored in password_hash (schema requires a value). It is not a
# credential: no sign-in exists, and this string can never pass a hash check.
NO_PASSWORD = "!demo-no-password"

HOME_FOR_ROLE = {
    "creator": "creator.draft_list",
    "reviewer": "reviewer.queue",
}


def get_demo_user_for(role):
    """Return the demo account for a role, creating it only if absent.

    The demo account always uses its dedicated address (DEMO_EMAILS), so
    choosing a role can never attach the session to any other account.
    Existing rows are never modified or deleted, so no drafts or other
    database data are reset by choosing a role.
    """
    db = get_db()
    user = db.execute(
        "SELECT * FROM users WHERE email = ?", (DEMO_EMAILS[role],)
    ).fetchone()
    if user is None:
        now = utcnow()
        cur = db.execute(
            """INSERT INTO users (email, display_name, password_hash, role, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (DEMO_EMAILS[role], f"Demo {role.capitalize()}", NO_PASSWORD, role, now),
        )
        db.commit()
        user = db.execute(
            "SELECT * FROM users WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
    return user


@bp.before_app_request
def load_selected_user():
    user_id = session.get("user_id")
    if user_id is None:
        g.user = None
    else:
        g.user = (
            get_db().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        )
        if g.user is None:
            session.clear()


def selection_required(view):
    """Require that a demo role has been chosen; otherwise show the chooser."""

    @functools.wraps(view)
    def wrapped(**kwargs):
        if g.user is None:
            return redirect(url_for("index"))
        return view(**kwargs)

    return wrapped


def role_required(*roles):
    """Allow only the given roles. Enforced server-side; aborts with 403."""

    def decorator(view):
        @functools.wraps(view)
        def wrapped(**kwargs):
            if g.user is None:
                return redirect(url_for("index"))
            if g.user["role"] not in roles:
                abort(403)
            return view(**kwargs)

        return wrapped

    return decorator


@bp.route("/continue", methods=("POST",))
def continue_as():
    """Switch this browser session to the chosen demo role (local demo only)."""
    role = request.form.get("role", "")
    if role not in ROLES:
        flash('Choose "Continue as Creator" or "Continue as Reviewer".')
        return redirect(url_for("index"))
    user = get_demo_user_for(role)
    session.clear()
    session["user_id"] = user["id"]
    flash(
        f"Local demo: now acting as {role}. "
        "This is a role switch, not sign-in — it is not authentication."
    )
    return redirect(url_for(HOME_FOR_ROLE[role]))
