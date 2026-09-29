"""The MARKETS tooltips must not lie about what feeds the stress score.

Twelve series sit on a board titled sovereign stress. Three of them are read
by a scorer; the other nine are context. Each card's tooltip says which it is,
and `D-0016` exists because the 30Y's presence on that board looked like a
factor until someone ruled that it was not.

A tooltip is prose and prose goes stale silently. The `scored` flag beside it
is structured, and this is what stops the flag going stale: if someone adds
`DGS30` to `stress_score_v2.py`, the card still claiming "Not scored" fails
here rather than misinforming a reader indefinitely.

The check runs in Python deliberately. The claim is about Python source, and
a JavaScript test asserting what a Python module reads would be asserting
against a copy of the answer.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONSTANTS = ROOT / "ui" / "src" / "lib" / "constants.js"

# The scorer whose factors are the v2 stress index.
V2_SCORER = ROOT / "pipelines" / "stress_score_v2.py"
# The per-country composite. Reads DGS10 as the sovereign-spread benchmark and
# oil for the petrodollar factor, and carries spot gold as CONTEXT only.
COMPOSITE_SCORER = ROOT / "pipelines" / "composite_stress.py"


def parse_metrics():
    """`code` -> {scored, tip, stressRole} straight out of constants.js.

    Deliberately a regex rather than a JS runtime: the point is to read what
    the frontend actually ships, without a build step standing between this
    test and the file.
    """
    source = CONSTANTS.read_text(encoding="utf-8")
    block = source[source.index("export const METRICS = ["):]
    block = block[: block.index("\n];")]

    metrics = {}
    for entry in re.finditer(
        r'\{\s*code:\s*"([^"]+)",(.*?)\n  \}', block, re.S
    ):
        code, body = entry.group(1), entry.group(2)
        scored = re.search(r"scored:\s*(true|false)", body)
        metrics[code] = {
            "scored": scored.group(1) == "true" if scored else None,
            "tip": _string_field(body, "tip"),
            "stressRole": _string_field(body, "stressRole"),
        }
    return metrics


def _string_field(body: str, name: str):
    """The value of a `name: "..."` property.

    Matches the string LITERAL rather than anchoring on whatever follows it.
    The first version required a trailing `",` and a newline, which every
    field has except the last one in each entry — so `stressRole` parsed as
    None for all twelve and the file looked as though it carried no roles at
    all. Anchoring a parser on a neighbour's punctuation is how that happens.
    """
    match = re.search(name + r':\s*"((?:[^"\\]|\\.)*)"', body)
    return match.group(1) if match else None


def reads_code(path: Path, code: str) -> bool:
    """Does this module name the metric code as a string literal?"""
    return f'"{code}"' in path.read_text(encoding="utf-8")


class MarketsTooltipsExist(unittest.TestCase):
    def test_all_twelve_cards_carry_an_explanation(self):
        metrics = parse_metrics()
        self.assertEqual(len(metrics), 12, "MARKETS should carry twelve cards")

        for code, metric in metrics.items():
            with self.subTest(code=code):
                self.assertIsNotNone(metric["tip"], f"{code} has no tip")
                self.assertIsNotNone(metric["stressRole"], f"{code} has no stressRole")
                self.assertIsNotNone(metric["scored"], f"{code} has no scored flag")
                self.assertGreater(len(metric["tip"]), 120, f"{code}'s tip is too thin")


class ScoredFlagsMatchTheScorers(unittest.TestCase):
    """The flag and the code must agree, in both directions."""

    def test_every_scored_card_is_read_by_a_scorer(self):
        for code, metric in parse_metrics().items():
            if not metric["scored"]:
                continue
            with self.subTest(code=code):
                self.assertTrue(
                    reads_code(V2_SCORER, code) or reads_code(COMPOSITE_SCORER, code),
                    f"{code} is marked scored but neither scorer names it",
                )

    def test_no_unscored_card_is_read_by_the_v2_scorer(self):
        # The direction that actually protects a reader. A card saying
        # "Not scored" while the v2 scorer weights it is a false statement on
        # screen, and nothing else would catch it.
        for code, metric in parse_metrics().items():
            if metric["scored"]:
                continue
            with self.subTest(code=code):
                self.assertFalse(
                    reads_code(V2_SCORER, code),
                    f"{code}'s tooltip says it is not scored, but "
                    f"stress_score_v2.py reads it",
                )

    def test_the_scored_set_is_exactly_the_three_expected(self):
        scored = sorted(c for c, m in parse_metrics().items() if m["scored"])
        self.assertEqual(scored, ["DCOILWTICO", "DGS10", "DGS2"])

    def test_d0016_the_30y_is_displayed_and_not_weighted(self):
        # T-0016 already asserts the scorer ignores a 30Y level. This asserts
        # the UI says so, which is the half a reader can see.
        dgs30 = parse_metrics()["DGS30"]
        self.assertFalse(dgs30["scored"])
        self.assertIn("D-0016", dgs30["stressRole"])
        self.assertIn("Not scored", dgs30["stressRole"])

    def test_gold_spot_is_context_and_says_which_gold_signal_is_scored(self):
        # The distinction is easy to get wrong: the composite DOES have a gold
        # factor, but it scores reserve TONNAGE. Spot price is context.
        gold = parse_metrics()["GOLD_SPOT_USD"]
        self.assertFalse(gold["scored"])
        self.assertIn("tonnage", gold["stressRole"])


class TooltipsDescribeTheRealMechanism(unittest.TestCase):
    def test_the_yield_curve_pair_names_the_other_leg(self):
        # DGS10 - DGS2 is one factor. A reader looking at either card should
        # be able to find the other.
        metrics = parse_metrics()
        self.assertIn("yield-curve factor", metrics["DGS10"]["stressRole"])
        self.assertIn("DGS10 - DGS2", metrics["DGS2"]["stressRole"])

    def test_the_inversion_threshold_matches_the_scorer(self):
        # calculate_yield_curve_stress pins at 100 when the spread is -1.0.
        source = V2_SCORER.read_text(encoding="utf-8")
        self.assertIn("if spread < -1.0:", source)
        self.assertIn("-1.00pp", parse_metrics()["DGS2"]["stressRole"])

    def test_the_oil_volatility_bounds_match_the_scorer(self):
        # calculate_volatility_stress: 1% daily sigma = 0, 5%+ = 100.
        source = V2_SCORER.read_text(encoding="utf-8")
        self.assertIn("if wti_volatility >= 5.0:", source)
        role = parse_metrics()["DCOILWTICO"]["stressRole"]
        self.assertIn("5%+ = 100", role)
        self.assertIn("1% daily sigma = 0", role)


if __name__ == "__main__":
    unittest.main()


class MonthlyCardsSayTheyAreMonthly(unittest.TestCase):
    """A-0013 / D-0057.

    The twelve cards sit in one grid with no visual distinction between a
    daily series and a monthly one, so a monthly card reads as a stale daily
    one. That is how the question arrived: "is there no real time ticker on
    Fed Funds? My latest data is July 31."

    Two of the twelve are still monthly. They disclose it in their own text,
    which is the only place a reader can find out.
    """

    MONTHLY = {"CPIAUCSL", "M2SL"}

    def test_the_monthly_series_disclose_their_cadence(self):
        metrics = parse_metrics()
        for code in self.MONTHLY:
            with self.subTest(code=code):
                tip = metrics[code]["tip"].lower()
                self.assertIn(
                    "monthly", tip,
                    f"{code} is a monthly series and its tooltip does not say so",
                )

    def test_no_other_card_claims_to_be_monthly(self):
        # The inverse. A daily card describing itself as monthly is the same
        # failure pointing the other way, and the Fed Funds card spent one
        # commit in exactly that state.
        #
        # Scoped to the FIRST SENTENCE, which is where a card says what it is.
        # A blunter check fails on the Fed Funds tip, which legitimately
        # mentions the monthly average further down to explain what D-0057
        # changed — and a test that forbids explaining a fix is a test that
        # makes the tooltips worse.
        for code, metric in parse_metrics().items():
            if code in self.MONTHLY:
                continue
            with self.subTest(code=code):
                opening = metric["tip"].split(".")[0].lower()
                self.assertNotIn(
                    "monthly", opening,
                    f"{code} is a daily series but introduces itself as monthly",
                )


class FedFundsIsTheDailySeries(unittest.TestCase):
    """D-0057.

    The Fed Funds card showed FRED's FEDFUNDS — the MONTHLY AVERAGE. On
    2026-09-29 that read **3.63%** while the effective rate was **3.88%**: not
    merely a month behind, but 25bp wrong about where policy actually sits, on
    a board whose fiscal calculator is denominated in yields.

    The card now reads DFF, the daily effective rate. FEDFUNDS is still
    ingested — it is what most published analysis quotes — but it is not what
    the UI shows.
    """

    def test_the_card_reads_the_daily_series(self):
        self.assertIn("DFF", parse_metrics())
        self.assertNotIn("FEDFUNDS", parse_metrics())

    def test_the_daily_series_is_actually_ingested(self):
        # A card reading a code no pipeline fetches renders a permanent dash,
        # which is the quietest possible way to break this.
        fetcher = (ROOT / "pipelines" / "fred_fetcher.py").read_text(encoding="utf-8")
        self.assertTrue(
            '"DFF"' in fetcher,
            "the Fed Funds card reads DFF but fred_fetcher.py does not fetch it",
        )

    def test_the_monthly_average_is_still_collected(self):
        fetcher = (ROOT / "pipelines" / "fred_fetcher.py").read_text(encoding="utf-8")
        self.assertTrue(
            '"FEDFUNDS"' in fetcher,
            "FEDFUNDS stopped being ingested - D-0057 kept it deliberately",
        )

    def test_every_code_the_ui_shows_is_one_a_pipeline_fetches(self):
        # Generalised from the above, because the specific failure - a card
        # pointing at a code nothing ingests - is not unique to Fed Funds.
        fetcher = (ROOT / "pipelines" / "fred_fetcher.py").read_text(encoding="utf-8")
        gold = (ROOT / "pipelines" / "gold_price_fetcher.py").read_text(encoding="utf-8")
        for code in parse_metrics():
            with self.subTest(code=code):
                self.assertTrue(
                    f'"{code}"' in fetcher or f'"{code}"' in gold,
                    f"the {code} card has no pipeline fetching it",
                )
