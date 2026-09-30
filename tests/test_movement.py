"""D-0087 — a movement, and what kind of movement it was.

A change in holdings is not self-explanatory. Japan's July 2026 was **-$12.7bn
of position and +$0.9bn of transactions**: it bought, and the position fell on
price. A column showing only the change says the opposite of what happened, and
that reading is what misranked Japan for as long as dimension 1 existed
(`F-0099`).

The label the reader sees comes from the same rule the scorer applies to
suppress a price-driven magnitude (`A-0021`), so the word and the score cannot
disagree. Gold uses the same component with different words, because tonnes are
a pure quantity: there is no price component to separate, so the kind of
movement is its direction and persistence.
"""
import unittest

from pipelines.tic_state import (
    BOUGHT,
    FLAT,
    FLAT_BN,
    REPRICED,
    SOLD,
    UNKNOWN,
    classify_movement,
    describe_movement,
)


class TestTheRealCases(unittest.TestCase):
    def test_japan_july_is_repriced_not_sold(self):
        # The case this exists for. -$12.7bn of position, +$0.9bn transacted,
        # -$12.1bn valuation.
        self.assertEqual(classify_movement(0.9, -12.1), REPRICED)

    def test_china_july_is_sold(self):
        # 88% of its decline was transactions.
        self.assertEqual(classify_movement(-12.6, -1.7), SOLD)

    def test_germany_july_is_sold(self):
        self.assertEqual(classify_movement(-7.2, -0.5), SOLD)

    def test_a_genuine_buyer_is_bought(self):
        self.assertEqual(classify_movement(19.0, -1.3), BOUGHT)


class TestTheRule(unittest.TestCase):
    def test_valuation_larger_than_transactions_is_repriced(self):
        self.assertEqual(classify_movement(-1.0, -5.0), REPRICED)

    def test_transactions_larger_than_valuation_keeps_its_direction(self):
        self.assertEqual(classify_movement(-5.0, -1.0), SOLD)
        self.assertEqual(classify_movement(5.0, -1.0), BOUGHT)

    def test_equal_magnitudes_are_not_repriced(self):
        # Strictly greater. At parity the transaction is as real as the price
        # move, and calling it "repriced" would suppress a genuine sale.
        self.assertEqual(classify_movement(-5.0, -5.0), SOLD)

    def test_a_rounding_sized_transaction_is_flat(self):
        self.assertEqual(classify_movement(0.0, 0.0), FLAT)
        self.assertEqual(classify_movement(FLAT_BN / 2, 0.0), FLAT)

    def test_no_transaction_but_a_real_price_move_is_repriced(self):
        # The position moved and nobody traded. Precisely not "flat".
        self.assertEqual(classify_movement(0.0, -3.0), REPRICED)

    def test_missing_data_is_unknown_not_flat(self):
        # 16 reporters publish no total, and Table 3 starts in 2020. Reporting
        # "flat" for a country we cannot see is the F-0097 error: absence
        # presented as an observation.
        self.assertEqual(classify_movement(None, None), UNKNOWN)
        self.assertEqual(classify_movement(None, -5.0), UNKNOWN)


class TestItAgreesWithTheScorer(unittest.TestCase):
    def test_repriced_is_the_same_test_dimension_1_suppresses_on(self):
        # A-0021: the magnitude is suppressed when the country bought on net or
        # when valuation exceeded transactions. Both land on REPRICED here, so
        # a reader who sees "repriced" and a score that declines to count the
        # move are reading the same rule.
        for net, val in ((0.9, -12.1), (-1.0, -5.0), (5.0, -1.0)):
            kind = classify_movement(net, val)
            suppressed = net >= 0 or abs(val) > abs(net)
            self.assertEqual(
                kind in (REPRICED, BOUGHT, FLAT), suppressed,
                f"net={net} val={val} -> {kind} but scorer suppressed={suppressed}",
            )


class TestTheDescription(unittest.TestCase):
    def test_it_names_the_figures_behind_the_label(self):
        # F-0097's lesson: "EXITED: Zero US Treasuries" was a fabrication
        # because it asserted a number nobody observed. A label has to carry
        # what it was derived from.
        note = describe_movement(REPRICED, 0.9, -12.1)
        self.assertIn("0.9", note)
        self.assertIn("12.1", note)

    def test_it_points_at_the_scoring_consequence(self):
        self.assertIn("A-0021", describe_movement(REPRICED, 0.9, -12.1))

    def test_unknown_says_why_rather_than_showing_a_number(self):
        note = describe_movement(UNKNOWN)
        self.assertIn("no transaction data", note)
        self.assertNotIn("$", note)

    def test_every_kind_has_a_description(self):
        for kind in (SOLD, BOUGHT, REPRICED, FLAT, UNKNOWN):
            self.assertTrue(describe_movement(kind, -1.0, -0.5))


class TestTheSurfacesUseOneRenderer(unittest.TestCase):
    def test_holdings_and_gold_share_the_component(self):
        # F-0047 is the standing example of two implementations of one idea
        # drifting apart. A second movement cell would drift in its colours and
        # its rounding before it drifted in its logic.
        from pathlib import Path
        root = Path(__file__).resolve().parents[1] / "ui" / "src"
        for tab in ("pages/HoldingsTab.jsx", "pages/GoldReservesTab.jsx"):
            text = (root / tab).read_text(encoding="utf-8")
            self.assertIn("MovementCell", text, tab)

    def test_the_gold_labels_do_not_claim_a_price_component(self):
        # Tonnes are a quantity. "repriced" is meaningless for gold and
        # offering it would invent a distinction the data cannot support.
        from pathlib import Path
        cell = (Path(__file__).resolve().parents[1] / "ui" / "src"
                / "components" / "MovementCell.jsx").read_text(encoding="utf-8")
        self.assertIn("accumulating", cell)
        self.assertIn("selling", cell)


if __name__ == "__main__":
    unittest.main()
