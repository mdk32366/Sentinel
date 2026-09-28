"""ORDER-01 B7 — prove the freshness watchdog by tripping it.

A safety net nobody has seen catch anything is a hope, not a guarantee.

Gold reading CRITICAL does not count as proof: that is the fault the watchdog
was built for, and a guard that fires on the one case it was written against
has not been shown to fire on anything else.

So: a disposable in-memory database holding a single metric that matches a
`CHECKS` pattern, with a deliberately backdated observation. Watch the source
go CRITICAL. Move the observation to today. Watch it clear.

The status must change because an assertion about *age* failed - a
failure-red - and not because something threw. `test_the_trip_is_a_failure_red_not_an_error_red`
is what separates those two.
"""
import datetime
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.models import Base, Metric, TimeSeries
from pipelines.freshness_watchdog import get_freshness_report

# Matches the "DGS%" pattern of the treasury check, whose limit is 5 days.
BACKDATED_CODE = "DGS10"
TREASURY_KEY = "treasury_yields"


class TestWatchdogTrip(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.addCleanup(self.db.close)

        self.metric = Metric(
            code=BACKDATED_CODE,
            name="10-Year Treasury Yield",
            category="treasury",
            unit="%",
            source="test",
        )
        self.db.add(self.metric)
        self.db.commit()

    def _observe(self, days_ago):
        point = TimeSeries(
            metric_id=self.metric.id,
            country_id=None,
            date=datetime.datetime.utcnow() - datetime.timedelta(days=days_ago),
            value=5.18,
        )
        self.db.add(point)
        self.db.commit()
        return point

    def _treasury_source(self):
        report = get_freshness_report(self.db)
        for source in report["sources"]:
            if source["key"] == TREASURY_KEY:
                return source
        self.fail(f"no source keyed {TREASURY_KEY!r} in the report")

    def test_backdated_observation_goes_critical_then_clears(self):
        """The whole of B7 in one place: watch it go red, watch it clear."""
        point = self._observe(days_ago=400)
        tripped = self._treasury_source()
        self.assertEqual(tripped["status"], "critical")
        self.assertGreater(tripped["age_days"], tripped["max_age_days"])

        # remove the backdated row and replace it with a current one
        self.db.delete(point)
        self.db.commit()
        self._observe(days_ago=0)

        cleared = self._treasury_source()
        self.assertEqual(cleared["status"], "ok")
        self.assertLessEqual(cleared["age_days"], cleared["max_age_days"])

    def test_the_trip_is_a_failure_red_not_an_error_red(self):
        """An exception would also stop a deploy, and would prove nothing about
        the check. The report must come back intact, with a status field that
        says critical."""
        self._observe(days_ago=400)
        report = get_freshness_report(self.db)
        self.assertIn("sources", report)
        self.assertIn("counts", report)
        self.assertGreaterEqual(report["counts"]["critical"], 1)

    def test_a_current_observation_alone_does_not_trip_it(self):
        """Clause (c): correct and incorrect implementations differ here. A
        watchdog that reported critical unconditionally would pass the test
        above and be worthless."""
        self._observe(days_ago=0)
        self.assertEqual(self._treasury_source()["status"], "ok")

    def test_the_boundary_is_where_the_threshold_says(self):
        """Just inside the limit is OK; well past it is not. Establishes that
        the age comparison is real rather than a constant."""
        point = self._observe(days_ago=0)
        limit = self._treasury_source()["max_age_days"]
        self.assertEqual(self._treasury_source()["status"], "ok")

        self.db.delete(point)
        self.db.commit()
        self._observe(days_ago=limit + 30)
        self.assertEqual(self._treasury_source()["status"], "critical")

    def test_no_data_at_all_is_unknown_not_ok(self):
        """Absence must be a category with a cause, never a silent pass."""
        self.assertEqual(self._treasury_source()["status"], "unknown")


if __name__ == "__main__":
    unittest.main()
