"""F-0092 — dimension 3 scored whatever the newest year was, however old.

Countries drop out of World Bank broad-money reporting and do not come back.
Newest year available per country, as served in production:

    CAN 2008 (14.9%)   CHE 2016 (3.3%)   SAU 2017 (0.2%)
    RUS 2020 (16.7%)   SGP 2020 (13.2%)  PHL 2022 (7.8%)   TUR 2025 (37.9%)

Russia was earning 10 points from a 2020 figure, displayed beside Turkey's 2025
figure with nothing marking the difference. Canada's 2008 figure sat a tenth of
a point under the 15% first rung - the only reason an eighteen-year-old number
was not scoring.

The source-level watchdog cannot see this: `money_supply` as a source IS
current, because 2025 data exists for the countries that still report. The
staleness is per country.
"""
import re
import unittest
from datetime import datetime

from pipelines.composite_stress import MAX_M2_DATA_AGE_YEARS

THIS_YEAR = datetime.utcnow().year


def is_stale(year, now_year=THIS_YEAR):
    """The rule as the scorer applies it."""
    return year < now_year - MAX_M2_DATA_AGE_YEARS


class TestTheCutoffAdmitsWhatItShould(unittest.TestCase):
    def test_the_newest_year_the_world_bank_offers_is_admitted(self):
        # The World Bank publishes year Y around the middle of Y+1, so in 2026
        # the newest year anywhere is 2025. A cutoff that excluded it would
        # zero the whole dimension for every country at once.
        self.assertFalse(is_stale(THIS_YEAR - 1))

    def test_one_fully_missed_release_is_admitted(self):
        # Slack for a country that reports late or a release that slips a year.
        self.assertFalse(is_stale(THIS_YEAR - 2))
        self.assertFalse(is_stale(THIS_YEAR - 3))

    def test_two_missed_releases_are_not(self):
        self.assertTrue(is_stale(THIS_YEAR - 4))

    def test_the_real_laggards_are_all_excluded(self):
        # The cases that prompted this, asserted by year rather than by
        # hardcoded age so the file does not rot in January.
        for year in (2008, 2016, 2017, 2020, 2022):
            self.assertTrue(is_stale(year, now_year=2026), f"{year} still scores")

    def test_the_countries_that_still_report_are_unaffected(self):
        for year in (2023, 2024, 2025):
            self.assertFalse(is_stale(year, now_year=2026), f"{year} lost")


class TestTheCutoffIsRelativeNotAbsolute(unittest.TestCase):
    def test_it_moves_with_the_calendar(self):
        # A hardcoded ">= 2023" would silently start admitting five- and then
        # six-year-old data as the years passed, which is the same class of rot
        # as a threshold nobody re-derives (F-0089).
        self.assertTrue(is_stale(2023, now_year=2030))
        self.assertFalse(is_stale(2023, now_year=2026))


class TestTheFigureIsStillReported(unittest.TestCase):
    """Excluded from scoring is not the same as hidden.

    "Canada last reported broad money in 2008" is a fact worth seeing. The
    defect was scoring it, not showing it.
    """

    def test_the_scorer_still_carries_the_value_and_the_year(self):
        with open("pipelines/composite_stress.py", encoding="utf-8") as fh:
            body = fh.read()
        # The result dict must emit all three, or the UI cannot distinguish
        # "no data" from "old data" - and those call for opposite reactions.
        for field in ('"m2_growth_pct"', '"m2_year"', '"m2_stale"'):
            self.assertIn(field, body, f"{field} is not returned")

    def test_the_flag_is_declared_on_the_response_model(self):
        # F-0079: response_model is a filter, not a validator. An undeclared
        # field is stripped in silence, which is how the entire CDS dimension
        # once vanished between the scorer and the screen. A stripped
        # `m2_stale` would leave the UI showing a stale figure as current.
        from api.schemas import CompositeCountry

        self.assertIn("m2_stale", CompositeCountry.model_fields)

    def test_the_signal_text_says_it_did_not_score(self):
        # Otherwise a reader adds up the narrative and gets a different number
        # from the score.
        with open("pipelines/composite_stress.py", encoding="utf-8") as fh:
            body = fh.read()
        m = re.search(r'suffix = (.+?) if m2_stale else ""', body)
        self.assertIsNotNone(m, "the signal does not distinguish a stale figure")
        self.assertIn("score", m.group(1).lower())


class TestTheGuardCannotBeSkipped(unittest.TestCase):
    def test_scoring_is_inside_the_freshness_branch(self):
        # D-0027: a guard that stands aside is not a guard. The three rungs
        # must be nested under `if not m2_stale`, not merely followed by it.
        with open("pipelines/composite_stress.py", encoding="utf-8") as fh:
            lines = fh.read().splitlines()

        guard = next(
            (i for i, ln in enumerate(lines) if "if not m2_stale:" in ln), None
        )
        self.assertIsNotNone(guard, "the freshness branch is gone")
        guard_indent = len(lines[guard]) - len(lines[guard].lstrip())

        rungs = [
            i for i, ln in enumerate(lines)
            if re.search(r"monetary_score = (35|20|10)\b", ln)
        ]
        self.assertEqual(len(rungs), 3, "expected three scoring rungs")
        for i in rungs:
            self.assertGreater(i, guard, "a rung scores before the check")
            indent = len(lines[i]) - len(lines[i].lstrip())
            self.assertGreater(
                indent, guard_indent,
                f"line {i + 1} scores outside the freshness branch",
            )


if __name__ == "__main__":
    unittest.main()
