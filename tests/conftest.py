import pytest

from inkloom import create_app
from inkloom.db import get_db, init_db
from inkloom.seed import seed_all


@pytest.fixture
def app(tmp_path):
    app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-secret",
            "DATABASE": str(tmp_path / "test.sqlite3"),
        }
    )
    with app.app_context():
        init_db()
        seed_all(get_db())
    yield app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def db(app):
    with app.app_context():
        yield get_db()


def choose_role(client, role):
    """Pick a demo role (the app's no-password entry flow)."""
    return client.post(
        "/continue",
        data={"role": role},
        follow_redirects=True,
    )
