"""End-to-end workflow tests: role choice, access, checks, decisions.

There is no password sign-in in this demo; the tests exercise the
"Continue as Creator" / "Continue as Reviewer" flow instead.
"""
import re

from tests.conftest import choose_role


# --- the chooser itself ------------------------------------------------------


def test_app_opens_on_the_lekhani_welcome_page(client):
    response = client.get("/")
    assert response.status_code == 200
    body = response.data
    # Public brand is Lekhani; the formal project name is not shown here.
    assert b"Lekhani" in body
    assert b"Inkloom" not in body
    # The agreed welcome copy.
    assert b"Words carry trust." in body
    assert b"Review them with care." in body
    assert b"Named after the Sanskrit word for" in body
    assert b"responsible review to digital communication." in body
    assert b"Every issue cites a rule. Every decision stays human." in body
    # Guest entry card, stated as a guest preview rather than a sign-in.
    assert b"Welcome to Lekhani" in body
    assert b"Your name" in body
    assert b'placeholder="Enter your name"' in body
    assert b"Slide to enter" in body
    assert b"Continue without sliding" in body
    assert b"not a sign-in" in body
    # No sign-in/coming-soon placeholders and no password field.
    assert b"Google" not in body
    assert b"Coming soon" not in body
    assert b'type="password"' not in body


def test_no_login_route_remains(client):
    assert client.get("/login").status_code == 404
    assert client.post("/login", data={}).status_code == 404


def test_invalid_role_choice_leaves_the_session_unset(client):
    response = client.post("/continue", data={"role": "hacker"}, follow_redirects=True)
    assert response.status_code == 200
    # Still no role selected: workflow pages redirect back to the welcome page.
    follow = client.get("/drafts/", follow_redirects=True)
    assert follow.status_code == 200
    assert b"Welcome to Lekhani" in follow.data


def test_pages_without_a_selected_role_redirect_to_the_welcome_page(client):
    for path in ("/drafts/", "/review/"):
        response = client.get(path, follow_redirects=True)
        assert response.status_code == 200
        assert b"Welcome to Lekhani" in response.data


# --- server-side role enforcement -------------------------------------------


def test_creator_choice_grants_creator_pages_only(client):
    choose_role(client, "creator")
    assert client.get("/drafts/").status_code == 200
    assert client.get("/drafts/new").status_code == 200
    assert client.get("/review/").status_code == 403


def test_reviewer_choice_grants_reviewer_pages_only(client):
    choose_role(client, "reviewer")
    assert client.get("/review/").status_code == 200
    assert client.get("/drafts/").status_code == 403
    assert client.get("/drafts/new").status_code == 403


def test_role_switch_replaces_the_previous_role(client):
    choose_role(client, "creator")
    assert client.get("/drafts/").status_code == 200
    # Switching role re-points the same session to the other demo account.
    choose_role(client, "reviewer")
    assert client.get("/drafts/").status_code == 403
    assert client.get("/review/").status_code == 200


# --- persistence of the choice -----------------------------------------------


def test_chosen_role_is_stored_server_side_per_session(client, db):
    client.post("/continue", data={"role": "creator"})
    with client.session_transaction() as sess:
        user_id = sess["user_id"]
    user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    assert user["role"] == "creator"

    client.post("/continue", data={"role": "reviewer"})
    with client.session_transaction() as sess:
        other_id = sess["user_id"]
    other = db.execute("SELECT * FROM users WHERE id = ?", (other_id,)).fetchone()
    assert other["role"] == "reviewer"
    assert other_id != user_id


# --- creator workflow --------------------------------------------------------


def _create_draft(client, title="Test landing page", body="A calm sentence.",
                  content_type="product page", audience="New visitors"):
    return client.post(
        "/drafts/new",
        data={
            "title": title,
            "body": body,
            "content_type": content_type,
            "audience": audience,
            "action": "revise",
        },
        follow_redirects=True,
    )


def db_id_from_response(client, title):
    response = client.get("/drafts/")
    match = re.search(rf"/drafts/(\d+)\">" + re.escape(title), response.data.decode())
    assert match, f"draft {title!r} not listed"
    return int(match.group(1))


def _create_and_submit(client, title):
    _create_draft(client, title=title)
    draft_id = db_id_from_response(client, title)
    client.post(f"/drafts/{draft_id}", data={"action": "submit"})
    return draft_id


def test_creator_submits_check_revises_and_sends_for_review(client, db):
    choose_role(client, "creator")

    # 1. Submit draft text with content type and intended audience.
    _create_draft(
        client,
        title="Launch page",
        body="We will disrupt the industry. Act now for guaranteed results.",
    )
    draft = db.execute("SELECT * FROM drafts WHERE title = 'Launch page'").fetchone()
    assert draft is not None
    assert draft["author_id"] == db.execute(
        "SELECT id FROM users WHERE email = 'creator@inkloom.test'"
    ).fetchone()["id"]
    assert draft["created_at"] and draft["updated_at"]
    assert draft["status"] == "draft"

    # 2. Run checks; issues persist with validated citations.
    client.post(f"/drafts/{draft['id']}", data={"action": "check"})
    check = db.execute(
        "SELECT * FROM checks WHERE draft_id = ?", (draft["id"],)
    ).fetchone()
    assert check is not None
    issues = db.execute(
        "SELECT * FROM issues WHERE check_id = ?", (check["id"],)
    ).fetchall()
    assert issues, "expected issues for the messy draft"
    for issue in issues:
        rule = db.execute(
            "SELECT * FROM rules WHERE rule_id = ?", (issue["rule_id"],)
        ).fetchone()
        assert rule is not None  # validated against the rule table
        assert issue["clause_quote"] == rule["clause_text"]

    # 3. Revise the text (creator workflow).
    client.post(
        f"/drafts/{draft['id']}",
        data={
            "action": "revise",
            "title": "Launch page",
            "body": "We improve every season. Pricing may change at any time, and you can cancel whenever you like.",
            "content_type": "product page",
            "audience": "New visitors",
        },
    )
    db.commit()
    revised = db.execute("SELECT * FROM drafts WHERE id = ?", (draft["id"],)).fetchone()
    assert "improve every season" in revised["body"]
    assert revised["status"] == "draft"

    # 4. Send for review.
    client.post(f"/drafts/{draft['id']}", data={"action": "submit"})
    db.commit()
    submitted = db.execute(
        "SELECT status FROM drafts WHERE id = ?", (draft["id"],)
    ).fetchone()
    assert submitted["status"] == "submitted"


# --- creator -> reviewer -> creator round trip --------------------------------


def test_reviewer_records_decision_with_time_and_reviewer(client, db):
    choose_role(client, "creator")
    draft_id = _create_and_submit(client, "Review me")

    # Switch straight to the reviewer (no password step).
    choose_role(client, "reviewer")

    queue = client.get("/review/")
    assert queue.status_code == 200
    assert b"Review me" in queue.data

    response = client.post(
        f"/review/{draft_id}",
        data={"decision": "needs_changes", "comment": "Please soften the opening."},
        follow_redirects=True,
    )
    assert response.status_code == 200

    decision = db.execute(
        "SELECT * FROM decisions WHERE draft_id = ? ORDER BY id DESC LIMIT 1",
        (draft_id,),
    ).fetchone()
    assert decision is not None
    assert decision["decision"] == "needs_changes"
    assert decision["comment"] == "Please soften the opening."
    assert decision["created_at"]  # time of decision stored
    reviewer = db.execute(
        "SELECT * FROM users WHERE id = ?", (decision["reviewer_id"],)
    ).fetchone()
    assert reviewer["role"] == "reviewer"
    draft = db.execute("SELECT * FROM drafts WHERE id = ?", (draft_id,)).fetchone()
    assert draft["status"] == "changes_requested"

    # Invalid decision values are rejected without recording anything.
    count_before = db.execute("SELECT COUNT(*) AS c FROM decisions").fetchone()["c"]
    client.post(f"/review/{draft_id}", data={"decision": "whatever"}, follow_redirects=True)
    db.commit()
    count_after = db.execute("SELECT COUNT(*) AS c FROM decisions").fetchone()["c"]
    assert count_after == count_before


def test_creator_sees_decision_and_draft_is_final(client, db):
    choose_role(client, "creator")
    draft_id = _create_and_submit(client, "Round trip")

    choose_role(client, "reviewer")
    client.post(f"/review/{draft_id}", data={"decision": "approved"})

    choose_role(client, "creator")
    page = client.get(f"/drafts/{draft_id}")
    assert page.status_code == 200
    # The creator sees the reviewer's decision and who recorded it.
    assert b"Approved" in page.data
    assert b"Demo Reviewer" in page.data

    draft = db.execute("SELECT * FROM drafts WHERE id = ?", (draft_id,)).fetchone()
    assert draft["status"] == "approved"


# --- guard rails --------------------------------------------------------------


def test_cannot_submit_a_draft_that_is_already_submitted(client, db):
    choose_role(client, "creator")
    draft_id = _create_and_submit(client, "Double submit")
    client.post(f"/drafts/{draft_id}", data={"action": "submit"})
    db.commit()
    draft = db.execute("SELECT * FROM drafts WHERE id = ?", (draft_id,)).fetchone()
    assert draft["status"] == "submitted"  # unchanged, no error


def test_reviewer_cannot_decide_on_a_draft_that_is_not_submitted(client, db):
    choose_role(client, "creator")
    _create_draft(client, title="Still editing")  # stays in 'draft'
    draft_id = db_id_from_response(client, "Still editing")

    choose_role(client, "reviewer")
    client.post(
        f"/review/{draft_id}", data={"decision": "approved"}, follow_redirects=True
    )
    db.commit()
    draft = db.execute("SELECT * FROM drafts WHERE id = ?", (draft_id,)).fetchone()
    assert draft["status"] == "draft"
    decisions = db.execute(
        "SELECT * FROM decisions WHERE draft_id = ?", (draft_id,)
    ).fetchall()
    assert decisions == []


def test_creator_sees_only_their_own_drafts(client, db):
    """Other creators' drafts 404 (authorship is enforced server-side)."""
    from inkloom.auth import NO_PASSWORD
    from inkloom.db import utcnow

    # A second creator with one draft.
    cur = db.execute(
        """INSERT INTO users (email, display_name, password_hash, role, created_at)
           VALUES (?, ?, ?, 'creator', ?)""",
        ("other@inkloom.test", "Other Creator", NO_PASSWORD, utcnow()),
    )
    db.execute(
        """INSERT INTO drafts (title, body, content_type, audience, author_id,
                               status, created_at, updated_at)
           VALUES ('Private', 'Body', 'email', 'Internal', ?, 'draft', ?, ?)""",
        (cur.lastrowid, utcnow(), utcnow()),
    )
    db.commit()
    other_id = db.execute(
        "SELECT id FROM drafts WHERE title = 'Private'"
    ).fetchone()["id"]

    choose_role(client, "creator")
    assert client.get(f"/drafts/{other_id}").status_code == 404
    listing = client.get("/drafts/")
    assert b"Private" not in listing.data
