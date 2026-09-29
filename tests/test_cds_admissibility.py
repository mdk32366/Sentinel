"""F-0074: a CDS quote must be current and must be a running spread.

Three things were wrong at once, and all three came from `get_cds_score`
reading the latest value with no regard for its age:

  * Every `*_CDS_10Y` series froze at 500.0 on 2026-07-16 — the ISDA standard
    running coupon, written by a scraper that has since been fixed. Germany,
    Japan, Switzerland and the United States all sat at 500bps. It fed the
    term-structure component and the CDS tab's "Inverted Curves" tile.
  * `SAUDI_ARABIA_CDS_5Y` held seven rows of the same 500.0 from the same
    window. It scored 10 points, which was **100% of Saudi Arabia's composite
    score** — the country appeared on the COMPOSITE tab purely on a
    missing-data placeholder.
  * `RUSSIA_CDS_5Y` read 13,775.2 — 137.75% — frozen to one decimal for 23
    consecutive days including weekends, after Russia's CDS triggered and
    settled at auction in 2022. It earned the maximum 20 points inside a
    CRISIS score.

The fetcher already refused to produce any of this. The reader did not refuse
to consume it. Fixing the writer does not fix the reader.
"""
import unittest
from datetime import datetime, timedelta

from pipelines.composite_stress import (
    MAX_CDS_AGE_DAYS,
    MAX_PLAUSIBLE_CDS_BPS,
    admit_cds_quote,
)

NOW = datetime(2026, 9, 29)


def _age(days):
    return NOW - timedelta(days=days)


class AGoodQuoteIsAdmitted(unittest.TestCase):
    def test_a_current_ordinary_spread_passes(self):
        # Germany 9.6, Turkey 248.1, Egypt 307.3 — the real board.
        for value in (7.5, 9.6, 33.8, 129.6, 248.1, 307.3):
            with self.subTest(value=value):
                self.assertIsNone(admit_cds_quote(value, _age(1), now=NOW))

    def test_a_genuinely_distressed_but_quotable_spread_passes(self):
        # The guard must not simply reject "large". A sovereign under real
        # stress can print four figures and still be quoted as a running
        # spread; refusing that would delete the signal the dimension exists
        # to catch.
        self.assertIsNone(admit_cds_quote(2500.0, _age(1), now=NOW))
        self.assertIsNone(admit_cds_quote(9999.0, _age(1), now=NOW))


class StaleQuotesAreRefused(unittest.TestCase):
    def test_the_july_placeholders_are_refused(self):
        # Saudi Arabia's 5Y and every 10Y series, as of 2026-09-29.
        reason = admit_cds_quote(500.0, datetime(2026, 7, 16), now=NOW)
        self.assertIsNotNone(reason)
        self.assertIn("stale", reason)
        self.assertIn("75d", reason)

    def test_the_boundary_is_inclusive_on_the_good_side(self):
        self.assertIsNone(admit_cds_quote(100.0, _age(MAX_CDS_AGE_DAYS), now=NOW))
        self.assertIn("stale", admit_cds_quote(100.0, _age(MAX_CDS_AGE_DAYS + 1), now=NOW))

    def test_a_long_weekend_does_not_trip_it(self):
        # The window has to absorb a holiday plus an outage, or the guard
        # fires on ordinary operation and gets ignored.
        self.assertIsNone(admit_cds_quote(100.0, _age(4), now=NOW))

    def test_staleness_is_judged_per_tenor(self):
        # The 10Y board stopped in July while the 5Y did not. Judging the pair
        # together would either keep the dead 10Y or discard the live 5Y.
        self.assertIsNone(admit_cds_quote(248.1, _age(1), now=NOW))
        self.assertIn("stale", admit_cds_quote(500.0, datetime(2026, 7, 16), now=NOW))


class ImplausibleQuotesAreRefused(unittest.TestCase):
    def test_russia_is_refused_even_though_it_is_current(self):
        # 13,775.2 as of today. Not stale — and still not a running spread.
        reason = admit_cds_quote(13775.2, _age(0), now=NOW)
        self.assertEqual(reason, "not quoted as a running spread")

    def test_the_ceiling_is_one_hundred_percent_of_notional(self):
        self.assertEqual(MAX_PLAUSIBLE_CDS_BPS, 10000.0)
        self.assertIsNone(admit_cds_quote(MAX_PLAUSIBLE_CDS_BPS - 0.1, _age(0), now=NOW))
        self.assertIsNotNone(admit_cds_quote(MAX_PLAUSIBLE_CDS_BPS, _age(0), now=NOW))

    def test_a_non_positive_quote_is_refused(self):
        self.assertEqual(admit_cds_quote(0.0, _age(0), now=NOW), "non-positive quote")
        self.assertEqual(admit_cds_quote(-5.0, _age(0), now=NOW), "non-positive quote")


class AbsenceIsReportedAsAbsence(unittest.TestCase):
    def test_no_value_and_no_date_read_as_no_coverage(self):
        self.assertEqual(admit_cds_quote(None, None, now=NOW), "no coverage")
        self.assertEqual(admit_cds_quote(100.0, None, now=NOW), "no coverage")
        self.assertEqual(admit_cds_quote(None, _age(1), now=NOW), "no coverage")

    def test_every_refusal_says_why(self):
        # The point of returning a reason rather than a bool: a country with
        # no quote and a country whose quote was thrown away both score zero,
        # and the UI has to be able to tell the reader which happened.
        refusals = [
            admit_cds_quote(None, None, now=NOW),
            admit_cds_quote(500.0, datetime(2026, 7, 16), now=NOW),
            admit_cds_quote(13775.2, _age(0), now=NOW),
        ]
        self.assertEqual(len(set(refusals)), 3, "refusal reasons must be distinguishable")
        for reason in refusals:
            self.assertTrue(reason and reason.strip())


if __name__ == "__main__":
    unittest.main()
