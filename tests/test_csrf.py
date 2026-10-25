"""Tests for Lekhani CSRF protection and Origin validation."""
import re
import pytest
from inkloom import create_app
from inkloom.db import init_db, get_db
from inkloom.seed import seed_all


@pytest.fixture
def csrf_app(tmp_path):
    """App fixture with CSRF protection explicitly enabled for testing."""
    app = create_app(
        {
            "TESTING": True,
            "CSRF_ENABLED": True,
            "SECRET_KEY": "csrf-test-secret",
            "DATABASE": str(tmp_path / "csrf_test.sqlite3"),
        }
    )
    with app.app_context():
        init_db()
        seed_all(get_db())
    return app


@pytest.fixture
def csrf_client(csrf_app):
    return csrf_app.test_client()


def extract_csrf_token(response_data: bytes) -> str:
    """Extract CSRF token from rendered HTML input or meta tag."""
    text = response_data.decode("utf-8")
    match = re.search(r'name="csrf_token"\s+value="([a-f0-9]{64})"', text)
    if match:
        return match.group(1)
    match_meta = re.search(r'<meta\s+name="csrf-token"\s+content="([a-f0-9]{64})"', text)
    if match_meta:
        return match_meta.group(1)
    return ""


def test_get_request_injects_csrf_token_in_session_and_page(csrf_client):
    response = csrf_client.get("/")
    assert response.status_code == 200
    token = extract_csrf_token(response.data)
    assert len(token) == 64
    with csrf_client.session_transaction() as sess:
        assert sess.get("_csrf_token") == token


def test_post_without_csrf_token_is_rejected_403(csrf_client):
    # Establish session first
    csrf_client.get("/")
    # Attempt POST without token
    response = csrf_client.post("/guest/login", data={"name": "Attacker"})
    assert response.status_code == 403


def test_post_with_invalid_csrf_token_is_rejected_403(csrf_client):
    csrf_client.get("/")
    response = csrf_client.post(
        "/guest/login",
        data={"name": "Attacker", "csrf_token": "a" * 64},
    )
    assert response.status_code == 403


def test_post_with_cross_origin_is_rejected_403(csrf_client):
    res = csrf_client.get("/")
    token = extract_csrf_token(res.data)
    response = csrf_client.post(
        "/guest/login",
        data={"name": "Victim", "csrf_token": token},
        headers={"Origin": "https://evil-attacker.example.com"},
    )
    assert response.status_code == 403


def test_post_with_cross_origin_referer_is_rejected_403(csrf_client):
    res = csrf_client.get("/")
    token = extract_csrf_token(res.data)
    response = csrf_client.post(
        "/guest/login",
        data={"name": "Victim", "csrf_token": token},
        headers={"Referer": "https://evil-attacker.example.com/phish"},
    )
    assert response.status_code == 403


def test_post_with_valid_token_and_same_origin_succeeds(csrf_client):
    res = csrf_client.get("/")
    token = extract_csrf_token(res.data)
    response = csrf_client.post(
        "/guest/login",
        data={"name": "Valid Guest", "csrf_token": token},
        headers={"Origin": "http://localhost"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/home")


def test_ajax_post_with_valid_csrf_header_succeeds(csrf_client):
    # Enter as guest
    res = csrf_client.get("/")
    token = extract_csrf_token(res.data)
    csrf_client.post(
        "/guest/login",
        data={"name": "Guest", "csrf_token": token},
        headers={"Origin": "http://localhost"},
    )

    # Workspace page loads with CSRF token
    ws_res = csrf_client.get("/workspace")
    assert ws_res.status_code == 200
    ws_token = extract_csrf_token(ws_res.data)
    assert len(ws_token) == 64

    # Fetch request with X-CSRF-Token header
    from inkloom.workbench import fingerprint
    text = "We will disrupt routines."
    fp = fingerprint(text)
    ajax_res = csrf_client.post(
        "/workspace/replace",
        json={
            "body": text,
            "rule_id": "GLS-001",
            "start": 8,
            "end": 15,
            "content_type": "website copy",
            "rule_mode": "workspace",
            "check_fingerprint": fp,
        },
        headers={
            "X-CSRF-Token": ws_token,
            "Origin": "http://localhost",
        },
    )
    assert ajax_res.status_code == 200
    assert ajax_res.json["ok"] is True
    assert ajax_res.json["body"] == "We will change routines."


def test_safe_methods_are_exempt(csrf_client):
    for method in ("get", "head", "options"):
        fn = getattr(csrf_client, method)
        response = fn("/")
        assert response.status_code in (200, 405)
