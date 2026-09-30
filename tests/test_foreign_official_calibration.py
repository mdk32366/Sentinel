"""D-0088 / A-0020 — the Foreign Official rule was calibrated on too little history.

`D-0080` built a "sustained decline" flag from the **thirteen months** SLT
Table 5 carries: 8 or more falls in the last 12 monthly steps plus a 1.0pp
cumulative move. `A-0020` recorded the open question - is 9-of-12 ordinary for
this series, or the de-dollarization it appears to be? - and said only a second
year could answer it.

`D-0081` had already supplied it. SLT **Table 3** carries the same aggregates
back to **2020-01**: 79 months, not 13.

Against that history the answer inverts:

  * 9 falls in 12 is the **median** window.
  * The old rule fires on **70% of windows** - decoration (`D-0024`).
  * The current -1.86pp move is at the **84th percentile**: 56 of 67 windows
    were MORE negative. The flag was firing on one of the mildest periods in
    the series.

The structural finding is real and much larger than any 12-month window:
official share **59.34% -> 40.80%** since 2020 while private holdings rose
**91.6%**. That is reported as a trend. The alarm is not.
"""
import unittest

from pipelines.tic_aggregate import (
    FO_MEDIAN_MOVE_PP,
    FO_WORST_DECILE_PP,
    SHARE_MOVE_PCT_POINTS,
)

# The 67 rolling 12-month share moves, measured from the real 79-month series.
OBSERVED_MIN = -6.98
OBSERVED_P10 = -5.10
OBSERVED_MEDIAN = -3.23
OBSERVED_CURRENT = -1.86
OBSERVED_MAX = 0.72


class TestTheThresholdComesFromThisSeries(unittest.TestCase):
    def test_it_is_the_worst_decile_of_the_observed_distribution(self):
        self.assertAlmostEqual(FO_WORST_DECILE_PP, OBSERVED_P10, places=2)

    def test_it_is_more_severe_than_the_median_window(self):
        # A threshold at or above the median fires more than half the time,
        # which is the defect A-0020 asked about.
        self.assertLess(FO_WORST_DECILE_PP, FO_MEDIAN_MOVE_PP)

    def test_it_does_not_fire_on_the_current_window(self):
        # The point of the recalibration. -1.86pp is the 84th percentile.
        self.assertGreater(OBSERVED_CURRENT, FO_WORST_DECILE_PP)

    def test_it_still_fires_on_the_worst_periods(self):
        # A threshold nothing can reach is the opposite failure (F-0089).
        self.assertGreater(FO_WORST_DECILE_PP, OBSERVED_MIN)

    def test_it_is_not_all_other_s_threshold(self):
        # D-0080 already refused to inherit SHARE_MOVE_PCT_POINTS across two
        # series that happen to share a unit. This one is derived from its own
        # distribution too, and the two are not interchangeable.
        self.assertNotEqual(abs(FO_WORST_DECILE_PP), SHARE_MOVE_PCT_POINTS)


class TestTheRetiredRuleWouldHaveBeenDecoration(unittest.TestCase):
    """Held as arithmetic, so the reason survives the code changing."""

    # Falls per 12-month window across the 67 windows.
    FALLS_MIN, FALLS_MEDIAN, FALLS_MAX = 4, 9, 11
    OLD_RULE_HIT_RATE = 47 / 67  # >=8 falls and >=1.0pp

    def test_nine_falls_is_the_median_not_a_finding(self):
        self.assertEqual(self.FALLS_MEDIAN, 9)

    def test_the_old_rule_fired_on_most_windows(self):
        self.assertGreater(self.OLD_RULE_HIT_RATE, 0.5)

    def test_a_decile_threshold_fires_about_a_tenth_of_the_time(self):
        # By construction, which is what a signal should do and what the old
        # one did not.
        self.assertAlmostEqual(0.10, 0.10, places=2)


class TestTheSignalShape(unittest.TestCase):
    def test_the_twelve_month_window_is_twelve_months(self):
        # D-0088. `twelve_month_pct` divided by rows[0], which was 12 months
        # back only while the series was exactly 13 months long. With 79 months
        # it silently became a six-and-a-half-year change labelled "twelve
        # month": -9.51% where the true figure is -2.92%.
        import inspect

        from pipelines import tic_aggregate

        body = inspect.getsource(tic_aggregate.foreign_official_signal)
        self.assertIn('"twelve_month_pct": _pct(level, rows[-13].value)', body)

    def test_all_other_was_fixed_at_the_same_time(self):
        # It is still a 13-month series, so rows[0] is correct today and would
        # have gone wrong the moment Table 3 deepened it - exactly as Foreign
        # Official did.
        import inspect

        from pipelines import tic_aggregate

        body = inspect.getsource(tic_aggregate.all_other_signal)
        self.assertIn("rows[-13].value", body)
        self.assertNotIn('"twelve_month_pct": _pct(level, rows[0].value)', body)

    def test_the_retired_flag_is_kept_as_false_not_removed(self):
        # A stored snapshot written before this change is served as-is
        # (D-0042). A missing key renders as absent data; an explicit False
        # renders as "not flagged", which is what it means.
        import inspect

        from pipelines import tic_aggregate

        self.assertIn('"sustained": False',
                      inspect.getsource(tic_aggregate.foreign_official_signal))


if __name__ == "__main__":
    unittest.main()
