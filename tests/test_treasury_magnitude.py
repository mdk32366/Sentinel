"""D-0084 — dimension 1's magnitude, rebuilt on three findings.

`min(30, abs(month_on_month_pct) * 3)` had three defects:

  `F-0099`  it scaled by proportion of a country's own position, so $1bn of
            selling was worth 0.27 points to Japan and 90.91 to Uruguay.
  `A-0021`  it read HOLDINGS, which move with price. Of 31 countries whose
            position fell over three months, 19 fell for reasons other than
            selling and five were net BUYERS.
  new       it read a single month, and it read the TOTAL position. Japan sold
            **54% of its short-term book** across May and June while its total
            moved 8%, then bought bills back in July. Invisible on both counts.

Every constant is fitted to the real 13-month Table 3 history, and these cases
assert against the observed figures rather than against the constants, so a
change to a constant cannot also change its own justification.
"""
import unittest

from pipelines.composite_stress import (
    MAGNITUDE_CAP,
    SIZE_WEIGHT_MAX,
    ST_MIN_BOOK_BN,
    ST_MIN_DRAWDOWN_PCT,
    treasury_magnitude,
)

GLOBAL = 9248.1  # Grand Total, 2026-07

# Japan, May-July 2026. Total barely moves; the bill book collapses.
JP_TOT = [1209.9, 1143.1, 1116.7, 1103.9]
JP_ST = [153.3, 93.6, 70.5, 80.2]
JP_NET, JP_VAL = -88.6, -14.6

# Argentina: position fell, but it BOUGHT.
AR_TOT = [10.3, 11.0, 10.5, 9.4]
AR_ST = [0.3, 0.4, 0.1, 0.2]
AR_NET, AR_VAL = 0.9, -0.1

# Finland: total ROSE while its bill book fell. Rotation, not liquidation.
FI_TOT = [10.0, 11.0, 11.5, 12.0]
FI_ST = [4.0, 3.5, 3.0, 2.7]
FI_NET, FI_VAL = -0.2, 0.0

# China: a genuine total-position sale, 84% transactions.
CN_TOT = [651.1, 659.3, 633.4, 618.0]
CN_ST = [30.0, 29.0, 25.0, 23.4]
CN_NET, CN_VAL = -28.6, -5.4


def mag(tot, st, net, val, global_total=GLOBAL):
    return treasury_magnitude(tot, st, net, val, global_total)


class TestTheCaseThatPromptedIt(unittest.TestCase):
    def test_japan_scores_on_its_bill_book(self):
        points, detail = mag(JP_TOT, JP_ST, JP_NET, JP_VAL)
        self.assertEqual(detail["tic_magnitude_basis"], "short-term liquidation")
        self.assertAlmostEqual(detail["tic_st_drawdown_pct"], -47.7, places=1)
        # The old formula gave Japan 3.4 for magnitude on a -1.15% month.
        self.assertGreater(points, 25)

    def test_japan_would_score_almost_nothing_on_the_total_alone(self):
        # -8.8% over three months is 13.2 points before weighting. The bill
        # book is what carries it, which is the whole point.
        _, detail = mag(JP_TOT, JP_ST, JP_NET, JP_VAL)
        self.assertAlmostEqual(detail["tic_3m_pct"], -8.8, places=1)

    def test_argentina_scores_nothing_because_it_bought(self):
        # A-0021 option 2. Its position fell 9.1% and its transactions were
        # +$0.9bn, so the fall was not selling.
        points, detail = mag(AR_TOT, AR_ST, AR_NET, AR_VAL)
        self.assertEqual(points, 0.0)
        self.assertTrue(detail["tic_price_driven"])
        self.assertEqual(detail["tic_magnitude_basis"], "none")

    def test_china_still_scores_on_the_total(self):
        # The suppression must not swallow a genuine sale. China's decline was
        # 84% transactions.
        points, detail = mag(CN_TOT, CN_ST, CN_NET, CN_VAL)
        self.assertGreater(points, 0)
        self.assertFalse(detail["tic_price_driven"])


class TestTheShortTermGates(unittest.TestCase):
    def test_a_rotation_into_duration_does_not_score(self):
        # Finland: total +20%, bills -32.5%. It lengthened duration; it did not
        # raise dollars.
        points, detail = mag(FI_TOT, FI_ST, FI_NET, FI_VAL)
        self.assertIsNone(detail["tic_st_drawdown_pct"])
        self.assertEqual(points, 0.0)

    def test_a_net_buyer_does_not_score_on_its_bill_book(self):
        # Brazil (+$1.3bn) and Hong Kong (+$5.2bn) both shrank their bill books
        # while buying overall.
        tot = [100.0, 99.0, 98.0, 97.0]
        st = [20.0, 18.0, 15.0, 14.0]
        _, detail = mag(tot, st, +1.3, -0.2)
        self.assertIsNone(detail["tic_st_drawdown_pct"])

    def test_a_shallow_drawdown_is_rolling_not_liquidation(self):
        tot = [100.0, 99.0, 98.0, 97.0]
        st = [20.0, 19.5, 19.0, 18.5]  # -7.5%, under the threshold
        _, detail = mag(tot, st, -2.0, 0.0)
        self.assertIsNone(detail["tic_st_drawdown_pct"])
        self.assertLess(7.5, ST_MIN_DRAWDOWN_PCT)

    def test_a_tiny_bill_book_halving_is_noise(self):
        # A $0.2bn book going to $0.1bn is a -50% drawdown and means nothing.
        tot = [100.0, 99.0, 98.0, 97.0]
        st = [0.2, 0.15, 0.12, 0.1]
        _, detail = mag(tot, st, -2.0, 0.0)
        self.assertIsNone(detail["tic_st_drawdown_pct"])
        self.assertLess(0.2, ST_MIN_BOOK_BN)

    def test_the_drawdown_is_measured_from_the_peak_not_the_start(self):
        # Japan's bills fell to $70.5bn then recovered to $80.2bn. Measured
        # start-to-end that is -47.7% from the April peak; measured against the
        # previous month it is +13.8% and the liquidation vanishes.
        _, detail = mag(JP_TOT, JP_ST, JP_NET, JP_VAL)
        self.assertLess(detail["tic_st_drawdown_pct"], -40)


class TestTheSizeWeight(unittest.TestCase):
    """F-0099. Proportion leads; size modifies."""

    def test_a_large_holder_is_weighted_up(self):
        big, _ = mag(CN_TOT, CN_ST, CN_NET, CN_VAL, global_total=GLOBAL)
        # Same proportional move, tiny country.
        small_tot = [6.51, 6.59, 6.33, 6.18]
        small, _ = mag(small_tot, [0.3, 0.29, 0.25, 0.23], -0.29, -0.05, GLOBAL)
        self.assertGreater(big, small)

    def test_the_weight_is_capped(self):
        # It modifies, it does not drive. A weight large enough to let dollars
        # outrank proportion would invert the judgement this was built on.
        self.assertLessEqual(SIZE_WEIGHT_MAX, 2.0)
        self.assertGreater(SIZE_WEIGHT_MAX, 1.0)

    def test_no_country_can_exceed_the_magnitude_cap(self):
        # Dimension 1 is 50: magnitude 30 plus persistence 20. A weighted
        # magnitude above 30 would silently raise the dimension's maximum and
        # move every tier boundary.
        extreme = [1000.0, 700.0, 400.0, 100.0]
        points, _ = mag(extreme, [200.0, 100.0, 50.0, 10.0], -800.0, -10.0)
        self.assertLessEqual(points, MAGNITUDE_CAP)

    def test_a_missing_global_total_does_not_crash_or_inflate(self):
        # The aggregate is imported by a different pipeline and may not be there.
        points, _ = mag(CN_TOT, CN_ST, CN_NET, CN_VAL, global_total=None)
        self.assertGreaterEqual(points, 0)


class TestItDegradesQuietly(unittest.TestCase):
    def test_too_little_history_scores_nothing(self):
        # A three-month lens needs four observations. A country newly in Table 3
        # must not score on two points.
        points, detail = mag([100.0, 90.0], [10.0, 5.0], -10.0, 0.0)
        self.assertEqual(points, 0.0)
        self.assertEqual(detail["tic_magnitude_basis"], "none")

    def test_no_short_term_data_still_scores_on_the_total(self):
        # Sixteen reporters publish no bill figure at all.
        points, detail = mag(CN_TOT, [], CN_NET, CN_VAL)
        self.assertGreater(points, 0)
        self.assertEqual(detail["tic_magnitude_basis"], "total position")

    def test_a_rising_position_scores_nothing(self):
        points, _ = mag([90.0, 95.0, 98.0, 100.0], [10.0, 11.0, 12.0, 13.0], 10.0, 0.0)
        self.assertEqual(points, 0.0)

    def test_missing_flow_data_is_treated_as_unverified_not_as_selling(self):
        # Without transactions there is no way to know the fall was selling, and
        # assuming it was is how F-0097 awarded 1,050 points for nothing.
        points, detail = mag(CN_TOT, CN_ST, None, None)
        self.assertEqual(points, 0.0)
        self.assertTrue(detail["tic_price_driven"])


class TestTheExplanationTravelsWithTheScore(unittest.TestCase):
    def test_the_basis_is_named(self):
        # D-0078's principle: a number the reader cannot account for is worse
        # than a number they can argue with.
        for tot, st, net, val, expected in (
            (JP_TOT, JP_ST, JP_NET, JP_VAL, "short-term liquidation"),
            (CN_TOT, [], CN_NET, CN_VAL, "total position"),
            (AR_TOT, AR_ST, AR_NET, AR_VAL, "none"),
        ):
            _, detail = mag(tot, st, net, val)
            self.assertEqual(detail["tic_magnitude_basis"], expected)

    def test_every_detail_key_is_always_present(self):
        # An absent key is filtered to a default by response_model and reads as
        # a real value (F-0079).
        for args in ((JP_TOT, JP_ST, JP_NET, JP_VAL), ([], [], None, None)):
            _, detail = mag(*args)
            for key in ("tic_3m_pct", "tic_st_drawdown_pct",
                        "tic_magnitude_basis", "tic_price_driven"):
                self.assertIn(key, detail)


if __name__ == "__main__":
    unittest.main()
