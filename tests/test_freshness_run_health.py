"""D-0094 G3–G6, G8, G10 — run-health watchdog."""
import datetime
import logging
import os
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.models import Base, Metric, TimeSeries, UpdateLog
from pipelines.freshness_watchdog import (
    DEFAULT_MAX_CONSECUTIVE_FAILURES,
    get_freshness_report,
    run_freshness_check,
)


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _seed_gold_data(db, days_ago=1):
    m = Metric(
        code="GOLD_SPOT_USD", name="Gold", category="gold",
        unit="USD/oz", source="test",
    )
    db.add(m)
    db.commit()
    db.add(TimeSeries(
        metric_id=m.id, country_id=None,
        date=datetime.datetime.utcnow() - datetime.timedelta(days=days_ago),
        value=4000,
    ))
    db.commit()
    return m


def _log(db, status, error=None, hours_ago=0, pipeline="Gold_Spot_Price"):
    when = datetime.datetime.utcnow() - datetime.timedelta(hours=hours_ago)
    db.add(UpdateLog(
        pipeline_name=pipeline, status=status,
        records_inserted=0, records_updated=0,
        error_message=error,
        started_at=when, completed_at=when,
    ))
    db.commit()


def _gold(report):
    for s in report["sources"]:
        if s["key"] == "gold_price":
            return s
    raise AssertionError("gold_price missing")


class TestBlockedShowsRed(unittest.TestCase):
    """G3 — a 403 run shows red on the very next status read."""

    def setUp(self):
        self.db = _session()
        self.addCleanup(self.db.close)
        _seed_gold_data(self.db, days_ago=1)
        _log(self.db, "success", hours_ago=30)
        _log(
            self.db, "failed",
            error="FETCH_BLOCKED http=403 cf=1 host=prices.lbma.org.uk | GOLD_SPOT_USD: HTTP Error 403",
            hours_ago=1,
        )

    def test_critical_blocked(self):
        src = _gold(get_freshness_report(self.db))
        self.assertEqual(src["status"], "critical")
        self.assertEqual(src["reason"], "blocked")
        pipe = src["pipelines"]["Gold_Spot_Price"]
        self.assertEqual(pipe["status"], "failed")
        self.assertEqual(pipe["failure_kind"], "blocked")
        self.assertTrue(pipe["cloudflare"])
        self.assertEqual(pipe["http_status"], 403)


class TestThreeFailures(unittest.TestCase):
    """G4 — three consecutive failures → red; two → amber; success clears."""

    def setUp(self):
        self.db = _session()
        self.addCleanup(self.db.close)
        _seed_gold_data(self.db, days_ago=0)
        _log(self.db, "success", hours_ago=100)

    def test_three_transient_critical(self):
        for i in range(3):
            _log(
                self.db, "failed",
                error="FETCH_TRANSIENT http=503 host=api.gold-api.com | boom",
                hours_ago=3 - i,
            )
        src = _gold(get_freshness_report(self.db))
        self.assertEqual(src["status"], "critical")
        self.assertEqual(src["reason"], "failing")
        self.assertEqual(
            src["pipelines"]["Gold_Spot_Price"]["consecutive_failures"], 3
        )

    def test_two_transient_stale(self):
        for i in range(2):
            _log(
                self.db, "failed",
                error="FETCH_TRANSIENT http=503 host=api.gold-api.com | boom",
                hours_ago=2 - i,
            )
        src = _gold(get_freshness_report(self.db))
        self.assertEqual(src["status"], "stale")
        self.assertEqual(src["reason"], "last_run_failed")

    def test_success_clears(self):
        for i in range(3):
            _log(self.db, "failed",
                 error="FETCH_TRANSIENT http=503 host=x | boom", hours_ago=10 - i)
        _log(self.db, "success", hours_ago=0)
        src = _gold(get_freshness_report(self.db))
        self.assertEqual(src["status"], "ok")
        self.assertEqual(src["reason"], "age")


class TestOneTransientAndLegacy(unittest.TestCase):
    """G5."""

    def setUp(self):
        self.db = _session()
        self.addCleanup(self.db.close)
        _seed_gold_data(self.db, days_ago=0)
        _log(self.db, "success", hours_ago=50)

    def test_one_transient_is_amber(self):
        _log(self.db, "failed",
             error="FETCH_TRANSIENT net=timeout host=api.gold-api.com | t",
             hours_ago=1)
        src = _gold(get_freshness_report(self.db))
        self.assertEqual(src["status"], "stale")
        self.assertNotEqual(src["status"], "critical")

    def test_legacy_unprefixed_counts_as_failure_not_block(self):
        _log(self.db, "failed",
             error="GOLD_SPOT_USD: HTTP Error 403: Forbidden", hours_ago=1)
        src = _gold(get_freshness_report(self.db))
        # kind None → not blocked; single failure → stale
        self.assertEqual(src["status"], "stale")
        self.assertEqual(src["reason"], "last_run_failed")
        self.assertIsNone(src["pipelines"]["Gold_Spot_Price"]["failure_kind"])


class TestPipelineViewHonesty(unittest.TestCase):
    """G6."""

    def setUp(self):
        self.db = _session()
        self.addCleanup(self.db.close)
        _seed_gold_data(self.db, days_ago=1)
        _log(self.db, "success", hours_ago=80)
        _log(self.db, "failed",
             error="FETCH_BLOCKED http=403 cf=1 host=x | y", hours_ago=1)

    def test_status_is_failed_not_success(self):
        src = _gold(get_freshness_report(self.db))
        pipe = src["pipelines"]["Gold_Spot_Price"]
        self.assertEqual(pipe["status"], "failed")
        self.assertIsNotNone(pipe["last_success"])
        self.assertNotEqual(pipe["status"], "success")


class TestAlerting(unittest.TestCase):
    """G8."""

    def setUp(self):
        self.db = _session()
        self.addCleanup(self.db.close)
        _seed_gold_data(self.db, days_ago=1)
        _log(self.db, "success", hours_ago=80)
        _log(self.db, "failed",
             error="FETCH_BLOCKED http=403 cf=1 host=prices.lbma.org.uk | y",
             hours_ago=1)

    def test_missing_webhook_warns(self):
        env = {k: v for k, v in os.environ.items() if k != "JARVIS_WEBHOOK_URL"}
        with patch.dict(os.environ, env, clear=True):
            with self.assertLogs("pipelines.freshness_watchdog", level="WARNING") as cm:
                report = run_freshness_check(self.db, notify=True)
        warnings = [r.getMessage() for r in cm.records]
        hits = [w for w in warnings
                if w == "FRESHNESS ALERT NOT SENT: JARVIS_WEBHOOK_URL is not configured"]
        self.assertEqual(len(hits), 1)
        self.assertFalse(report["alerting"]["webhook_configured"])
        blob = " ".join(warnings)
        self.assertNotIn("https://", blob)  # no URL value in test output

    def test_webhook_configured_calls_notify(self):
        with patch.dict(os.environ, {"JARVIS_WEBHOOK_URL": "http://example.test/hook"}):
            with patch("pipelines.freshness_watchdog._notify") as notify:
                report = run_freshness_check(self.db, notify=True)
        notify.assert_called_once()
        self.assertTrue(report["alerting"]["webhook_configured"])
        # payload reason surfaces in problems / text path — check call arg
        arg = notify.call_args[0][0]
        gold = _gold(arg)
        self.assertEqual(gold["reason"], "blocked")


class TestNote(unittest.TestCase):
    """G10."""

    def test_no_manual_csv(self):
        db = _session()
        self.addCleanup(db.close)
        src = _gold(get_freshness_report(db))
        self.assertNotIn("MANUAL CSV", src["note"] or "")
        self.assertIn("gold-api.com", src["note"])
        self.assertIn("D-0094", src["note"])


class TestDefaultN(unittest.TestCase):
    def test_default_is_three(self):
        self.assertEqual(DEFAULT_MAX_CONSECUTIVE_FAILURES, 3)


if __name__ == "__main__":
    unittest.main()
