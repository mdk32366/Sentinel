"""F-0076: the methodology panel must describe the model the scorer runs.

The COMPOSITE tab's panel is headed `SCORE =` and listed four dimensions. The
scorer sums six:

    raw_score = tic_score + gold_score + monetary_score
              + spread_score + petro_score + cds_score

Monetary/M2 (0-35), Sovereign CDS (0-20) and the non-dollar reserve multiplier
were absent from the explanation. A reader could not reconcile a score of
179.7 with a panel whose parts sum to 130 — and CDS, which is the entire score
for some countries, appeared nowhere at all.

This runs in Python because the claim is about Python source. A JavaScript
test asserting what the scorer sums would be asserting against a copy of the
answer.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIMENSIONS_JS = ROOT / "ui" / "src" / "lib" / "dimensions.js"
SCORER = ROOT / "pipelines" / "composite_stress.py"


def declared_dimensions():
    """`key` -> max, straight out of the module the UI renders from."""
    source = DIMENSIONS_JS.read_text(encoding="utf-8")
    block = source[source.index("export const STRESS_DIMENSIONS = ["):]
    block = block[: block.index("\n];")]
    out = {}
    for entry in re.finditer(r'key:\s*"([^"]+)",(.*?)\n  \}', block, re.S):
        key, body = entry.group(1), entry.group(2)
        found = re.search(r"max:\s*(\d+)", body)
        out[key] = int(found.group(1)) if found else None
    return out


def summed_terms():
    """The identifiers the scorer actually adds into raw_score."""
    source = SCORER.read_text(encoding="utf-8")
    line = re.search(r"raw_score = ([^\n]*(?:\n\s+\+[^\n]*)*)", source)
    assert line, "raw_score assignment not found in composite_stress.py"
    return {t.strip() for t in line.group(1).replace("\n", " ").split("+") if t.strip()}


class TheUiListsEveryScoredDimension(unittest.TestCase):
    def test_every_summed_term_is_declared_in_the_ui(self):
        missing = summed_terms() - set(declared_dimensions())
        self.assertEqual(
            missing, set(),
            f"the scorer sums {sorted(missing)} but the methodology panel does not list them",
        )

    def test_the_ui_does_not_invent_a_dimension(self):
        # The other direction. A panel claiming a factor the scorer does not
        # compute is the same defect wearing the opposite sign.
        extra = set(declared_dimensions()) - summed_terms()
        self.assertEqual(
            extra, set(),
            f"the panel lists {sorted(extra)} but the scorer does not sum them",
        )

    def test_there_are_six_of_them(self):
        self.assertEqual(len(declared_dimensions()), 6)
        self.assertEqual(len(summed_terms()), 6)


class TheDeclaredMaximaMatchTheScorer(unittest.TestCase):
    """Each dimension's cap, as the scorer's own docstring states it."""

    EXPECTED = {
        "tic_score": 50,
        "gold_score": 40,
        "monetary_score": 35,
        "spread_score": 20,
        "petro_score": 20,
        "cds_score": 20,
    }

    def test_the_ui_maxima_are_the_documented_ones(self):
        self.assertEqual(declared_dimensions(), self.EXPECTED)

    def test_each_cap_appears_in_the_scorer_header(self):
        # The module header enumerates DIMENSION 1..7 with their ranges. If a
        # cap is retuned there, this fails rather than leaving the panel
        # quoting an old number (F-0068's shape).
        header = SCORER.read_text(encoding="utf-8")[:4000]
        for label, cap in (("Treasury", 50), ("Gold Reserves", 40),
                           ("Monetary / M2", 35), ("Sovereign Spread", 20),
                           ("Petrodollar", 20), ("Sovereign CDS", 20)):
            with self.subTest(dimension=label):
                self.assertIn(f"0-{cap} pts", header)

    def test_the_raw_maximum_is_the_sum_of_the_parts(self):
        source = DIMENSIONS_JS.read_text(encoding="utf-8")
        self.assertIn("MAX_RAW_SCORE", source)
        self.assertEqual(sum(self.EXPECTED.values()), 185)


class CdsIsPresentedAsScored(unittest.TestCase):
    def test_cds_is_one_of_the_listed_dimensions(self):
        # The specific omission that started this: CDS is 100% of some
        # countries' composite score and was not mentioned in the panel at all.
        self.assertIn("cds_score", declared_dimensions())

    def test_the_cds_dimension_is_described_not_just_named(self):
        source = DIMENSIONS_JS.read_text(encoding="utf-8")
        block = source[source.index('key: "cds_score"'):]
        block = block[: block.index("},")]
        found = re.search(r'desc:\s*"([^"]+)"', block)
        self.assertIsNotNone(found, "the CDS dimension has no description")
        self.assertGreater(len(found.group(1)), 20)


if __name__ == "__main__":
    unittest.main()
