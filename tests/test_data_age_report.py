"""A-0017 — the distribution of per-country data age.

The watchdog answers "is this SOURCE current". Nothing answered "is it current
for this COUNTRY", and `F-0092` is why that matters: `money_supply` is `ok` at
the source, correctly, while Canada's newest broad money figure is **2008** and
dimension 3 was scoring it.

`A-0017` asked for the measurement before four more cutoffs get invented, so
this module computes no verdict and these cases check that it stays that way.
"""
import unittest
from datetime import datetime

from fastapi.routing import APIRoute

from api.routes import router
from pipelines.data_age_report import (
    BUCKETS,
    COUNTRY_COLUMN_PATTERNS,
    LAGGARD_TOLERANCE_MULTIPLE,
    _bucket_label,
    _percentile,
)
from pipelines.freshness_watchdog import CHECKS


class TestBucketing(unittest.TestCase):
    def test_boundaries_are_inclusive_at_the_top(self):
        self.assertEqual(_bucket_label(90), "0-90d")
        self.assertEqual(_bucket_label(91), "91-180d")

    def test_the_oldest_bucket_is_open_ended(self):
        # Canada's 2008 figure is about 6,800 days old. A closed top bucket
        # would silently drop it out of the histogram it exists to appear in.
        self.assertEqual(_bucket_label(99999), f">{BUCKETS[-1]}d")
        self.assertEqual(_bucket_label(6800), f">{BUCKETS[-1]}d")

    def test_every_age_lands_in_exactly_one_bucket(self):
        labels = {_bucket_label(v) for v in range(0, 4000, 7)}
        self.assertEqual(len(labels), len(BUCKETS) + 1)

    def test_the_boundaries_straddle_the_real_cadences(self):
        # Monthly, quarterly and annual publication all need a boundary that
        # separates "late" from "normal" for that cadence.
        for cadence in (90, 365):
            self.assertIn(cadence, BUCKETS)


class TestPercentile(unittest.TestCase):
    def test_median_of_an_odd_list(self):
        self.assertEqual(_percentile([1, 2, 3], 0.5), 2)

    def test_p90_picks_a_high_value_not_the_max(self):
        vals = list(range(1, 101))
        self.assertGreater(_percentile(vals, 0.9), 85)
        self.assertLessEqual(_percentile(vals, 0.9), 100)

    def test_a_single_value_is_its_own_every_percentile(self):
        for q in (0.0, 0.5, 0.9, 1.0):
            self.assertEqual(_percentile([42], q), 42)

    def test_an_empty_list_is_none_rather_than_an_error(self):
        # A source with no rows at all must report "nothing" rather than fail
        # the whole report for the other nine.
        self.assertIsNone(_percentile([], 0.5))


class TestTheLaggardThresholdIsDerived(unittest.TestCase):
    def test_it_is_a_multiple_of_the_watchdog_tolerance_not_a_new_constant(self):
        # A fresh absolute number here would be a fourth opinion about
        # staleness, which is F-0087. The watchdog owns the tolerances; this
        # scales them.
        self.assertGreater(LAGGARD_TOLERANCE_MULTIPLE, 1.0)

    def test_the_multiple_is_loose_enough_not_to_flag_normal_lag(self):
        # At 1.0 every source would report laggards on its ordinary cadence,
        # which is the cry-wolf shape of F-0089 and F-0091 in a brand-new
        # diagnostic.
        self.assertGreaterEqual(LAGGARD_TOLERANCE_MULTIPLE, 1.5)


class TestItCoversTheSourcesTheModelScores(unittest.TestCase):
    def test_the_country_column_patterns_all_appear_in_the_watchdog(self):
        # These name the storage shape of real sources. A typo would silently
        # send a source down the wrong query and report nothing.
        configured = {p for c in CHECKS for p in c.get("patterns", [])}
        for p in COUNTRY_COLUMN_PATTERNS:
            self.assertIn(p, configured, f"{p} matches no watchdog source")

    def test_the_scored_dimensions_are_all_monitored(self):
        # If a scoring dimension's source is not in CHECKS it is not in this
        # report either, and the blind spot A-0017 is about would persist in
        # the very thing measuring it.
        keys = {c["key"] for c in CHECKS}
        for key in ("tic", "gold_reserves", "money_supply", "cds",
                    "reserves_ex_gold", "sovereign_yields"):
            self.assertIn(key, keys)

    def test_it_derives_its_source_list_rather_than_holding_one(self):
        # Reads CHECKS directly, so a source added to the watchdog appears here
        # without anyone remembering to add it twice.
        import inspect

        from pipelines import data_age_report

        body = inspect.getsource(data_age_report)
        self.assertIn("for check in CHECKS", body)


class TestItIsReadOnly(unittest.TestCase):
    def test_the_module_never_writes(self):
        # A-0017 asks for a measurement. A diagnostic that also decided
        # something would be a fifth scoring rule nobody reviewed.
        import inspect

        from pipelines import data_age_report

        body = inspect.getsource(data_age_report)
        for forbidden in ("db.add", "db.commit", "db.delete", "UpdateLog"):
            self.assertNotIn(forbidden, body, f"the report {forbidden}s")

    def test_the_route_is_a_get(self):
        paths = [(r.path, r.methods) for r in router.routes if isinstance(r, APIRoute)]
        match = [m for p, m in paths if p == "/api/diagnostics/data-age"]
        self.assertTrue(match, "the route does not exist")
        self.assertIn("GET", match[0])
        self.assertNotIn("POST", match[0])


if __name__ == "__main__":
    unittest.main()
