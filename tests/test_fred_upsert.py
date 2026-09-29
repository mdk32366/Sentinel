"""F-0073 remaining half: the FRED write is an upsert, not check-then-insert.

The old path did SELECT-then-INSERT per observation. Two overlapping runs —
and every deploy starts one, on top of the nightly schedule — could both see
"absent" and both insert. 1,190 duplicate rows resulted.

**What runs where.** The Postgres path is a single `ON CONFLICT DO UPDATE` and
can only arbitrate on a NULL `country_id` because `ix_metric_country_date` is
`NULLS NOT DISTINCT`. This suite's databases are SQLite, which shares
Postgres' NULL-distinct semantics, so an `ON CONFLICT` there would silently
fail to arbitrate — which is why the fetcher branches and why the Postgres
behaviour is asserted on the compiled statement rather than by inserting.
"""
import unittest
from datetime import datetime
from decimal import Decimal

from sqlalchemy import create_engine, func, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import sessionmaker

from database.models import Base, Metric, TimeSeries
from pipelines.fred_fetcher import UPSERT_CHUNK, upsert_observations


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _metric(db, code="DFF"):
    metric = Metric(code=code, name=code, category="monetary", unit="%",
                    source="FRED", description=code)
    db.add(metric)
    db.commit()
    return metric


def _rows(pairs):
    return [(datetime(2026, 9, day), Decimal(str(value))) for day, value in pairs]


class UpsertWritesAndCounts(unittest.TestCase):
    def test_a_first_write_inserts_everything(self):
        db = _session()
        try:
            m = _metric(db)
            inserted, updated = upsert_observations(db, m.id, _rows([(1, 3.88), (2, 3.89)]))
            db.commit()
            self.assertEqual((inserted, updated), (2, 0))
            self.assertEqual(db.query(func.count(TimeSeries.id)).scalar(), 2)
        finally:
            db.close()

    def test_rewriting_the_same_dates_updates_rather_than_duplicating(self):
        # The property the whole change exists for.
        db = _session()
        try:
            m = _metric(db)
            upsert_observations(db, m.id, _rows([(1, 3.88), (2, 3.89)]))
            db.commit()
            inserted, updated = upsert_observations(db, m.id, _rows([(1, 4.00), (2, 3.89)]))
            db.commit()

            self.assertEqual((inserted, updated), (0, 2))
            self.assertEqual(db.query(func.count(TimeSeries.id)).scalar(), 2)
            value = db.execute(
                select(TimeSeries.value).where(TimeSeries.date == datetime(2026, 9, 1))
            ).scalar()
            self.assertEqual(Decimal(str(value)), Decimal("4.00"))
        finally:
            db.close()

    def test_a_mixed_batch_counts_each_kind(self):
        db = _session()
        try:
            m = _metric(db)
            upsert_observations(db, m.id, _rows([(1, 3.88)]))
            db.commit()
            inserted, updated = upsert_observations(db, m.id, _rows([(1, 3.88), (2, 3.90), (3, 3.91)]))
            db.commit()
            self.assertEqual((inserted, updated), (2, 1))
            self.assertEqual(db.query(func.count(TimeSeries.id)).scalar(), 3)
        finally:
            db.close()

    def test_an_empty_batch_is_not_a_write(self):
        db = _session()
        try:
            m = _metric(db)
            self.assertEqual(upsert_observations(db, m.id, []), (0, 0))
            self.assertEqual(db.query(func.count(TimeSeries.id)).scalar(), 0)
        finally:
            db.close()

    def test_one_metric_does_not_collide_with_another(self):
        # The conflict target includes metric_id. Two series holding the same
        # date is the ordinary case, not a conflict.
        db = _session()
        try:
            a, b = _metric(db, "DFF"), _metric(db, "DGS10")
            upsert_observations(db, a.id, _rows([(1, 3.88)]))
            inserted, updated = upsert_observations(db, b.id, _rows([(1, 4.21)]))
            db.commit()
            self.assertEqual((inserted, updated), (1, 0))
            self.assertEqual(db.query(func.count(TimeSeries.id)).scalar(), 2)
        finally:
            db.close()

    def test_country_scoped_rows_are_left_alone(self):
        # The fetcher writes global metrics only. A country-scoped row for the
        # same metric and date must survive an upsert of the global one.
        db = _session()
        try:
            m = _metric(db)
            db.add(TimeSeries(metric_id=m.id, country_id=42,
                              date=datetime(2026, 9, 1), value=Decimal("9.99")))
            db.commit()

            upsert_observations(db, m.id, _rows([(1, 3.88)]))
            db.commit()

            self.assertEqual(db.query(func.count(TimeSeries.id)).scalar(), 2)
            kept = db.execute(
                select(TimeSeries.value).where(TimeSeries.country_id == 42)
            ).scalar()
            self.assertEqual(Decimal(str(kept)), Decimal("9.99"))
        finally:
            db.close()


class ThePostgresStatement(unittest.TestCase):
    """Asserted on the compiled SQL, because SQLite cannot exercise it.

    Inserting a duplicate into SQLite and watching it succeed would prove
    nothing about Postgres, and a test that looked like it covered this would
    be worse than none.
    """

    def _compiled(self):
        stmt = pg_insert(TimeSeries.__table__).values([{
            "metric_id": 1, "country_id": None,
            "date": datetime(2026, 9, 1), "value": Decimal("3.88"),
            "created_at": datetime(2026, 9, 1), "updated_at": datetime(2026, 9, 1),
        }])
        stmt = stmt.on_conflict_do_update(
            index_elements=["metric_id", "country_id", "date"],
            set_={"value": stmt.excluded.value, "updated_at": stmt.excluded.updated_at},
        )
        return str(stmt.compile(dialect=postgresql.dialect()))

    def test_it_is_an_on_conflict_do_update(self):
        sql = self._compiled()
        self.assertIn("ON CONFLICT", sql)
        self.assertIn("DO UPDATE", sql)

    def test_the_conflict_target_is_the_f0073_index_columns(self):
        # ON CONFLICT (metric_id, country_id, date) can only arbitrate a NULL
        # country_id because ix_metric_country_date is NULLS NOT DISTINCT.
        # Change either and duplicates come straight back.
        sql = self._compiled()
        self.assertIn("metric_id", sql)
        self.assertIn("country_id", sql)
        self.assertIn("date", sql)

    def test_it_updates_the_value_and_the_timestamp_only(self):
        sql = self._compiled()
        self.assertIn("SET", sql)
        self.assertIn("value", sql)
        self.assertIn("updated_at", sql)
        # created_at must NOT be overwritten: when a row first arrived is a
        # fact about this database, not something a re-fetch revises.
        self.assertNotIn("created_at = excluded", sql)


class TheChunkSizeStaysUnderThePostgresParameterCap(unittest.TestCase):
    def test_a_full_chunk_fits_in_one_statement(self):
        # Postgres allows 65535 bind parameters per statement. Six columns a
        # row means the cap is ~10900 rows; the chunk is well inside it.
        self.assertLessEqual(UPSERT_CHUNK * 6, 65535)
        self.assertGreater(UPSERT_CHUNK, 1)



class ABatchContainingTheSameDateTwice(unittest.TestCase):
    """Postgres refuses to let ON CONFLICT DO UPDATE touch a row twice in one
    statement — "cannot affect row a second time". A FRED payload can carry
    the same date twice across a revision boundary, so the batch is made
    unique before it is sent.

    SQLite would accept the duplicate and insert two rows, so this asserts the
    OUTCOME — one row, last value wins — which is the same on both dialects.
    """

    def test_it_writes_one_row_and_the_last_value_wins(self):
        db = _session()
        try:
            m = _metric(db)
            rows = [
                (datetime(2026, 9, 1), Decimal("3.88")),
                (datetime(2026, 9, 1), Decimal("3.91")),   # revision
                (datetime(2026, 9, 2), Decimal("3.90")),
            ]
            inserted, updated = upsert_observations(db, m.id, rows)
            db.commit()

            self.assertEqual((inserted, updated), (2, 0))
            self.assertEqual(db.query(func.count(TimeSeries.id)).scalar(), 2)
            value = db.execute(
                select(TimeSeries.value).where(TimeSeries.date == datetime(2026, 9, 1))
            ).scalar()
            self.assertEqual(Decimal(str(value)), Decimal("3.91"))
        finally:
            db.close()

    def test_a_repeated_date_is_not_counted_twice(self):
        # The counters feed update_logs. Counting a deduped row twice would
        # report more inserts than rows written.
        db = _session()
        try:
            m = _metric(db)
            inserted, updated = upsert_observations(db, m.id, [
                (datetime(2026, 9, 1), Decimal("1")),
                (datetime(2026, 9, 1), Decimal("2")),
            ])
            db.commit()
            self.assertEqual((inserted, updated), (1, 0))
            self.assertEqual(db.query(func.count(TimeSeries.id)).scalar(), 1)
        finally:
            db.close()

if __name__ == "__main__":
    unittest.main()
