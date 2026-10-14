"""Engine and session factory construction."""

from __future__ import annotations

from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from digital_workshop.db.orm import Base


def create_db_engine(database_url: str) -> Engine:
    """Create an engine and make sure all tables exist.

    In-memory SQLite URLs (used by tests) share a single connection.
    """
    url = make_url(database_url)
    if url.get_backend_name() == "sqlite" and url.database in (None, "", ":memory:"):
        engine = create_engine(url, connect_args={"check_same_thread": False}, poolclass=StaticPool)
    else:
        engine = create_engine(url, pool_pre_ping=True)
    Base.metadata.create_all(engine)
    _upgrade_connection_segments(engine)
    return engine


def _upgrade_connection_segments(engine: Engine) -> None:
    """Add the optional geometry column to databases created by earlier versions."""
    inspector = inspect(engine)
    if inspector.has_table("dxf_objects") and "connection_segments" not in {
        column["name"] for column in inspector.get_columns("dxf_objects")
    }:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE dxf_objects ADD COLUMN connection_segments JSON"))


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Return a session factory bound to ``engine``."""
    return sessionmaker(bind=engine, expire_on_commit=False)
