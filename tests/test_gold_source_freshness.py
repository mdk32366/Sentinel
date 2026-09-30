"""D-0090 - D-0045 applied to gold reserves, the third file-backed source.

`D-0045` ruled that a frozen source is a **failure**, not a success and not a
`partial`. It was implemented for TIC and for the gold price, and never for
gold reserves - plausibly because that importer could not run at all
(`F-0103`), so it never reached the point where a freshness check would matter.

`gold_reserves.py` fetches nothing. It reads `data/gold_reserves.csv`, a file a
human downloads from the WGC. From the moment `F-0103` was fixed, the job would
have reported `success` forever while re-importing the same frozen file - which
is `F-0050` exactly, in a second pipeline.

The hard part is not the guard, it is the number. Rows are dated FIRST of
quarter, so a **perfectly current** file is already ~178 days old by this
measure. A bound set by intuition fires on healthy data, which is `F-0089`.
"""
import csv
import io
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.models import Base, Country
from pipelines.gold_fetcher import (
    MAX_SOURCE_AGE_DAYS,
    import_wgc_csv,
    parse_quarter,
)

REPO = Path(__file__).resolve().parents[1]
LIVE_CSV = REPO / "data" / "gold_reserves.csv"


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    db.add(Country(iso_code="USA", name="United States"))
    db.commit()
    return db


def _csv(tmp: Path, quarters, country="United States", value="8133.5"):
    """A minimal WGC-shaped file with the given quarter columns."""
    with io.open(tmp, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Holdings"] + list(quarters))
        w.writerow([country] + [value] * len(quarters))
    return tmp


class TestTheBoundDoesNotFireOnHealthyData(unittest.TestCase):
    """F-0089 is the failure this class exists to prevent."""

    def test_a_perfectly_current_file_is_already_about_178_days_old(self):
        # The fact that makes this threshold non-obvious. Measured from the
        # two real downloads in this repository's history:
        #   2026-06-24 download -> newest row Q1 26 (2026-01-01) = 174 days
        #   2026-09-26 download -> newest row Q2 26 (2026-04-01) = 178 days
        self.assertEqual((datetime(2026, 6, 24) - parse_quarter("Q1 26")).days, 174)
        self.assertEqual((datetime(2026, 9, 26) - parse_quarter("Q2 26")).days, 178)

    def test_the_bound_clears_a_freshly_downloaded_file(self):
        self.assertGreater(MAX_SOURCE_AGE_DAYS, 178)

    def test_the_bound_clears_a_healthy_file_waiting_on_the_next_quarter(self):
        # The newest row stays newest until the WGC publishes the following
        # quarter, so a promptly-refreshed file still peaks around 214-220.
        self.assertGreater(MAX_SOURCE_AGE_DAYS, 220)

    def test_the_bound_still_catches_a_file_that_missed_a_quarter(self):
        # One skipped quarter puts the newest row past 270. A bound above that
        # would be decoration (D-0024).
        self.assertLess(MAX_SOURCE_AGE_DAYS, 270)

    def test_the_live_repository_csv_passes(self):
        # The strongest form of the cry-wolf check: the file actually shipped
        # must import without raising. If this fails, the number is wrong.
        if not LIVE_CSV.exists():
            self.skipTest("data/gold_reserves.csv not present")
        db = _session()
        try:
            result = import_wgc_csv(db, csv_path=LIVE_CSV)
        finally:
            db.close()
        self.assertEqual(result["status"], "success")
        self.assertLessEqual(result["source_age_days"], MAX_SOURCE_AGE_DAYS)


class TestTheGuardFires(unittest.TestCase):
    """A guard that cannot fail is decoration (D-0024)."""

    def setUp(self):
        self.db = _session()
        # A temp directory, not the repository: a test that crashes must not
        # leave a stray CSV next to the real one.
        self._dir = tempfile.TemporaryDirectory()
        self.tmp = Path(self._dir.name) / "gold_reserves.csv"

    def tearDown(self):
        self.db.close()
        self._dir.cleanup()

    def test_a_frozen_file_raises_rather_than_reporting_success(self):
        # Q4 2019: far past any plausible bound.
        _csv(self.tmp, ["Q4 19"])
        with self.assertRaises(ValueError) as cm:
            import_wgc_csv(self.db, csv_path=self.tmp)
        msg = str(cm.exception)
        self.assertIn("stale", msg)
        self.assertIn("2019-10-01", msg)          # names the newest row
        self.assertIn(str(MAX_SOURCE_AGE_DAYS), msg)  # names the limit
        self.assertIn("gold.org", msg)            # says how to fix it

    def test_a_file_with_no_parseable_observations_raises(self):
        # A trailing column of AWAITED parses as a column and writes nothing.
        # Without this branch an empty import would report success.
        _csv(self.tmp, ["Q1 26"], value="AWAITED")
        with self.assertRaises(ValueError) as cm:
            import_wgc_csv(self.db, csv_path=self.tmp)
        self.assertIn("no parseable observations", str(cm.exception))

    def test_a_current_file_is_accepted(self):
        # The same code path, one quarter that is current - so the raise above
        # is attributable to the age and not to the fixture being malformed.
        now = datetime.utcnow()
        q = (now.month - 1) // 3 + 1
        _csv(self.tmp, [f"Q{q} {str(now.year)[2:]}"])
        result = import_wgc_csv(self.db, csv_path=self.tmp)
        self.assertEqual(result["status"], "success")
        self.assertGreaterEqual(result["inserted"], 1)

    def test_nothing_is_written_when_the_guard_fires(self):
        # D-0045's point is that the log must not say success. It must also
        # not half-import: a rolled-back frozen file leaves no rows behind.
        from database.models import TimeSeries

        _csv(self.tmp, ["Q4 19"])
        with self.assertRaises(ValueError):
            import_wgc_csv(self.db, csv_path=self.tmp)
        self.assertEqual(self.db.query(TimeSeries).count(), 0)

    def test_the_newest_row_is_what_counts_not_the_newest_column(self):
        # A frozen file with an empty current column would otherwise look
        # current. The date tracked is the one actually written.
        now = datetime.utcnow()
        q = (now.month - 1) // 3 + 1
        with io.open(self.tmp, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["Holdings", "Q4 19", f"Q{q} {str(now.year)[2:]}"])
            w.writerow(["United States", "8133.5", "AWAITED"])
        with self.assertRaises(ValueError) as cm:
            import_wgc_csv(self.db, csv_path=self.tmp)
        self.assertIn("2019-10-01", str(cm.exception))


class TestEveryFileBackedSourceHasABound(unittest.TestCase):
    """The general lesson of F-0103 and D-0090.

    The rule existed twice and the third source went without it for months. A
    fourth one must not be able to.
    """

    def test_all_three_declare_a_maximum_source_age(self):
        import importlib

        missing = []
        for mod in ("pipelines.treasury_holdings",
                    "pipelines.gold_price_import",
                    "pipelines.gold_fetcher"):
            m = importlib.import_module(mod)
            if not isinstance(getattr(m, "MAX_SOURCE_AGE_DAYS", None), int):
                missing.append(mod)
        self.assertEqual(missing, [])

    def test_the_bounds_are_not_copied_from_each_other(self):
        # Three sources, three cadences: TIC monthly, gold price monthly,
        # gold reserves quarterly-with-a-two-quarter-lag. Equal numbers would
        # mean one was inherited rather than derived - the mistake D-0080 made
        # and D-0088 had to undo.
        import importlib

        vals = [importlib.import_module(m).MAX_SOURCE_AGE_DAYS
                for m in ("pipelines.treasury_holdings",
                          "pipelines.gold_price_import",
                          "pipelines.gold_fetcher")]
        self.assertEqual(len(vals), len(set(vals)), f"identical bounds: {vals}")


if __name__ == "__main__":
    unittest.main()
