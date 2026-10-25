"""Inkloom AI -- Flask application factory."""
import os

from flask import Flask, render_template

from . import auth, guest
from .csrf import init_csrf
from .db import init_app as init_db_app


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("INKLOOM_SECRET_KEY", "dev-only-change-me"),
        DATABASE=os.path.join(app.instance_path, "inkloom.sqlite3"),
        # Keep Werkzeug's default scrypt hashing cost (do not weaken).
    )
    if test_config is None:
        app.config.from_pyfile("config.py", silent=True)
    else:
        app.config.from_mapping(test_config)

    os.makedirs(app.instance_path, exist_ok=True)

    init_db_app(app)
    init_csrf(app)
    app.register_blueprint(auth.bp)
    app.register_blueprint(guest.bp)

    from . import site

    app.register_blueprint(site.bp)

    from . import creator, reviewer

    app.register_blueprint(creator.bp)
    app.register_blueprint(reviewer.bp)

    @app.route("/")
    def index():
        """Guest entry: the Lekhani welcome page."""
        return render_template("index.html", roles=auth.ROLES)

    @app.errorhandler(403)
    def forbidden(e):
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def not_found(e):
        return render_template("errors/404.html"), 404

    return app
