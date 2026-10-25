"""Database access helpers for Inkloom AI (Flask + sqlite3)."""
import os
import sqlite3
from datetime import datetime, timezone

import click
from flask import current_app, g


def utcnow() -> str:
    """Current UTC time as an ISO-8601 string (second precision)."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = sqlite3.connect(
            current_app.config["DATABASE"],
            detect_types=sqlite3.PARSE_DECLTYPES,
        )
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    """Create the schema from schema.sql (destructive: recreates tables)."""
    db = get_db()
    with current_app.open_resource("schema.sql") as f:
        db.executescript(f.read().decode("utf-8"))


@click.command("init-db")
def init_db_command():
    """Create the schema (recreates all tables; discards existing data)."""
    init_db()
    click.echo("Initialized the database.")


@click.command("seed")
def seed_command():
    """Load the fictional sample rules (no users, no drafts)."""
    from .seed import seed_all

    seed_all(get_db())
    click.echo("Loaded the fictional sample rules (no users, no drafts).")


def init_app(app):
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
    app.cli.add_command(seed_command)
