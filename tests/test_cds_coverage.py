"""D-0020 / T-0019: CDS coverage visibility and failed-all-None pipeline status.

Does not change Dimension 7 scoring math.
"""
import unittest
from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.models import Base, Metric, TimeSeries, UpdateLog
from pipelines.cds_fetcher import (
    CDS_INSTRUMENTS,
    CDS_PIPELINE_NAME,
    cds_fetch_status,
    cds_instrument_codes,
    get_cds_coverage,
    run_cds_fetch,
)
from pipelines import scheduler as sched


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


class TestCdsFetchStatus(unittest.TestCase):
    def test_all_none_is_failed_not_success(self):
        self.assertEqual(cds_fetch_status(attempted=40, ok=0), "failed")
        self.assertNotEqual(cds_fetch_status(40, 0), "success")
        self.assertNotEqual(cds_fetch_status(40, 0), "partial")

    def test_partial_when_some_succeed(self):
        self.assertEqual(cds_fetch_status(attempted=40, ok=3), "partial")

    def test_success_when_all_ok(self):
        self.assertEqual(cds_fetch_status(attempted=40, ok=40), "success")


class TestCdsCoverageHelper(unittest.TestCase):
    def test_empty_db_reports_all_missing(self):
        db = _session()
        try:
            coverage = get_cds_coverage(db)
            configured = len(cds_instrument_codes())
            self.assertEqual(configured, sum(len(t) for t in CDS_INSTRUMENTS.values()))
            self.assertGreater(configured, 0)
            self.assertEqual(coverage["configured"], configured)
            self.assertEqual(coverage["with_data"], 0)
            self.assertEqual(coverage["without_data"], configured)
            self.assertEqual(coverage["missing_codes"], cds_instrument_codes())
            self.assertIsNone(coverage["last_pipeline"])
        finally:
            db.close()

    def test_with_data_and_last_pipeline(self):
        db = _session()
        try:
            codes = cds_instrument_codes()
            france = codes[0]
            metric = Metric(
                code=france,
                name="France 5Y CDS",
                category="sovereign_cds",
                unit="bps",
                source="Investing.com",
            )
            db.add(metric)
            db.flush()
            db.add(TimeSeries(
                metric_id=metric.id,
                country_id=None,
                date=datetime(2026, 9, 1),
                value=Decimal("55"),
            ))
            started = datetime(2026, 9, 1, 3, 0, 0)
            db.add(UpdateLog(
                pipeline_name=CDS_PIPELINE_NAME,
                status="failed",
                records_inserted=0,
                records_updated=0,
                error_message="x" * 600,
                started_at=started,
                completed_at=datetime(2026, 9, 1, 3, 5, 0),
            ))
            db.commit()

            coverage = get_cds_coverage(db)
            self.assertEqual(coverage["with_data"], 1)
            self.assertEqual(coverage["without_data"], coverage["configured"] - 1)
            self.assertNotIn(france, coverage["missing_codes"])
            self.assertEqual(len(coverage["missing_codes"]), coverage["without_data"])
            pipe = coverage["last_pipeline"]
            self.assertIsNotNone(pipe)
            self.assertEqual(pipe["status"], "failed")
            self.assertEqual(pipe["inserted"], 0)
            self.assertEqual(pipe["updated"], 0)
            self.assertTrue(pipe["started_at"].startswith("2026-09-01"))
            self.assertLessEqual(len(pipe["error_message"]), 500)
            self.assertTrue(pipe["error_message"].endswith("..."))
        finally:
            db.close()


class TestRunCdsFetchAllNoneFailed(unittest.TestCase):
    def test_all_none_persists_failed_updatelog(self):
        db = _session()
        try:
            with patch("pipelines.cds_fetcher.fetch_cds_value", return_value=None):
                result = run_cds_fetch(db)

            self.assertGreater(result["attempted"], 0)
            self.assertEqual(result["ok"], 0)
            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["inserted"], 0)
            self.assertEqual(result["updated"], 0)
            self.assertTrue(result["errors"])

            log = (
                db.query(UpdateLog)
                .filter_by(pipeline_name=CDS_PIPELINE_NAME)
                .order_by(UpdateLog.completed_at.desc())
                .first()
            )
            self.assertIsNotNone(log)
            self.assertEqual(log.status, "failed")
            self.assertEqual(log.records_inserted, 0)
            self.assertIsNotNone(log.error_message)

            coverage = get_cds_coverage(db)
            self.assertEqual(coverage["with_data"], 0)
            self.assertEqual(coverage["last_pipeline"]["status"], "failed")
        finally:
            db.close()

    def test_partial_when_one_slug_returns_value(self):
        db = _session()

        def fake_fetch(slug, timeout=20):
            if slug.startswith("france"):
                return Decimal("80")
            return None

        try:
            with patch("pipelines.cds_fetcher.fetch_cds_value", side_effect=fake_fetch):
                result = run_cds_fetch(db)
            self.assertEqual(result["ok"], 1)
            self.assertEqual(result["status"], "partial")
            self.assertEqual(result["inserted"], 1)
            log = db.query(UpdateLog).filter_by(pipeline_name=CDS_PIPELINE_NAME).one()
            self.assertEqual(log.status, "partial")
            coverage = get_cds_coverage(db)
            self.assertEqual(coverage["with_data"], 1)
        finally:
            db.close()


class TestScheduledCdsFetch(unittest.TestCase):
    def test_scheduled_cds_fetch_closes_session(self):
        db = MagicMock()
        with patch.object(sched, "get_session", return_value=db), \
             patch.object(
                 sched,
                 "run_cds_fetch",
                 return_value={"status": "failed", "inserted": 0, "updated": 0, "ok": 0, "attempted": 1},
             ):
            sched.scheduled_cds_fetch()
        db.close.assert_called_once()

    def test_scheduled_cds_fetch_closes_session_on_error(self):
        db = MagicMock()
        with patch.object(sched, "get_session", return_value=db), \
             patch.object(sched, "run_cds_fetch", side_effect=RuntimeError("scrape failed")):
            sched.scheduled_cds_fetch()
        db.close.assert_called_once()

    def test_start_scheduler_registers_cron_then_oneshot_after_start(self):
        with patch.object(sched.settings, "scheduler_enabled", True), \
             patch.object(sched, "scheduler") as mock_sched:
            sched.start_scheduler()

            ids = [c.kwargs.get("id") for c in mock_sched.add_job.call_args_list]
            self.assertEqual(ids.count("cds_multi_tenor_job"), 1)
            self.assertIn("startup_fetches", ids)
            self.assertIn("startup_cds_fetch", ids)

            post_start_ids = []
            seen_start = False
            for name, _args, kwargs in mock_sched.method_calls:
                if name == "start":
                    seen_start = True
                    continue
                if seen_start and name == "add_job":
                    post_start_ids.append(kwargs.get("id"))
            self.assertTrue(seen_start)
            self.assertIn("startup_fetches", post_start_ids)
            self.assertIn("startup_cds_fetch", post_start_ids)
            self.assertNotIn("cds_multi_tenor_job", post_start_ids)

            oneshot = next(
                c for c in mock_sched.add_job.call_args_list
                if c.kwargs.get("id") == "startup_cds_fetch"
            )
            self.assertIs(oneshot.args[0], sched.scheduled_cds_fetch)
            self.assertIsNotNone(oneshot.kwargs.get("next_run_time"))

            cron = next(
                c for c in mock_sched.add_job.call_args_list
                if c.kwargs.get("id") == "cds_multi_tenor_job"
            )
            self.assertIs(cron.args[0], sched.scheduled_cds_fetch)


if __name__ == "__main__":
    unittest.main()
