"""Guest preview: a temporary, session-only way to look around Inkloom.

A guest is NOT a database user. The guest's name and chosen role live only in
this browser session (a signed cookie); nothing about a guest — no name, no
draft, no decision — is ever written to the database. Guests therefore cannot
create or save drafts, and cannot record review decisions; the pages say so
and point at Google sign-in, which is not implemented yet ("Coming soon").

The existing demo role chooser and its server-side role enforcement are
untouched: `g.user` stays None for a guest, so the real creator/reviewer
routes still redirect or 403 exactly as before.
"""
import functools

from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

bp = Blueprint("guest", __name__, url_prefix="/guest")

ROLES = ("creator", "reviewer")
MAX_NAME_LENGTH = 60


def guest_name() -> str:
    name = session.get("guest_name", "")
    return name.strip() if isinstance(name, str) else ""


def guest_role() -> str:
    role = session.get("guest_role", "")
    return role if role in ROLES else ""


def guest_required(view):
    """Require a guest name in the session; otherwise return to the welcome page."""

    @functools.wraps(view)
    def wrapped(**kwargs):
        if not guest_name():
            flash("Enter a name to continue as a guest.")
            return redirect(url_for("index"))
        return view(**kwargs)

    return wrapped


@bp.route("/login", methods=("POST",))
def login():
    """Record a temporary guest name in this session only (never in the database)."""
    name = request.form.get("name", "").strip()
    if not name:
        flash("Enter your name to continue as a guest.")
        return redirect(url_for("index"))
    session["guest_name"] = name[:MAX_NAME_LENGTH]
    session.pop("guest_role", None)  # a fresh guest starts without a role
    return redirect(url_for("site.home"))


@bp.route("/logout")
def logout():
    """Forget this guest session (name and role); nothing was stored anywhere else)."""
    session.pop("guest_name", None)
    session.pop("guest_role", None)
    flash("Signed out of the guest preview. Nothing was saved.")
    return redirect(url_for("index"))


@bp.route("/role", methods=("GET", "POST"))
@guest_required
def role_pick():
    """Greet the guest by name and let them choose Creator or Reviewer."""
    if request.method == "POST":
        role = request.form.get("role", "")
        if role not in ROLES:
            flash('Choose "Continue as Creator" or "Continue as Reviewer".')
            return redirect(url_for("guest.role_pick"))
        session["guest_role"] = role
        return redirect(url_for("guest.home"))
    return render_template("guest/role.html", name=guest_name())


@bp.route("/home")
@guest_required
def home():
    role = guest_role()
    if not role:
        return redirect(url_for("guest.role_pick"))
    return render_template("guest/home.html", name=guest_name(), role=role)


@bp.route("/new-draft")
@guest_required
def new_draft():
    return render_template(
        "guest/gated.html",
        name=guest_name(),
        role=guest_role(),
        heading="Save drafts with Google sign-in",
        paragraphs=[
            "Creating and saving a draft needs a signed-in account, so this "
            "preview can't start one for you.",
            "Once Google sign-in arrives, you'll be able to write a draft, run "
            "the checks, revise it, and send it for review — and it will be "
            "saved to your account.",
        ],
    )


@bp.route("/old-drafts")
@guest_required
def old_drafts():
    return render_template(
        "guest/gated.html",
        name=guest_name(),
        role=guest_role(),
        heading="Your saved drafts appear here after sign-in",
        paragraphs=[
            "Saved drafts belong to a signed-in account, so a guest has none to "
            "show — and other people's drafts are never shown here.",
            "After Google sign-in, this is where your saved drafts will be "
            "listed so you can open, revise, or re-check them.",
        ],
    )
