"""F-0133 — the WGC monthly CSV must not replace the daily spot series.

D-0094 writes GOLD_SPOT_USD from gold-api.com, dated by the provider's
updatedAt. The World Bank Pink Sheet is the monthly fallback. The WGC file
importer is an older path onto the same metric: it normalises a month-end
date to day 1 and used to overwrite whatever was stored there.

These fixtures are synthetic. They do not read data/gold_prices.csv and they
do not carry a published gold price.
"""
import csv
import tempfile
import unittest
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.models import Base, TimeSeries, UpdateLog
from pipelines import gold_price_fetcher as gpf
from pipelines.gold_price_import import (
    ensure_spot_metric,
    import_gold_price_csv,
    run_gold_price_import,
)


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _month(months_back):
    """Day-1 of a month recent enough that the 70-day guard stays quiet.

    Previous month is at most about 62 days old on day 1. Two months back
    can pass 70, so callers stay inside 0 and 1.
    """
    now = datetime.utcnow()
    year, month = now.year, now.month - months_back
    while month <= 0:
        month += 12
        year -= 1
    return datetime(year, month, 1), f"{month}/28/{year}"


def _csv(path, rows):
    """rows: (m/d/yyyy, usd text). USD is column 3, matching the WGC layout."""
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["", "", "Date", "USD", "EUR"])
        writer.writerow([
            "", "",
            "Source: Bloomberg, Datastream, ICE Benchmark Administration, "
            "Multi Commodity Exchange of India, World Gold Council",
            "", "",
        ])
        for date_str, usd in rows:
            writer.writerow(["", "", date_str, usd, "1.0"])
    return path


def _spot(db, metric, when, value):
    db.add(TimeSeries(
        metric_id=metric.id,
        country_id=None,
        date=when,
        value=Decimal(value),
    ))
    db.commit()


def _value(db, metric, when):
    row = db.query(TimeSeries).filter_by(
        metric_id=metric.id, date=when,
    ).one_or_none()
    return None if row is None else Decimal(str(row.value))


class TestWgcImporterDoesNotReplaceSpot(unittest.TestCase):
    def setUp(self):
        self.db = _session()
        self.addCleanup(self.db.close)
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)
        self.csv = Path(self._dir.name) / "gold_prices.csv"

    def test_a_daily_series_is_left_untouched(self):
        metric = ensure_spot_metric(self.db)
        current, label = _month(0)
        mid = current.replace(day=15)
        _spot(self.db, metric, mid, "2222.2")
        _csv(self.csv, [(label, "1,000.5")])

        before = self.db.query(TimeSeries).count()
        with self.assertRaises(ValueError) as caught:
            import_gold_price_csv(self.db, csv_path=self.csv)
        msg = str(caught.exception)
        self.assertIn("not on day 1", msg)
        self.assertIn("/api/fetch/gold-price", msg)
        self.assertIn("not a copyright ruling", msg)
        self.assertNotIn("1000.5", msg)
        self.assertEqual(self.db.query(TimeSeries).count(), before)
        self.assertEqual(_value(self.db, metric, mid), Decimal("2222.2"))
        self.assertIsNone(_value(self.db, metric, current))

    def test_a_different_day1_value_is_not_replaced(self):
        # A gold-api print can land on the 1st. That row is still a spot
        # observation. The monthly file must not change it, and must not
        # insert anything else on the same attempt.
        metric = ensure_spot_metric(self.db)
        current, current_label = _month(0)
        previous, previous_label = _month(1)
        _spot(self.db, metric, current, "3333.3")
        _csv(self.csv, [
            (previous_label, "1000.5"),
            (current_label, "4444.4"),
        ])

        with self.assertRaises(ValueError) as caught:
            import_gold_price_csv(self.db, csv_path=self.csv)
        self.assertIn("differs from a stored observation", str(caught.exception))
        self.assertEqual(_value(self.db, metric, current), Decimal("3333.3"))
        self.assertIsNone(_value(self.db, metric, previous))

    def test_an_identical_monthly_reread_may_append_a_missing_month(self):
        metric = ensure_spot_metric(self.db)
        current, current_label = _month(0)
        previous, previous_label = _month(1)
        _spot(self.db, metric, previous, "1000.5")
        _csv(self.csv, [
            (previous_label, "1,000.5"),
            (current_label, "1100.25"),
        ])

        result = import_gold_price_csv(self.db, csv_path=self.csv)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["series"], "GOLD_SPOT_USD")
        self.assertEqual(_value(self.db, metric, previous), Decimal("1000.5"))
        self.assertEqual(_value(self.db, metric, current), Decimal("1100.25"))
        self.assertGreaterEqual(result["inserted"], 1)

    def test_a_frozen_file_still_fails_closed_with_nothing_written(self):
        _csv(self.csv, [("1/31/2020", "1000.5")])
        with self.assertRaises(ValueError) as caught:
            import_gold_price_csv(self.db, csv_path=self.csv)
        self.assertIn("stale", str(caught.exception))
        self.assertEqual(self.db.query(TimeSeries).count(), 0)

    def test_run_logs_failure_and_does_not_commit_the_series(self):
        metric = ensure_spot_metric(self.db)
        current, label = _month(0)
        _spot(self.db, metric, current.replace(day=15), "2222.2")
        _csv(self.csv, [(label, "1000.5")])

        with patch(
            "pipelines.gold_price_import.CSV_PATH", self.csv
        ):
            with self.assertRaises(ValueError):
                run_gold_price_import(self.db)

        log = self.db.query(UpdateLog).filter_by(
            pipeline_name="Gold_Spot_Price"
        ).one()
        self.assertEqual(log.status, "failed")
        self.assertLessEqual(len(log.error_message), 500)
        self.assertIn("/api/fetch/gold-price", log.error_message)
        self.assertEqual(
            _value(self.db, metric, current.replace(day=15)),
            Decimal("2222.2"),
        )


class TestMonthlyFallbackDoesNotReplaceSpot(unittest.TestCase):
    def setUp(self):
        self.db = _session()
        self.addCleanup(self.db.close)

    def test_primary_may_revise_the_same_observation(self):
        metric = gpf.ensure_metric(self.db)
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        _spot(self.db, metric, today, "100.0")
        payload = {
            "price": 101.5,
            "updatedAt": today.strftime("%Y-%m-%dT12:00:00Z"),
            "symbol": "XAU",
        }
        with patch.object(gpf, "fetch_gold_api_json", return_value=payload):
            result = gpf.run_gold_price_fetch(self.db)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["source"], "gold-api.com")
        self.assertEqual(result["updated"], 1)
        self.assertEqual(_value(self.db, metric, today), Decimal("101.5"))
        self.assertEqual(result["latest_date"], today.date().isoformat())

    def test_fallback_inserts_a_gap_and_leaves_a_stored_day_unchanged(self):
        metric = gpf.ensure_metric(self.db)
        current, _label = _month(0)
        previous, _prev = _month(1)
        _spot(self.db, metric, current, "3333.3")
        monthly = [
            {"date": previous, "usd": Decimal("1000.5"), "source": "world-bank-pink-sheet"},
            {"date": current, "usd": Decimal("9999.9"), "source": "world-bank-pink-sheet"},
        ]

        def _boom():
            raise TimeoutError("primary down")

        with patch.object(gpf, "fetch_gold_api_json", side_effect=_boom), \
             patch.object(gpf, "fetch_world_bank_monthly", return_value=monthly):
            result = gpf.run_gold_price_fetch(self.db)

        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["source"], "world-bank-pink-sheet")
        self.assertEqual(result["inserted"], 1)
        self.assertEqual(result["updated"], 0)
        self.assertEqual(result["preserved"], 1)
        self.assertEqual(_value(self.db, metric, current), Decimal("3333.3"))
        self.assertEqual(_value(self.db, metric, previous), Decimal("1000.5"))
        self.assertIn("World Bank", result["attribution"])


if __name__ == "__main__":
    unittest.main()
