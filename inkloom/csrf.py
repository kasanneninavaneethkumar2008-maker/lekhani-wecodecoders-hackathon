"""Lightweight CSRF protection for Lekhani state-changing requests.

Implements two complementary defenses without external dependencies:
1. Origin / Referer validation against the request host for all state-changing
   methods (POST, PUT, DELETE, PATCH).
2. Session-bound synchronizer CSRF tokens (`session["_csrf_token"]`), verified
   via form data (`csrf_token`), JSON body (`csrf_token`), or header (`X-CSRF-Token`).

In test mode (`app.config["TESTING"] == True`), CSRF verification is skipped
by default unless explicitly enabled via `CSRF_ENABLED=True` (matching standard
Flask-WTF behavior), allowing unit tests to run without boilerplate while
verifying CSRF protection in dedicated tests.
"""
import hmac
import secrets
from urllib.parse import urlparse

from flask import abort, current_app, request, session

SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}


def generate_csrf_token() -> str:
    """Return the current session's CSRF token, generating one if absent."""
    token = session.get("_csrf_token")
    if not token or not isinstance(token, str):
        token = secrets.token_hex(32)
        session["_csrf_token"] = token
    return token


def _same_origin(origin: str, host: str) -> bool:
    """Return whether origin matches the current request host."""
    try:
        parsed = urlparse(origin)
        origin_host = parsed.netloc or parsed.path
        return origin_host.casefold() == host.casefold()
    except Exception:
        return False


def validate_csrf():
    """Verify Origin and session CSRF token on state-changing requests."""
    if request.method in SAFE_METHODS:
        return

    # Skip in test mode unless explicitly enabled
    csrf_enabled = current_app.config.get(
        "CSRF_ENABLED", not current_app.config.get("TESTING", False)
    )
    if not csrf_enabled:
        return

    # 1. Check Origin / Referer if present
    host = request.host
    origin = request.headers.get("Origin")
    if origin and not _same_origin(origin, host):
        abort(403)

    referer = request.headers.get("Referer")
    if not origin and referer and not _same_origin(referer, host):
        abort(403)

    # 2. Check session token
    expected = session.get("_csrf_token")
    if not expected or not isinstance(expected, str):
        abort(403)

    received = (
        request.form.get("csrf_token")
        or request.headers.get("X-CSRF-Token")
        or (request.is_json and (request.get_json(silent=True) or {}).get("csrf_token"))
    )

    if not received or not isinstance(received, str):
        abort(403)

    if not hmac.compare_digest(received, expected):
        abort(403)


def init_csrf(app):
    """Register CSRF validation and template helpers with the Flask app."""
    app.before_request(validate_csrf)

    @app.context_processor
    def inject_csrf():
        return {"csrf_token": generate_csrf_token}
