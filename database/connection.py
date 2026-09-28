import os

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool
from config import settings
from database.models import Base
import logging

logger = logging.getLogger(__name__)

# Create engine with connection pooling
engine = create_engine(
    settings.database_url,
    poolclass=QueuePool,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,  # Verify connections before using
    echo=False,  # Set to True for SQL logging
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# --------------------------------------------------------------------------
# Day-One Step 12 / ORDER-01 A4: positive-identity guard.
#
# A test suite is entitled to treat its database as disposable, so it must
# refuse to run against one that is not. "Disposable" is not a hostname and not
# a port: a tunnel to production is a localhost address, and a guard that reads
# the hostname is defeated by the infrastructure you are most likely running.
#
# Identity is positive: the database must carry a canary table that only a
# disposable database has, created by a deliberate act (tools/mark_disposable.py)
# and never by the application. Production has no canary and cannot grow one by
# running normally.
#
# The guard fires when a real session is requested WHILE A TEST RUN IS IN
# PROGRESS - tests/__init__.py sets SENTINEL_TEST_RUN. That keeps both halves of
# Step 12 true at once: the suite passes offline, because it uses SQLite and
# never asks for this session; and a real database is a hard error, even
# through a tunnel, because identity is checked rather than inferred.
#
# What it does not cover: it does not protect a script run outside the suite.
# Nothing here stops you pointing a pipeline at production - that is what
# pipelines are for. It protects the case where a test fixture reaches a
# database whose data is not expendable.
CANARY_TABLE = "canary"
CANARY_MARKER = "SENTINEL_DISPOSABLE"
_TEST_RUN_ENV = "SENTINEL_TEST_RUN"


class NotADisposableDatabase(RuntimeError):
    """Raised instead of touching a database that has not identified itself."""


def assert_disposable(bind) -> None:
    """Raise unless `bind` carries the canary. Takes an Engine or Connection so
    the guard itself can be tested against a throwaway SQLite database."""
    query = text(f"SELECT marker FROM {CANARY_TABLE} LIMIT 1")
    try:
        if hasattr(bind, "connect"):
            with bind.connect() as conn:
                marker = conn.execute(query).scalar()
        else:
            marker = bind.execute(query).scalar()
    except Exception as exc:
        raise NotADisposableDatabase(
            f"Refusing to run: could not read the '{CANARY_TABLE}' table "
            f"({type(exc).__name__}: {exc}). A test run may only touch a "
            f"database that has identified itself as disposable. If this "
            f"database IS disposable, run: python tools/mark_disposable.py"
        ) from exc

    if marker != CANARY_MARKER:
        raise NotADisposableDatabase(
            f"Refusing to run: '{CANARY_TABLE}.marker' is {marker!r}, expected "
            f"{CANARY_MARKER!r}. This database has not identified itself as "
            f"disposable."
        )


def _guard_if_test_run() -> None:
    if os.environ.get(_TEST_RUN_ENV) == "1":
        assert_disposable(engine)


def init_db():
    """Initialize database tables"""
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables created/verified")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise


def get_db() -> Session:
    """Get database session (for FastAPI dependency injection)"""
    _guard_if_test_run()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_session() -> Session:
    """Get a database session for scripts/pipelines"""
    _guard_if_test_run()
    return SessionLocal()
