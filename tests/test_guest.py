"""Guest welcome / role-selection flow.

The guest session is temporary and never touches the database: no guest name,
draft, or decision is written, and the existing creator/reviewer access
controls still apply (a guest has no `g.user`, so workflow routes redirect).
"""
from tests.conftest import choose_role


def _continue_as_guest(client, name="Sam Rivera"):
    return client.post("/guest/login", data={"name": name}, follow_redirects=True)


def _guest_counts(db):
    return {
        table: db.execute(f"SELECT COUNT(*) AS c FROM {table}").fetchone()["c"]
        for table in ("users", "drafts", "checks", "issues", "decisions")
    }


# --- start page ---------------------------------------------------------------


def test_welcome_page_is_the_first_page(client):
    response = client.get("/")
    assert response.status_code == 200
    # Guest entry: name field + slide control + accessible alternative.
    assert b'name="name"' in response.data
    assert b"Welcome to Lekhani" in response.data
    assert b"Slide to enter" in response.data
    assert b"Continue without sliding" in response.data
    # No password sign-in, sign-in button, or coming-soon placeholder.
    assert b'type="password"' not in response.data
    assert b"Google" not in response.data
    assert b"Coming soon" not in response.data


def test_empty_guest_name_is_rejected(client):
    response = client.post("/guest/login", data={"name": "   "},
                           follow_redirects=True)
    assert response.status_code == 200
    with client.session_transaction() as sess:
        assert "guest_name" not in sess


def test_guest_name_lives_only_in_the_session(client, db):
    before = _guest_counts(db)
    response = client.post("/guest/login", data={"name": "Sam Rivera"})
    assert response.status_code == 302
    with client.session_transaction() as sess:
        assert sess["guest_name"] == "Sam Rivera"
        assert "user_id" not in sess  # a guest is not a database user
    assert _guest_counts(db) == before


# --- role selection with the character ----------------------------------------


def test_role_page_greets_the_guest_by_name(client):
    _continue_as_guest(client, "Sam Rivera")
    response = client.get("/guest/role")
    assert response.status_code == 200
    assert b"Welcome back, Sam Rivera" in response.data
    assert b"Continue as Creator" in response.data
    assert b"Continue as Reviewer" in response.data


def test_role_pages_require_a_guest_name(client):
    response = client.get("/guest/role", follow_redirects=True)
    assert response.status_code == 200
    assert b"Welcome to Lekhani" in response.data  # bounced back to the welcome
    assert client.get("/guest/home", follow_redirects=True).status_code == 200


def test_guest_picks_a_role_and_reaches_guest_home(client, db):
    before = _guest_counts(db)
    _continue_as_guest(client)
    response = client.post("/guest/role", data={"role": "creator"},
                           follow_redirects=True)
    assert response.status_code == 200
    assert b"Welcome back" in response.data
    assert b"New Draft" in response.data
    assert b"Old Drafts" in response.data
    # Google sign-in shown in the top corner, labelled Coming soon.
    assert b"Google sign-in" in response.data
    assert b"Coming soon" in response.data
    assert _guest_counts(db) == before


def test_invalid_guest_role_is_refused(client):
    _continue_as_guest(client)
    client.post("/guest/role", data={"role": "admin"})
    with client.session_transaction() as sess:
        assert "guest_role" not in sess
    # Home with no role chosen sends the guest back to the role picker.
    response = client.get("/guest/home", follow_redirects=True)
    assert b"Welcome back" in response.data
    assert b"Continue as Creator" in response.data


# --- gated actions ------------------------------------------------------------


def test_guest_cannot_create_a_draft(client, db):
    before = _guest_counts(db)
    _continue_as_guest(client)
    client.post("/guest/role", data={"role": "creator"})

    response = client.get("/guest/new-draft")
    assert response.status_code == 200
    assert b"Google sign-in" in response.data
    # The real creation route still refuses (no database user in the session).
    assert client.get("/drafts/new", follow_redirects=False).status_code in (302, 403)
    assert client.post("/drafts/new", data={"title": "x", "body": "y",
                                            "content_type": "email",
                                            "audience": "a"},
                       follow_redirects=False).status_code in (302, 403)
    assert _guest_counts(db) == before


def test_guest_sees_no_other_users_drafts(client, db):
    # A creator creates a real draft in the app (nothing is pre-seeded).
    choose_role(client, "creator")
    client.post("/drafts/new", data={
        "title": "Private working draft",
        "body": "Internal text that a guest must never see.",
        "content_type": "email",
        "audience": "Internal team",
    }, follow_redirects=True)
    mine = db.execute(
        "SELECT title FROM drafts WHERE title = 'Private working draft'"
    ).fetchone()
    assert mine is not None  # real drafts are the only drafts

    # A fresh guest session can never see it.
    with client.session_transaction() as sess:
        sess.clear()  # a different person, fresh browser
    _continue_as_guest(client)
    client.post("/guest/role", data={"role": "creator"})
    response = client.get("/guest/old-drafts")
    assert response.status_code == 200
    assert b"Google sign-in" in response.data
    assert "Private working draft" not in response.data.decode()
    # The real listing route still refuses a guest.
    assert client.get("/drafts/", follow_redirects=False).status_code in (302, 403)


def test_reviewer_guest_cannot_save_a_decision(client, db):
    # A creator submits a real draft (nothing is pre-seeded).
    choose_role(client, "creator")
    client.post("/drafts/new", data={
        "title": "Needs a decision",
        "body": "Text that awaits review.",
        "content_type": "email",
        "audience": "Members",
    }, follow_redirects=True)
    draft = db.execute(
        "SELECT id FROM drafts WHERE title = 'Needs a decision'"
    ).fetchone()
    assert draft is not None
    client.post(f"/drafts/{draft['id']}", data={"action": "submit"})

    # A guest reviewer in a fresh session cannot record the decision.
    with client.session_transaction() as sess:
        sess.clear()
    before = _guest_counts(db)
    _continue_as_guest(client)
    client.post("/guest/role", data={"role": "reviewer"})

    response = client.get("/guest/home")
    assert response.status_code == 200
    assert b"Google sign-in" in response.data

    response = client.post(f"/review/{draft['id']}",
                           data={"decision": "approved"},
                           follow_redirects=False)
    assert response.status_code in (302, 403)  # refused: guest has no role
    assert _guest_counts(db) == before
    status = db.execute("SELECT status FROM drafts WHERE id = ?",
                        (draft["id"],)).fetchone()["status"]
    assert status == "submitted"


# --- sign out -----------------------------------------------------------------


def test_sign_out_clears_the_guest_session_only(client, db):
    before = _guest_counts(db)
    _continue_as_guest(client)
    client.get("/guest/logout", follow_redirects=True)
    with client.session_transaction() as sess:
        assert "guest_name" not in sess
        assert "guest_role" not in sess
    assert _guest_counts(db) == before
    # The guest is back at the welcome page.
    response = client.get("/guest/home", follow_redirects=True)
    assert b"Continue without sliding" in response.data


# --- existing demo flow is untouched ------------------------------------------


def test_demo_role_chooser_still_works_alongside_guests(client):
    _continue_as_guest(client)  # a guest session exists first
    choose_role(client, "creator")
    assert client.get("/drafts/").status_code == 200
    choose_role(client, "reviewer")
    assert client.get("/review/").status_code == 200
