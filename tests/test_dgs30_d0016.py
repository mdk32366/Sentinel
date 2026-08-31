"""D-0016: DGS30 ingest and display, not a v2 factor.

T-0015 / T-0016 are meant to go red if DGS30 is missing from FRED_METRICS
or if calculate_yield_curve_stress starts reading a 30Y level.
"""
import unittest
from datetime import datetime
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.models import Base, Metric, TimeSeries
from pipelines.fred_fetcher import FRED_METRICS
from pipelines.stress_score_v2 import calculate_yield_curve_stress


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _add_series(db, code, name, value, date=None):
    metric = Metric(
        code=code,
        name=name,
        category="treasury",
        unit="%",
        source="FRED",
        description=name,
    )
    db.add(metric)
    db.flush()
    db.add(
        TimeSeries(
            metric_id=metric.id,
            country_id=None,
            date=date or datetime(2026, 8, 31),
            value=Decimal(str(value)),
        )
    )
    db.commit()
    return metric


class T0015FredMetricsDgs30(unittest.TestCase):
    def test_t0015_dgs30_is_first_treasury_row(self):
        dgs30 = next((m for m in FRED_METRICS if m["code"] == "DGS30"), None)
        self.assertIsNotNone(dgs30, "FRED_METRICS is missing DGS30")
        self.assertEqual(dgs30["category"], "treasury")

        treasury = [m for m in FRED_METRICS if m.get("category") == "treasury"]
        self.assertGreaterEqual(len(treasury), 1)
        self.assertEqual(treasury[0]["code"], "DGS30")
        self.assertEqual(treasury[0]["category"], "treasury")


class T0016YieldCurveIgnoresDgs30(unittest.TestCase):
    def test_t0016_score_identical_with_and_without_dgs30_5_3(self):
        db = _session()
        try:
            _add_series(db, "DGS10", "10-Year Treasury Yield", 4.2)
            _add_series(db, "DGS2", "2-Year Treasury Yield", 3.6)

            without = calculate_yield_curve_stress(db)
            self.assertNotEqual(without, (0.0, 0.0))

            _add_series(db, "DGS30", "30-Year Treasury Yield", 5.3)
            with_dgs30 = calculate_yield_curve_stress(db)

            self.assertEqual(without, with_dgs30)
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
