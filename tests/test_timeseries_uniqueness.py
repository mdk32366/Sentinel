"""F-0073: the unique index on timeseries must actually constrain macro series.

`ix_metric_country_date` was UNIQUE on `(metric_id, country_id, date)` and
never rejected a duplicate for any series with `country_id IS NULL` — which is
every macro series — because Postgres treats NULLs as DISTINCT in a unique
index. 1,190 duplicates had accumulated across six metrics before anyone
looked at it.

**What this file can and cannot prove.** SQLite shares Postgres' default NULL
semantics and ignores the `postgresql_` dialect kwarg, so an in-memory test
database does not enforce the constraint and inserting a duplicate into one
proves nothing either way. What is checkable here is the DDL the model emits,
which is what `create_all()` runs against a real database — so a fresh
deployment cannot silently get the old semantics back.

The runtime behaviour was verified directly against production on 2026-09-29:

    RESULT: rejected -> IntegrityError
            duplicate key value violates unique constraint "ix_metric_country_date"
    COUNTRY-SCOPED: still rejected -> IntegrityError
"""
import unittest

from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.schema import CreateIndex

from database.models import TimeSeries


def _index(name):
    for item in TimeSeries.__table__.indexes:
        if item.name == name:
            return item
    raise AssertionError(f"index {name} is not declared on timeseries")


def _postgres_ddl(index):
    return str(CreateIndex(index).compile(dialect=postgresql.dialect()))


class TheUniqueIndexIsDeclared(unittest.TestCase):
    def test_it_exists_and_is_unique(self):
        index = _index("ix_metric_country_date")
        self.assertTrue(index.unique)
        self.assertEqual(
            [c.name for c in index.columns],
            ["metric_id", "country_id", "date"],
        )


class TheUniqueIndexBindsOnNulls(unittest.TestCase):
    def test_the_emitted_postgres_ddl_says_nulls_not_distinct(self):
        # The whole finding, in one assertion. Without this clause the index
        # is decoration for every country-less series.
        self.assertIn("NULLS NOT DISTINCT", _postgres_ddl(_index("ix_metric_country_date")))

    def test_the_clause_survives_a_rename_or_reorder(self):
        # Asserted on the compiled DDL rather than on the kwarg dict, because
        # what matters is the statement create_all() actually runs.
        ddl = _postgres_ddl(_index("ix_metric_country_date"))
        self.assertIn("CREATE UNIQUE INDEX", ddl)
        self.assertIn("metric_id", ddl)
        self.assertIn("country_id", ddl)
        self.assertIn("date", ddl)

    def test_sqlite_drops_the_clause_rather_than_failing(self):
        # Stated so nobody discovers it as a surprise: the test databases in
        # this suite do NOT enforce this constraint. A test that inserted a
        # duplicate into SQLite and passed would be proving the opposite of
        # what it claimed.
        ddl = str(CreateIndex(_index("ix_metric_country_date")).compile(dialect=sqlite.dialect()))
        self.assertIn("CREATE UNIQUE INDEX", ddl)
        self.assertNotIn("NULLS NOT DISTINCT", ddl)


class TheOtherIndexesAreNotUnique(unittest.TestCase):
    def test_lookup_indexes_stay_non_unique(self):
        # ix_metric_date would reject a legitimate row: two countries can hold
        # the same metric on the same date.
        for name in ("ix_metric_date", "ix_country_date"):
            with self.subTest(index=name):
                self.assertFalse(_index(name).unique)


if __name__ == "__main__":
    unittest.main()
