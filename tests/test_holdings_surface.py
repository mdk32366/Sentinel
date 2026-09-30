"""D-0085 — HOLDINGS changed under its own feet, and had to be told.

Nobody edited the tab today. `D-0081` imported SLT Table 3 into the same
`TIC_UST_HOLDINGS` metric the tab reads, and the surface silently went from 20
countries to 60 with every percentage recomputed. Three things then needed
fixing, and all three are the same mistake in different places: **a number
presented as something it is not.**

  1. "Total Foreign Holdings" was the SUM OF THE ROWS, $8,710.3bn, while the
     published total is $9,248.1bn — understated by $537.8bn.
  2. `percent_of_total` divided by that sum, so Japan read 12.7% of the rows we
     happen to list rather than 11.9% of all foreign holdings.
  3. Sixteen reporters that publish only a long-term figure were **absent
     entirely** — Poland, Egypt, Hungary, Romania, Serbia, Ukraine, Lebanon,
     Greece — which reads as "not a holder". That is `F-0097` in a new place.
"""
import unittest
from unittest import mock

from fastapi.routing import APIRoute

from api.routes import router
from api.schemas import HoldingItem, HoldingsResponse


def holdings_route():
    return next(
        r for r in router.routes
        if isinstance(r, APIRoute) and r.path == "/api/holdings" and "GET" in r.methods
    )


class TestTheResponseDeclaresTheNewFacts(unittest.TestCase):
    """`response_model` is a filter (F-0079): undeclared is deleted, silently."""

    def test_the_published_total_is_declared(self):
        self.assertIn("grand_total_billions_usd", HoldingsResponse.model_fields)

    def test_coverage_is_declared(self):
        # Without it a reader cannot tell whether the rows are most of the total
        # or a fraction of it.
        self.assertIn("coverage_pct", HoldingsResponse.model_fields)

    def test_the_counts_are_declared(self):
        # country_count was returning null before D-0085 because nothing set it.
        for field in ("country_count", "long_term_only_count"):
            self.assertIn(field, HoldingsResponse.model_fields)

    def test_the_long_term_flag_is_declared_on_each_row(self):
        # A stripped flag would render every long-term figure as a total, which
        # is the measure-substitution this whole finding is about.
        self.assertIn("long_term_only", HoldingItem.model_fields)

    def test_the_flag_defaults_to_false_not_true(self):
        # 60 of 76 rows are real totals. A default of True would mislabel them.
        self.assertIs(HoldingItem.model_fields["long_term_only"].default, False)


class TestTheEndpointLogic(unittest.TestCase):
    """Read from the source: these are properties of the query, not of a fixture."""

    def setUp(self):
        import inspect
        self.body = inspect.getsource(holdings_route().endpoint)

    def test_the_published_grand_total_is_read_not_summed(self):
        # From the TIC_GRAND_TOTAL series (D-0079), a global row with a NULL
        # country, rather than by adding up the countries.
        self.assertIn('filter_by(code="TIC_GRAND_TOTAL")', self.body)
        self.assertIn("country_id.is_(None)", self.body)

    def test_the_grand_total_is_taken_from_the_same_month(self):
        # A grand total from a different month would make coverage nonsense and
        # would move every percentage. F-0087's shape: two figures, two dates.
        self.assertIn("TimeSeries.date == as_of", self.body)

    def test_percentages_use_the_published_total_when_available(self):
        self.assertIn("denominator = grand_total or listed_total", self.body)

    def test_it_falls_back_to_the_listed_sum(self):
        # TIC_GRAND_TOTAL is imported by a different pipeline and may be absent
        # on a fresh database. The tab must still render.
        self.assertIn("or listed_total", self.body)

    def test_long_term_only_countries_are_added_not_dropped(self):
        self.assertIn('filter_by(code="TIC_UST_LT_HOLDINGS")', self.body)
        self.assertIn('"long_term_only": True', self.body)

    def test_a_country_with_a_total_is_not_duplicated_by_its_long_term_row(self):
        # Every country has a long-term figure; only 16 lack a total. Adding all
        # of them would list Japan twice, once at $1,103.9bn and once at
        # $1,023.8bn.
        self.assertIn("if r[0] not in have", self.body)

    def test_the_single_country_query_does_not_gain_extra_rows(self):
        # /api/holdings?country_iso=JPN must return that country, not a list.
        self.assertIn("and not country_iso", self.body)


class TestTheNumbersItWouldProduce(unittest.TestCase):
    """The real figures, as arithmetic rather than as a live call."""

    LISTED = 8710.3
    GRAND = 9248.1
    JAPAN = 1103.9

    def test_the_listed_sum_is_not_the_published_total(self):
        # The gap is the point: $537.8bn of holdings sit in countries Table 3
        # does not name.
        self.assertNotAlmostEqual(self.LISTED, self.GRAND, delta=1.0)
        self.assertGreater(self.GRAND - self.LISTED, 500)

    def test_coverage_is_most_but_not_all(self):
        coverage = self.LISTED / self.GRAND * 100
        self.assertGreater(coverage, 90)
        self.assertLess(coverage, 100)

    def test_japans_share_falls_when_measured_against_the_real_total(self):
        # 12.7% of the rows listed, 11.9% of all foreign holdings. The second is
        # a fact about the world; the first is a fact about our query.
        against_listed = self.JAPAN / self.LISTED * 100
        against_published = self.JAPAN / self.GRAND * 100
        self.assertGreater(against_listed, against_published)
        self.assertAlmostEqual(against_published, 11.9, places=1)


class TestTheTabDoesNotMixMeasures(unittest.TestCase):
    def setUp(self):
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        self.tab = (root / "ui" / "src" / "pages" / "HoldingsTab.jsx").read_text(
            encoding="utf-8"
        )

    def test_concentration_excludes_long_term_only_countries(self):
        # A long-term figure summed with totals produces a concentration
        # percentage of two different things.
        self.assertIn("r.long_term_only", self.tab)
        self.assertIn("comparable", self.tab)

    def test_the_headline_uses_the_published_total(self):
        self.assertIn("grandTotal", self.tab)
        self.assertIn("Total Foreign Holdings", self.tab)

    def test_the_rows_say_when_a_figure_is_long_term_only(self):
        self.assertIn("LT only", self.tab)

    def test_the_count_tile_separates_the_two_kinds(self):
        self.assertIn("long-term only", self.tab)


if __name__ == "__main__":
    unittest.main()
