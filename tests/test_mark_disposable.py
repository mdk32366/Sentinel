"""F-0111 — tools/mark_disposable.py could not mark a fresh Postgres database.

Two defects, found running it for the auction-demand backfill on 2026-10-08:

1. It probed for the canary with `SELECT marker FROM canary` and swallowed the
   error when the table did not exist. Postgres aborts the whole transaction on
   any error, so the `CREATE TABLE` that followed failed with "current
   transaction is aborted". Every fresh database - the only kind that needs
   marking - hit it.
2. `python tools/mark_disposable.py`, the command its own docstring gives,
   failed with "No module named 'config'": a script's sys.path starts at
   `tools/`, not the repo root.

SQLite does not abort a transaction on error, so the suite's databases could
never show defect 1. The engine here is SQLite made to behave like Postgres:
after any failed statement, every further statement fails until a rollback.
"""
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

from sqlalchemy import create_engine, event, text
from sqlalchemy.pool import StaticPool

from database.connection import CANARY_MARKER, CANARY_TABLE
from database.models import Base

ROOT = Path(__file__).resolve().parents[1]


def postgres_like_engine():
    """SQLite that refuses every statement after an error, until rollback."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    state = {"aborted": False, "errors": []}

    @event.listens_for(engine, "connect")
    def _functions(dbapi_conn, _):
        dbapi_conn.create_function("current_database", 0, lambda: "scratch")

    @event.listens_for(engine, "handle_error")
    def _abort(ctx):
        state["errors"].append(str(ctx.original_exception))
        state["aborted"] = True

    @event.listens_for(engine, "before_cursor_execute")
    def _refuse(conn, cursor, statement, *args):
        if state["aborted"]:
            raise RuntimeError(
                "current transaction is aborted, commands ignored until end of "
                f"transaction block: {statement[:60]}"
            )

    @event.listens_for(engine, "rollback")
    def _reset(conn):
        state["aborted"] = False

    Base.metadata.create_all(engine)
    return engine, state


class AFreshDatabaseCanBeMarked(unittest.TestCase):
    def run_tool(self, engine, typed="scratch", argv=()):
        from tools import mark_disposable

        with mock.patch.object(mark_disposable, "create_engine", return_value=engine), \
             mock.patch("builtins.input", return_value=typed), \
             mock.patch.object(sys, "argv", ["mark_disposable.py", *argv]), \
             mock.patch("builtins.print"):
            try:
                return mark_disposable.main()
            except Exception as e:  # the defect; reported as a failure, not an error
                self.fail(f"mark_disposable raised on a fresh database: {e}")

    def canary(self, engine):
        with engine.connect() as conn:
            return conn.execute(text(f"SELECT marker FROM {CANARY_TABLE}")).scalar()

    def test_the_probe_causes_no_failed_statement(self):
        engine, state = postgres_like_engine()
        self.assertEqual(self.run_tool(engine, argv=["--show"]), 0)
        self.assertEqual(state["errors"], [], "a failed statement aborts a Postgres transaction")

    def test_a_fresh_database_is_marked(self):
        engine, state = postgres_like_engine()
        self.assertEqual(self.run_tool(engine), 0)
        self.assertEqual(self.canary(engine), CANARY_MARKER)
        self.assertEqual(state["errors"], [])

    def test_marking_twice_is_a_no_op(self):
        engine, _ = postgres_like_engine()
        self.run_tool(engine)
        self.assertEqual(self.run_tool(engine), 0)
        self.assertEqual(self.canary(engine), CANARY_MARKER)

    def test_a_wrong_name_writes_nothing(self):
        engine, _ = postgres_like_engine()
        self.assertEqual(self.run_tool(engine, typed="production"), 1)
        with engine.connect() as conn:
            exists = conn.execute(text(
                "SELECT count(*) FROM sqlite_master WHERE name = :t"
            ), {"t": CANARY_TABLE}).scalar()
        self.assertEqual(exists, 0)


class TheDocumentedCommandRuns(unittest.TestCase):
    def test_python_tools_mark_disposable_imports_from_the_repo_root(self):
        result = subprocess.run(
            [sys.executable, "tools/mark_disposable.py", "--help"],
            cwd=ROOT, capture_output=True, text=True, env=dict(os.environ),
        )
        self.assertNotIn("No module named", result.stderr)
        self.assertEqual(result.returncode, 0, result.stderr[-400:])


if __name__ == "__main__":
    unittest.main()
