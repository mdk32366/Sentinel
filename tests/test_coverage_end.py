"""A-0016 / D-0077 — age measured from when the period ended, not when it began.

Every series is stored dated to the START of the period it describes: a TIC row
for July 2026 is dated 2026-07-01, a broad-money row for calendar 2025 is dated
2025-01-01. The observation describes a period that ENDS later - TIC's own file
says "Holdings at end of time period" - so an age measured from the stored date
overstates staleness by up to a full period, and every tolerance was inflated to
compensate.

The inflation was real and it was documented as such: TIC needed 110 days and
broad money 960, wide enough to be nearly decorative.

`A-0016` recorded this as a migration of stored dates. It is not done that way.
Rewriting three whole series is an irreversible UPDATE across the history, and a
half-applied version would leave one holding recorded under two conventions.
Deriving the coverage end at read time is the same arithmetic with nothing to
undo.
"""
import unittest
from datetime import datetime

from pipelines.freshness_watchdog import (
    CHECKS,
    _age_from_coverage,
    coverage_end,
)


class TestCoverageEnd(unittest.TestCase):
    def test_a_monthly_row_covers_to_the_end_of_its_month(self):
        self.assertEqual(
            coverage_end(datetime(2026, 7, 1), "month"), datetime(2026, 7, 31)
        )

    def test_a_quarterly_row_covers_to_the_end_of_its_quarter(self):
        # The WGC series is dated to quarter start: Q3 2026 is 2026-07-01.
        self.assertEqual(
            coverage_end(datetime(2026, 7, 1), "quarter"), datetime(2026, 9, 30)
        )

    def test_an_annual_row_covers_to_the_end_of_its_year(self):
        self.assertEqual(
            coverage_end(datetime(2025, 1, 1), "year"), datetime(2025, 12, 31)
        )

    def test_a_daily_row_covers_its_own_date(self):
        d = datetime(2026, 9, 29)
        self.assertEqual(coverage_end(d, "day"), d)

    def test_a_weekly_row_covers_its_week_ending_date(self):
        # FRED WM2NS is dated to the week-ENDING Monday (D-0095). That Monday
        # already is the coverage end — same arithmetic as day, not month.
        d = datetime(2026, 8, 31)  # a Monday
        self.assertEqual(coverage_end(d, "week"), d)
        self.assertEqual(
            _age_from_coverage(d, "week", datetime(2026, 10, 6)), 36
        )

    def test_it_crosses_a_year_boundary(self):
        self.assertEqual(
            coverage_end(datetime(2026, 12, 1), "month"), datetime(2026, 12, 31)
        )
        self.assertEqual(
            coverage_end(datetime(2026, 10, 1), "quarter"), datetime(2026, 12, 31)
        )

    def test_february_in_a_leap_year(self):
        # Computed as "first of the next period minus one day" rather than from
        # a table of month lengths, so leap years need no special case - but a
        # regression here would silently shift one month a year.
        self.assertEqual(
            coverage_end(datetime(2028, 2, 1), "month"), datetime(2028, 2, 29)
        )
        self.assertEqual(
            coverage_end(datetime(2026, 2, 1), "month"), datetime(2026, 2, 28)
        )

    def test_none_in_none_out(self):
        self.assertIsNone(coverage_end(None, "month"))
        self.assertIsNone(_age_from_coverage(None, "month", datetime(2026, 9, 30)))

    def test_an_unknown_period_falls_back_to_a_single_month(self):
        # A new source with a typo in its period must not crash the report for
        # the other nine, and must not silently claim a longer coverage than the
        # row supports.
        got = coverage_end(datetime(2026, 7, 1), "fortnight")
        self.assertEqual(got, datetime(2026, 7, 31))


class TestTheAgeIsShorterAndByTheRightAmount(unittest.TestCase):
    NOW = datetime(2026, 9, 30)

    def test_tic_drops_by_a_month(self):
        # The row dated 2026-07-01 was 91 days old by its label and 61 by its
        # coverage. Both describe the same observation.
        self.assertEqual(_age_from_coverage(datetime(2026, 7, 1), "month", self.NOW), 61)

    def test_broad_money_drops_by_nearly_a_year(self):
        # 637 days by label, 273 by coverage. This is the series where the
        # convention did the most damage.
        self.assertEqual(
            _age_from_coverage(datetime(2025, 1, 1), "year", self.NOW), 273
        )

    def test_a_daily_series_is_unaffected(self):
        # Most sources are daily and their numbers must not move at all, or this
        # change would have quietly re-tuned six guards nobody asked about.
        for d in (datetime(2026, 9, 29), datetime(2026, 9, 22)):
            self.assertEqual(
                _age_from_coverage(d, "day", self.NOW), (self.NOW - d).days
            )


class TestEverySourceDeclaresItsPeriod(unittest.TestCase):
    def test_no_source_is_missing_a_period(self):
        # A missing period silently defaults to daily, which would restore the
        # original overstatement for exactly the monthly and annual sources this
        # is about.
        missing = [c["key"] for c in CHECKS if not c.get("period")]
        self.assertEqual(missing, [], f"sources with no period: {missing}")

    def test_the_periods_match_each_source_real_cadence(self):
        expected = {
            "treasury_yields": "day", "oil": "day", "dollar_index": "day",
            "us_m2": "week",
            "gold_price": "day", "cds": "day",
            "tic": "month", "gold_reserves": "month",
            "reserves_ex_gold": "month", "sovereign_yields": "month",
            "money_supply": "year",
            "treasury_auctions": "day",
        }
        actual = {c["key"]: c.get("period") for c in CHECKS}
        self.assertEqual(actual, expected)


class TestTheRetunedTolerances(unittest.TestCase):
    """The inflation is removed, not merely relabelled."""

    def tol(self, key):
        return next(c["max_age_days"] for c in CHECKS if c["key"] == key)

    def test_tic_is_tighter_than_the_label_based_number(self):
        # Was 110 because it had to cover 77-106 days measured from the label.
        # From the coverage end the same cycle is 47-76.
        self.assertLess(self.tol("tic"), 110)
        self.assertGreaterEqual(self.tol("tic"), 76)

    def test_gold_is_tighter(self):
        # Was 95 covering 50-80; from coverage end the cycle is 28-55.
        self.assertLess(self.tol("gold_reserves"), 95)
        self.assertGreaterEqual(self.tol("gold_reserves"), 55)

    def test_broad_money_is_tighter(self):
        # Was 960 covering 558-923; from coverage end 194-559.
        self.assertLess(self.tol("money_supply"), 960)
        self.assertGreaterEqual(self.tol("money_supply"), 559)

    def test_the_observed_production_ages_all_still_pass(self):
        # Retuning a threshold downward is how a working source starts crying
        # wolf - which is F-0089, F-0091 and F-0095 - so the real newest-row
        # dates are checked against the new numbers.
        now = datetime(2026, 9, 30)
        observed = {
            "tic": datetime(2026, 7, 1),
            "gold_reserves": datetime(2026, 8, 1),
            "money_supply": datetime(2025, 1, 1),
            "reserves_ex_gold": datetime(2026, 8, 1),
            "sovereign_yields": datetime(2026, 8, 1),
        }
        for key, newest in observed.items():
            period = next(c["period"] for c in CHECKS if c["key"] == key)
            age = _age_from_coverage(newest, period, now)
            self.assertLessEqual(
                age, self.tol(key),
                f"{key}: {age}d against a tolerance of {self.tol(key)}d would "
                f"report a healthy source as stale",
            )

    def test_the_two_fred_monthly_sources_were_left_with_headroom(self):
        # reserves_ex_gold and sovereign_yields were NOT retuned. Their numbers
        # came from `calibrate` against observed data, and shifting the
        # measurement basis by a month gives them more headroom rather than
        # less - so leaving them cannot cause a false alarm. Stated here rather
        # than left for someone to infer that they were overlooked.
        for key in ("reserves_ex_gold", "sovereign_yields"):
            age = _age_from_coverage(datetime(2026, 8, 1), "month", datetime(2026, 9, 30))
            self.assertLess(age, self.tol(key) * 0.6, key)


if __name__ == "__main__":
    unittest.main()
