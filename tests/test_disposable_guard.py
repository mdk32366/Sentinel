"""Day-One Step 12 / ORDER-01 A4 — prove the positive-identity guard.

Runs entirely on in-memory SQLite: no network, no live service, no credentials.
The guard is exercised against databases this test builds and throws away, so
the proof is deterministic and costs nothing.

What is deliberately NOT tested here: pointing the suite at the real production
cluster through a tunnel. That is the case the guard exists for and it cannot be
rehearsed in CI without production credentials, which is precisely what must
never be in a test environment. The offline cases below establish that identity
is read from the database rather than inferred from an address, which is the
property that makes the tunnel case safe.
"""
import unittest

from sqlalchemy import create_engine, text

from database import connection
from database.connection import (
    CANARY_MARKER,
    CANARY_TABLE,
    NotADisposableDatabase,
    assert_disposable,
)


def _engine(marker=None, with_table=True):
    """A throwaway SQLite database, optionally carrying a canary."""
    engine = create_engine("sqlite:///:memory:")
    if with_table:
        with engine.connect() as conn:
            conn.execute(
                text(f"CREATE TABLE {CANARY_TABLE} (marker varchar(64))")
            )
            if marker is not None:
                conn.execute(
                    text(f"INSERT INTO {CANARY_TABLE} (marker) VALUES (:m)"),
                    {"m": marker},
                )
            conn.commit()
    return engine


class TestDisposableGuard(unittest.TestCase):
    def test_passes_when_canary_present(self):
        """A correct implementation and a broken one must differ HERE."""
        assert_disposable(_engine(marker=CANARY_MARKER))

    def test_refuses_when_canary_table_absent(self):
        """Production has no canary table. This is the production case."""
        with self.assertRaises(NotADisposableDatabase) as caught:
            assert_disposable(_engine(with_table=False))
        self.assertIn(CANARY_TABLE, str(caught.exception))

    def test_refuses_when_canary_empty(self):
        """Table present but unmarked is not an identification."""
        with self.assertRaises(NotADisposableDatabase):
            assert_disposable(_engine(marker=None))

    def test_refuses_on_wrong_marker(self):
        """A table called canary proves nothing; the marker is the identity."""
        with self.assertRaises(NotADisposableDatabase) as caught:
            assert_disposable(_engine(marker="something-else"))
        self.assertIn(CANARY_MARKER, str(caught.exception))

    def test_refusal_is_an_error_not_a_skip(self):
        """A guard that stands aside is not a guard (Principle 6)."""
        self.assertTrue(issubclass(NotADisposableDatabase, RuntimeError))

    def test_get_session_is_actually_wired_to_the_guard(self):
        """The helper being correct is not the same as the suite being guarded.

        Points the module engine at a canary-less database and asks for a
        session the way a fixture would.
        """
        original = connection.engine
        connection.engine = _engine(with_table=False)
        try:
            with self.assertRaises(NotADisposableDatabase):
                connection.get_session()
        finally:
            connection.engine = original

    def test_guard_is_armed_by_importing_the_test_package(self):
        """tests/__init__.py sets the marker, so no entry point bypasses it."""
        import os

        self.assertEqual(os.environ.get("SENTINEL_TEST_RUN"), "1")


if __name__ == "__main__":
    unittest.main()
