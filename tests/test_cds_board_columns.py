"""D-0063 / F-0080: the board columns the fetcher used to discard.

The World Government Bonds board publishes, per sovereign:

    Country | S&P | 5Y CDS | Var 1m | Var 6m | PD (*) | Date

Only the spread and the date were read. Everything else arrived on every
fetch, every day, and was thrown away — including the source's own implied
probability of default and its six-month change, which predates this
project's CDS ingest entirely.
"""
import io
import unittest
from decimal import Decimal
from pathlib import Path

from pipelines.cds_fetcher import CdsQuote, _parse_pct, parse_wgb_cds_table

FIXTURE = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "cds" / "wgb_5y_board.html"


def quotes():
    return parse_wgb_cds_table(io.open(FIXTURE, encoding="utf-8").read())


class ParsingAPercentageCell(unittest.TestCase):
    def test_the_forms_the_board_actually_uses(self):
        self.assertEqual(_parse_pct("+13.76 %"), Decimal("13.76"))
        self.assertEqual(_parse_pct("-16.17 %"), Decimal("-16.17"))
        self.assertEqual(_parse_pct("0.12 %"), Decimal("0.12"))
        self.assertEqual(_parse_pct("100.00 %"), Decimal("100.00"))

    def test_an_absent_cell_is_none_rather_than_zero(self):
        # Zero is a real value for a change column. Confusing "no data" with
        # "no change" would report a frozen feed as a stable market.
        for raw in (None, "", "   ", "-", "--", "n/a"):
            with self.subTest(raw=raw):
                self.assertIsNone(_parse_pct(raw))

    def test_junk_is_none_rather_than_an_exception(self):
        self.assertIsNone(_parse_pct("about 4"))


class TheExtraColumnsAreRead(unittest.TestCase):
    def test_every_quote_carries_them(self):
        parsed = quotes()
        self.assertGreater(len(parsed), 0)
        for q in parsed:
            with self.subTest(country=q.country):
                self.assertIsNotNone(q.implied_pd_pct, "no implied PD")
                self.assertIsNotNone(q.var_1m_pct, "no 1m change")
                self.assertIsNotNone(q.var_6m_pct, "no 6m change")
                self.assertTrue(q.rating, "no rating")

    def test_the_values_match_the_board(self):
        by_country = {q.country: q for q in quotes()}
        germany = by_country["Germany"]
        self.assertEqual(germany.spread_bps, Decimal("6.99"))
        self.assertEqual(germany.implied_pd_pct, Decimal("0.12"))
        self.assertEqual(germany.var_1m_pct, Decimal("-1.96"))
        self.assertEqual(germany.var_6m_pct, Decimal("-9.10"))
        self.assertEqual(germany.rating, "AAA")

    def test_a_negative_change_keeps_its_sign(self):
        # Tightening and widening are opposite signals. Losing the sign would
        # turn a recovering sovereign into a deteriorating one.
        for q in quotes():
            if q.country == "Germany":
                self.assertLess(q.var_6m_pct, 0)

    def test_a_board_without_the_columns_still_parses(self):
        # The extra columns are optional by construction: a source that drops
        # them should cost us the extras, not the spread.
        minimal = """
        <table>
        <thead><tr><th>Country</th><th>5 Years Credit Default Swaps</th><th>Date</th></tr></thead>
        <tbody><tr>
          <td sorttable_customkey="Germany">Germany</td>
          <td sorttable_customkey="9.64">9.64</td>
          <td sorttable_customkey="2026-09-29">29 Sep</td>
        </tr></tbody></table>
        """
        parsed = parse_wgb_cds_table(minimal)
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0].spread_bps, Decimal("9.64"))
        self.assertIsNone(parsed[0].implied_pd_pct)


class ImpliedPdIsNotIndependentInformation(unittest.TestCase):
    """F-0080.

    Measured across all 30 names on the live board, implied PD is the spread
    times a constant 1/60 — Sweden 7.36bps/0.12%, Germany 9.64/0.16, Brazil
    124.90/2.08, Egypt 307.29/5.12. It is a rescaling, not a second opinion.

    It is carried for READABILITY — "a 2.18% chance of default" means
    something to a reader and "130.86bps" does not — and it must never be
    scored, because scoring it would double-count the level band exactly.
    """

    RATIO = Decimal("0.0167")

    def test_pd_tracks_the_spread_at_a_fixed_ratio(self):
        for q in quotes():
            if not q.implied_pd_pct or not q.spread_bps:
                continue
            with self.subTest(country=q.country):
                ratio = q.implied_pd_pct / q.spread_bps
                # Generous band: the board rounds PD to two decimals, which is
                # coarse at single-digit spreads.
                self.assertAlmostEqual(float(ratio), float(self.RATIO), delta=0.002)

    def test_the_scorer_does_not_read_the_pd_series(self):
        # The guard that matters. If someone adds PD to get_cds_score it will
        # double-count the level band, and this is what says so.
        source = (Path(__file__).resolve().parents[1]
                  / "pipelines" / "composite_stress.py").read_text(encoding="utf-8")
        self.assertNotIn("_CDS_PD", source)


class TheQuoteDefaultsStayBackwardCompatible(unittest.TestCase):
    def test_a_quote_can_still_be_built_from_spread_and_date_alone(self):
        # Existing tests and any caller predating D-0063 construct CdsQuote
        # positionally. The new fields are optional and must stay so.
        from datetime import date
        q = CdsQuote(country="Germany", spread_bps=Decimal("9.64"), as_of=date(2026, 9, 29))
        self.assertIsNone(q.implied_pd_pct)
        self.assertIsNone(q.var_6m_pct)
        self.assertEqual(q.tenor, "5Y")


if __name__ == "__main__":
    unittest.main()
