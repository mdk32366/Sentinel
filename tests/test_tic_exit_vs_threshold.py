"""F-0097 — "not in the major-holders table" was scored as "holds zero".

SLT Table 5 is the **MAJOR** Foreign Holders table. It names exactly 20
countries and folds every other holder into one "All Other" row. Falling off
that list means dropping below the reporting threshold; it does not mean going
to zero.

`no_tic_holdings` was `len(tic_hist) == 0` against a 185-day window, and that
was read as a completed liquidation worth 30-50 points of dimension 1 — the
largest dimension in the model.

Measured against production before the fix: **32 of 49 scored countries** were
on that path, worth **1,050 TIC points**, and **not one had ever reported
zero**:

    DEU $103.1bn   MEX $85.4bn   THA $82.8bn   ESP $73.6bn   AUS $72.3bn
    NLD  $70.0bn   ITA $62.1bn   POL $60.5bn   SWE $50.1bn   CHL $39.6bn
    (most as recently as 2025-12; RUS $13.2bn in 2018)

and fifteen more — KAZ, QAT, PAK, HUN, CZE, IRQ, LBN, LBY, DZA, JOR, KHM, ROU,
SRB, UZB, BLR — had **no TIC row at all** and were each awarded 30 points for a
liquidation that was never recorded. The screen read
"🚨 EXITED: Zero US Treasuries", which was a false statement of fact about 32
sovereigns.

**I made this worse.** `F-0088` moved `tic_latest` from 2025-12 to 2026-07,
which pushed every country whose newest row was December 2025 out of the
185-day window and onto the false-exit path. Fixing the source aggravated a
latent defect in the thing reading it — the same shape as `F-0094`, except that
one was caught before shipping and this one was not. The `A-0017` diagnostic is
what found it.
"""
import unittest
from datetime import datetime, timedelta

import inspect

from pipelines.tic_state import (
    TIC_EXIT_THRESHOLD_BN,
    classify_tic_state,
    describe,
)


class Row:
    """Minimal stand-in for a TimeSeries row."""

    def __init__(self, date, value):
        self.date, self.value = date, value


def classify(tic_hist, tic_last, peak_bn=None):
    """Exercise the REAL classifier, not a copy of it.

    An earlier draft of this file reimplemented the rule here, which would have
    passed while the shipped classifier said something else - and duplicating
    the rule is the defect being fixed (`F-0047`: two implementations of one
    idea, and the endpoint serving the wrong one).

    `peak_bn` defaults to the last holding: a country whose last row is its
    highest. D-0106 makes the peak decide whether a near-zero holding is an
    exit, so the exit cases below pass it explicitly.
    """
    last_bn = float(tic_last.value) if tic_last else None
    peak = peak_bn if peak_bn is not None else last_bn
    return classify_tic_state(bool(tic_hist), last_bn, peak), last_bn


NOW = datetime(2026, 7, 1)


class TestTheFourStates(unittest.TestCase):
    def test_current_data_is_reported(self):
        hist = [Row(NOW, 100.0)]
        self.assertEqual(classify(hist, hist[-1])[0], "reported")

    def test_a_positive_last_holding_with_no_current_row_is_below_threshold(self):
        # Germany. $103.1bn in December 2025, absent from Table 5's 20 named
        # holders because it sits inside "All Other". This is the case that was
        # worth 50 of 50 points as a "completed liquidation".
        state, bn = classify([], Row(datetime(2025, 12, 1), 103.1))
        self.assertEqual(state, "below_threshold")
        self.assertEqual(bn, 103.1)

    def test_a_near_zero_last_holding_after_a_real_one_is_a_genuine_exit(self):
        state, _ = classify([], Row(datetime(2024, 6, 1), 0.0), peak_bn=30.6)
        self.assertEqual(state, "exited")

    def test_no_rows_at_all_is_no_data_not_an_exit(self):
        # Kazakhstan, Qatar, Pakistan and twelve others. Never in the table.
        # Awarding 30 points for an unrecorded liquidation is the starkest form
        # of the defect: there was no observation of any kind to reason from.
        self.assertEqual(classify([], None)[0], "no_data")

    def test_the_states_are_mutually_exclusive(self):
        cases = [
            ([Row(NOW, 5.0)], Row(NOW, 5.0), None),
            ([], Row(datetime(2025, 12, 1), 103.1), None),
            ([], Row(datetime(2024, 6, 1), 0.0), 30.6),
            ([], Row(datetime(2024, 6, 1), 0.5), 0.94),
            ([], None, None),
        ]
        states = [classify(h, l, p)[0] for h, l, p in cases]
        self.assertEqual(len(set(states)), 5, f"states collapsed: {states}")


class TestOnlyARealExitEarnsThePostureScore(unittest.TestCase):
    """The 30/40/50 gold-confirmed bonus is gated on one state."""

    def test_below_threshold_does_not_earn_it(self):
        state, _ = classify([], Row(datetime(2025, 12, 1), 62.1))  # Italy
        self.assertNotEqual(state, "exited")

    def test_no_data_does_not_earn_it(self):
        self.assertNotEqual(classify([], None)[0], "exited")

    def test_russia_at_13bn_is_not_an_exit_either(self):
        # Russia's last reported holding was $13.2bn in December 2018. It
        # reduced heavily and then fell out of the table; it did not reach zero,
        # and "EXITED: Zero US Treasuries" was wrong about Russia too — the one
        # country where the label seemed most defensible.
        state, _ = classify([], Row(datetime(2018, 12, 1), 13.2))
        self.assertEqual(state, "below_threshold")


class TestTheThreshold(unittest.TestCase):
    def test_it_admits_a_rounded_wind_down(self):
        # Table 5 rounds to 0.1bn, so a genuine wind-down lands at 0.0-0.9
        # rather than exactly on zero. A wind-down of something: D-0106 makes
        # the position it wound down from part of the test.
        for v in (0.0, 0.1, 0.9):
            self.assertEqual(classify([], Row(NOW, v), peak_bn=30.6)[0], "exited")

    def test_it_is_far_below_every_real_below_threshold_holding(self):
        # The smallest positive last-reported holding observed in production was
        # Finland at $11.2bn. A threshold anywhere near that would start calling
        # real holders exited.
        self.assertLess(TIC_EXIT_THRESHOLD_BN, 11.2)

    def test_it_is_not_zero(self):
        self.assertGreater(TIC_EXIT_THRESHOLD_BN, 0.0)


class TestAnExitNeedsSomethingToExitFrom(unittest.TestCase):
    """D-0106. Owner ruling, 2026-10-08: whether a country has exited depends
    on whether it ever held Treasuries in the first place. A country that never
    held $1bn cannot have liquidated a position, and calling it EXITED is
    worth a 50-point base score for a liquidation that never happened.

    Production, 2026-10-08: Cyprus (peak $0.94bn), Venezuela ($0.84bn) and
    Liberia ($0.65bn) have never held $1bn. Each still reports, so each is
    `reported` today - and each would have been called `exited` the month it
    dropped out of the TIC tables."""

    def test_a_country_that_never_held_a_billion_never_held(self):
        state, _ = classify([], Row(datetime(2026, 7, 1), 0.5), peak_bn=0.943)  # Cyprus
        self.assertEqual(state, "never_held")

    def test_a_country_that_held_and_wound_down_has_exited(self):
        state, _ = classify([], Row(datetime(2026, 7, 1), 0.2), peak_bn=30.6)
        self.assertEqual(state, "exited")

    def test_the_bar_is_the_same_line_an_exit_falls_below(self):
        line = TIC_EXIT_THRESHOLD_BN
        self.assertEqual(classify([], Row(NOW, 0.1), peak_bn=line)[0], "exited")
        self.assertEqual(classify([], Row(NOW, 0.1), peak_bn=line - 0.01)[0], "never_held")

    def test_the_peak_cannot_be_left_out(self):
        # A default would let a caller skip the question this ruling is about.
        params = inspect.signature(classify_tic_state).parameters
        self.assertIn("peak_reported_bn", params)
        self.assertIs(params["peak_reported_bn"].default, inspect.Parameter.empty)

    def test_never_held_says_what_it_never_held(self):
        line = describe("never_held", 0.5, datetime(2026, 7, 1), peak_bn=0.943)
        self.assertIn("0.9", line)
        self.assertNotIn("xited", line)

    def test_both_call_sites_pass_the_peak(self):
        for path in ("pipelines/composite_stress.py", "pipelines/gold_fetcher.py"):
            with open(path, encoding="utf-8") as fh:
                code = "\n".join(
                    ln for ln in fh.read().splitlines() if not ln.lstrip().startswith("#")
                )
            self.assertIn("peak_reported_holding", code, f"{path} does not read the peak")


class TestTheDefectWouldBeCaughtNow(unittest.TestCase):
    def test_the_production_population_classifies_correctly(self):
        # The 21 countries with a positive last holding, as measured. Every one
        # was scored as a completed liquidation; none may be now.
        observed = {
            "DEU": 103.1, "MEX": 85.4, "THA": 82.8, "ESP": 73.6, "AUS": 72.3,
            "NLD": 70.0, "KWT": 66.1, "ITA": 62.1, "PHL": 62.0, "POL": 60.5,
            "TUR": 52.6, "SWE": 50.1, "CHL": 39.6, "IDN": 32.0, "VNM": 30.7,
            "EGY": 21.0, "DNK": 16.9, "MYS": 14.3, "ZAF": 13.8, "RUS": 13.2,
            "FIN": 11.2,
        }
        for iso, bn in observed.items():
            state, _ = classify([], Row(datetime(2025, 12, 1), bn))
            self.assertEqual(state, "below_threshold", f"{iso} at ${bn}bn")

    def test_the_fifteen_with_no_rows_classify_as_no_data(self):
        for _ in range(15):
            self.assertEqual(classify([], None)[0], "no_data")

    def test_the_schema_declares_the_new_fields(self):
        # F-0079: response_model is a filter, not a validator. A stripped
        # tic_state would leave the UI unable to tell a real liquidation from a
        # country that merely fell below the reporting threshold — which is the
        # distinction this whole finding is about.
        from api.schemas import CompositeCountry

        for field in ("tic_state", "tic_last_reported_bn", "tic_last_reported_date"):
            self.assertIn(field, CompositeCountry.model_fields)

    def test_the_signal_names_the_figure_rather_than_claiming_zero(self):
        # "EXITED: Zero US Treasuries" for a country holding $103.1bn was a
        # false statement of fact. The replacement must carry the number and
        # its date, because that is what makes it checkable.
        line = describe("below_threshold", 103.1, datetime(2025, 12, 1))
        self.assertIn("103.1", line)
        self.assertIn("Dec 2025", line)
        self.assertNotIn("Zero", line)
        self.assertNotIn("EXITED", line.upper())

    def test_a_real_exit_still_says_so(self):
        self.assertIn("xited", describe("exited", 0.0, datetime(2024, 6, 1)))

    def test_no_data_does_not_imply_a_holding_of_any_size(self):
        line = describe("no_data", None, None)
        self.assertIn("No TIC data", line)

    def test_both_call_sites_use_the_shared_classifier(self):
        # composite_stress.py (dimension 1, 30-50 points) and gold_fetcher.py
        # (CROSS-ASSET, 50-90 plus multipliers) each had their own copy of
        # `len(tic_hist) == 0`. One rule now, imported by both.
        for path in ("pipelines/composite_stress.py", "pipelines/gold_fetcher.py"):
            with open(path, encoding="utf-8") as fh:
                lines = fh.read().splitlines()
            # Comments stripped before matching. Both files now EXPLAIN the old
            # `len(tic_hist) == 0` rule in prose, and a whole-file substring
            # search matches that explanation - a test that fails on its own
            # documentation. Fourth time today I have written an assertion that
            # matched my own comment; scoping to code is the fix that sticks.
            code = "\n".join(
                ln for ln in lines if not ln.lstrip().startswith("#")
            )
            self.assertIn("classify_tic_state", code, f"{path} does not use it")
            self.assertNotIn(
                "len(tic_hist) == 0", code, f"{path} still has its own copy"
            )


if __name__ == "__main__":
    unittest.main()
