"""D-0046 — the MAX_JUMP_PP anomaly reaches the freshness report.

The testplan carried this as an open item from the day the watchdog was
written: the anomaly landed in `update_logs.error_message` and nowhere else,
which is a check placed where its answer cannot change what anyone does -
Principle 9's second form.

It stays NON-BLOCKING, and that is deliberate. On 2026-09-23 the 10-year moved
15 basis points in one session during a genuine selloff. A blocking jump
detector is a mechanism for refusing to record a crisis. The defect was
invisibility, not permissiveness, so the fix is visibility.

Offline, in-memory SQLite.
"""
import datetime
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.models import Base, Metric, TimeSeries, UpdateLog
from pipelines.freshness_watchdog import ANOMALY_MARKER, get_freshness_report

TREASURY_KEY = "treasury_yields"


class TestAnomalySurfacing(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.addCleanup(self.db.close)

        metric = Metric(code="DGS10", name="10-Year Treasury Yield",
                        category="treasury", unit="%", source="test")
        self.db.add(metric)
        self.db.commit()
        # a current observation, so freshness alone would read OK
        self.db.add(TimeSeries(metric_id=metric.id, country_id=None,
                               date=datetime.datetime.utcnow(), value=5.18))
        self.db.commit()

    def _log(self, message):
        now = datetime.datetime.utcnow()
        self.db.add(UpdateLog(
            pipeline_name="TreasuryDirect", status="success",
            records_inserted=1, records_updated=0,
            error_message=message, started_at=now, completed_at=now,
        ))
        self.db.commit()

    def _source(self):
        for s in get_freshness_report(self.db)["sources"]:
            if s["key"] == TREASURY_KEY:
                return s
        self.fail("treasury_yields missing from report")

    def test_without_an_anomaly_the_source_is_ok(self):
        """Clause (c): correct and incorrect must differ. A report that always
        said `anomaly` would pass the next test and be worthless."""
        self._log(None)
        source = self._source()
        self.assertEqual(source["status"], "ok")
        self.assertEqual(source["anomalies"], [])

    def test_an_anomaly_raises_an_otherwise_ok_source(self):
        """The whole point: the answer now changes what the report says."""
        self._log(f"{ANOMALY_MARKER} DGS10 2026-09-23 moved 1.90pp from 4.96")
        source = self._source()
        self.assertEqual(source["status"], "anomaly")
        self.assertEqual(len(source["anomalies"]), 1)
        self.assertIn("DGS10", source["anomalies"][0])

    def test_the_anomaly_text_is_carried_not_just_a_flag(self):
        """A boolean would send the reader back to the log field this exists
        to replace."""
        self._log(f"{ANOMALY_MARKER} DGS10 jumped 1.90pp; DGS30 jumped 1.70pp")
        self.assertEqual(len(self._source()["anomalies"]), 2)

    def test_it_never_blocks(self):
        """Non-blocking by design. The report must still be a complete,
        well-formed report - not an exception, not a truncated payload."""
        self._log(f"{ANOMALY_MARKER} DGS10 jumped 1.90pp")
        report = get_freshness_report(self.db)
        self.assertIn("sources", report)
        self.assertIn("counts", report)
        self.assertEqual(report["counts"]["anomaly"], 1)

    def test_a_worse_status_wins(self):
        """Stale data with an odd jump is still stale. The anomaly raises OK;
        it must never lower something more serious."""
        old = datetime.datetime.utcnow() - datetime.timedelta(days=400)
        metric = self.db.query(Metric).filter_by(code="DGS10").first()
        self.db.query(TimeSeries).delete()
        self.db.add(TimeSeries(metric_id=metric.id, country_id=None,
                               date=old, value=5.18))
        self.db.commit()
        self._log(f"{ANOMALY_MARKER} DGS10 jumped 1.90pp")
        self.assertEqual(self._source()["status"], "critical")

    def test_a_non_anomaly_error_does_not_trip_it(self):
        """A 502 in the log is not a jump. Matching loosely here would make
        every transient failure read as a data anomaly."""
        self._log("DGS10: 502 Server Error api_key=***")
        self.assertEqual(self._source()["status"], "ok")

    def test_anomaly_does_not_outrank_a_more_serious_status(self):
        """A genuine market move must not outrank real staleness or absence.

        This fixture holds one metric, so the other nine sources have no data
        and are `unknown`. Overall must therefore stay `unknown`: no data at
        all is a worse answer than an odd jump, and if `anomaly` won here it
        would mask every missing source the moment a yield moved.
        """
        self._log(f"{ANOMALY_MARKER} DGS10 jumped 1.90pp")
        report = get_freshness_report(self.db)
        self.assertEqual(report["counts"]["anomaly"], 1)
        self.assertGreater(report["counts"]["unknown"], 0)
        self.assertEqual(report["overall"], "unknown")

    def test_anomaly_is_reported_when_it_is_the_worst_thing_present(self):
        """And it must not be swallowed either - with nothing worse around,
        the anomaly is what the report leads with."""
        self._log(f"{ANOMALY_MARKER} DGS10 jumped 1.90pp")
        sources = get_freshness_report(self.db)["sources"]
        flagged = [s for s in sources if s["status"] == "anomaly"]
        self.assertEqual(len(flagged), 1)
        self.assertEqual(flagged[0]["key"], TREASURY_KEY)


if __name__ == "__main__":
    unittest.main()
