"""D-0095 G1–G7 — us_m2 freshness CHECK + A-0013 WM2NS card claim."""
import datetime
import re
import unittest
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.models import Base, Metric, TimeSeries, UpdateLog
from pipelines.freshness_watchdog import CHECKS, get_freshness_report

ROOT = Path(__file__).resolve().parents[1]


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _seed_wm2ns(db, days_ago):
    m = Metric(
        code="WM2NS",
        name="M2 Money Supply (Weekly)",
        category="monetary",
        unit="billions",
        source="FRED",
    )
    db.add(m)
    db.commit()
    db.add(TimeSeries(
        metric_id=m.id,
        country_id=None,
        date=datetime.datetime.utcnow() - datetime.timedelta(days=days_ago),
        value=23305.5,
    ))
    db.commit()
    # A recent FRED success so run-health does not dominate age.
    when = datetime.datetime.utcnow() - datetime.timedelta(hours=2)
    db.add(UpdateLog(
        pipeline_name="FRED",
        status="success",
        records_inserted=1,
        records_updated=0,
        error_message=None,
        started_at=when,
        completed_at=when,
    ))
    db.commit()
    return m


def _us_m2(report):
    for s in report["sources"]:
        if s["key"] == "us_m2":
            return s
    raise AssertionError("us_m2 missing from freshness report")


class G1FredMetricsStillBoth(unittest.TestCase):
    """G1 — FRED_METRICS still contains both WM2NS and M2SL."""

    def test_both_series_present(self):
        body = (ROOT / "pipelines" / "fred_fetcher.py").read_text(encoding="utf-8")
        self.assertIn('"WM2NS"', body)
        self.assertIn('"M2SL"', body)


class G2MarketsCardIsWm2ns(unittest.TestCase):
    """G2 — MARKETS METRICS has WM2NS and not M2SL as a card code."""

    def test_card_codes(self):
        body = (ROOT / "ui" / "src" / "lib" / "constants.js").read_text(
            encoding="utf-8"
        )
        # Pull every code: "…" inside METRICS.
        codes = re.findall(r'code:\s*"([A-Z0-9_]+)"', body)
        # Restrict to the METRICS array roughly: after "export const METRICS"
        start = body.index("export const METRICS")
        end = body.index("];", start)
        block = body[start:end]
        codes = re.findall(r'code:\s*"([A-Z0-9_]+)"', block)
        self.assertIn("WM2NS", codes)
        self.assertNotIn("M2SL", codes)


class G3TipDisclosesNsaAndMonthlyRelease(unittest.TestCase):
    """G3 — WM2NS tip still has NSA + once a month."""

    def test_tip(self):
        body = (ROOT / "ui" / "src" / "lib" / "constants.js").read_text(
            encoding="utf-8"
        )
        # Locate the WM2NS tip string.
        m = re.search(
            r'code:\s*"WM2NS"[\s\S]*?tip:\s*"([^"]+)"',
            body,
        )
        self.assertIsNotNone(m, "WM2NS tip not found")
        tip = m.group(1).lower()
        self.assertIn("not seasonally adjusted", tip)
        self.assertIn("once a month", tip)


class G4UsM2CheckShape(unittest.TestCase):
    """G4 — CHECKS contains us_m2 with the Spec shape."""

    def test_shape(self):
        src = next((c for c in CHECKS if c["key"] == "us_m2"), None)
        self.assertIsNotNone(src, "us_m2 missing from CHECKS")
        self.assertEqual(src["patterns"], ["WM2NS"])
        self.assertEqual(src["period"], "week")
        self.assertEqual(src["pipelines"], ["FRED"])
        self.assertGreaterEqual(src["max_age_days"], 45)
        self.assertLessEqual(src["max_age_days"], 70)
        note = (src.get("note") or "").lower()
        self.assertIn("h.6", note)
        self.assertTrue(
            "not seasonally adjusted" in note or "nsa" in note,
            "note should disclose NSA / not seasonally adjusted",
        )


class G5SyntheticAge(unittest.TestCase):
    """G5 — fresh WM2NS → ok; 80d → stale; >2×max → critical."""

    def test_yesterday_is_ok(self):
        db = _session()
        self.addCleanup(db.close)
        _seed_wm2ns(db, days_ago=1)
        src = _us_m2(get_freshness_report(db))
        self.assertEqual(src["status"], "ok")
        self.assertEqual(src["reason"], "age")

    def test_eighty_days_is_stale_or_critical(self):
        # max_age_days=55 → 80 is stale (≤110); Spec allows either per _classify.
        db = _session()
        self.addCleanup(db.close)
        _seed_wm2ns(db, days_ago=80)
        src = _us_m2(get_freshness_report(db))
        self.assertIn(src["status"], ("stale", "critical"))
        self.assertNotEqual(src["status"], "ok")

    def test_well_past_double_is_critical(self):
        db = _session()
        self.addCleanup(db.close)
        _seed_wm2ns(db, days_ago=120)
        src = _us_m2(get_freshness_report(db))
        self.assertEqual(src["status"], "critical")


class G6A0013NoLongerNamesM2slAsCard(unittest.TestCase):
    """G6 — A-0013 text does not claim the M2 card reads M2SL."""

    def test_a0013_settled_claim(self):
        body = (ROOT / "docs" / "assumptions.md").read_text(encoding="utf-8")
        # Isolate the A-0013 section through the next ### heading.
        m = re.search(r"### A-0013[\s\S]*?(?=\n### |\Z)", body)
        self.assertIsNotNone(m, "A-0013 section missing")
        section = m.group(0)
        # Historical narrative may still mention M2SL as what the card *was*.
        # The settled claim must name WM2NS as the card and must not say the
        # card *is* / *reads* M2SL.
        self.assertIn("WM2NS", section)
        # Reject the stale "cards — `CPIAUCSL` and `M2SL`" / "card reads M2SL"
        # formulations that taught the wrong series.
        self.assertNotRegex(
            section,
            r"(?i)(card|cards).{0,40}`?M2SL`?.{0,20}(still monthly|are monthly)",
        )
        self.assertNotRegex(
            section,
            r"(?i)M2 (card|tile).{0,30}`?M2SL`?",
        )
        # Positive: settled language.
        self.assertRegex(
            section,
            r"(?i)(reads|card now reads|M2 card).{0,40}`?WM2NS`?",
        )


class G7MutationGuardsExist(unittest.TestCase):
    """G7 scaffolding — the mutation runner exercises these; smoke that
    the assertions above are loadable as named gates."""

    def test_gates_are_importable(self):
        # Presence check so a deleted G4 class fails here before mut script.
        self.assertTrue(callable(G4UsM2CheckShape.test_shape))
        self.assertTrue(callable(G1FredMetricsStillBoth.test_both_series_present))
        self.assertTrue(callable(G2MarketsCardIsWm2ns.test_card_codes))
        self.assertTrue(callable(G3TipDisclosesNsaAndMonthlyRelease.test_tip))


if __name__ == "__main__":
    unittest.main()
