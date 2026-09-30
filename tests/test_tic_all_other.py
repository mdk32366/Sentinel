"""D-0079 / A-0019 option 2 — the "All Other" aggregate, and the line it must not cross.

SLT Table 5 names twenty holders and folds every other foreign holder into one
**"All Other"** row. `F-0097` established that a country absent from the table is
inside that row rather than at zero, and `D-0078` disclosed that as a gap. This
closes the other half: the row is published, so the non-reporters' *combined*
position is knowable even though no individual position is.

**The constraint these cases exist for.** All Other covers roughly a hundred
holders - sovereign wealth funds, private institutions, and the 28 scored
countries outside the table. A -1% move says *someone* reduced. Turning that into
28 country-level findings would be `F-0097` in a new costume: a number nobody
observed, asserted about a named sovereign. So the signal is system-level and
`TestItCannotBecomeACountryFinding` is the part of this file that matters.

Every parse case takes file **text**, so the file runs offline.
"""
import inspect
import unittest
from datetime import datetime

from pipelines import composite_stress, tic_aggregate
from pipelines.tic_aggregate import SHARE_MOVE_PCT_POINTS, all_other_signal
from pipelines.treasury_holdings import (
    TIC_AGGREGATES,
    parse_tic_aggregates,
    parse_tic_mfh,
)

# The real Table 5 shape, values included.
TABLE5 = "\r\n".join([
    "Table 5: Major Foreign Holders of Treasury Securities\t\t\t",
    "Link: https://ticdata.treasury.gov/.../slt_table5.txt\t\t\t",
    "\t\t\t",
    "Country\t2026-07\t2026-06\t2026-05",
    "Japan\t1103.9\t1116.7\t1143.1",
    "United Kingdom\t998.3\t939.9\t948.6",
    "All Other\t1842.4\t1850.3\t1859.6",
    "Grand Total\t9248.1\t9298.5\t9368.5",
    "Of Which: Foreign Official\t3773.1\t3778.1\t3845.9",
    "",
])


class Row:
    def __init__(self, date, value):
        self.date, self.value = date, value


def series(*pairs):
    return [Row(datetime(*d), v) for d, v in pairs]


class TestTheAggregateRowsAreCaptured(unittest.TestCase):
    def test_all_other_and_grand_total_are_parsed(self):
        out = parse_tic_aggregates(TABLE5)
        self.assertEqual(sorted(out), ["TIC_ALL_OTHER", "TIC_GRAND_TOTAL"])

    def test_the_values_land_on_the_right_months(self):
        # Newest-first columns, same hazard as the country rows. An off-by-one
        # would date July's aggregate to May and every percentage would be wrong
        # while looking entirely plausible.
        ao = parse_tic_aggregates(TABLE5)["TIC_ALL_OTHER"]
        self.assertEqual(ao["Jul 2026"], 1842.4)
        self.assertEqual(ao["Jun 2026"], 1850.3)
        self.assertEqual(ao["May 2026"], 1859.6)

    def test_the_of_which_row_is_still_excluded(self):
        # "Of Which: Foreign Official" is a SUBSET of Grand Total, not a peer of
        # All Other. At 3,773.1 it once outranked Japan (F-0088), and admitting
        # it here would double-count.
        out = parse_tic_aggregates(TABLE5)
        self.assertNotIn("TIC_FOREIGN_OFFICIAL", out)
        for by_date in out.values():
            self.assertNotIn(3773.1, by_date.values())

    def test_the_country_parse_is_unchanged(self):
        # parse_tic_mfh's contract is "countries". An aggregate leaking into it
        # is exactly F-0088, so the default call must still refuse them.
        countries = parse_tic_mfh(TABLE5)
        self.assertEqual(sorted(countries), ["Japan", "United Kingdom"])

    def test_one_parser_owns_the_month_columns(self):
        # Both readings come from parse_tic_mfh, differing only by `admit`. Two
        # implementations would each own a copy of the header logic, and the
        # first attempt at this - rewriting the text so the aggregates were the
        # only data rows - returned nothing, because SKIP_ROWS drops them
        # however they arrive.
        body = inspect.getsource(parse_tic_aggregates)
        self.assertIn("parse_tic_mfh(text, admit=", body)

    def test_the_aggregates_are_declared_with_a_description(self):
        for label, meta in TIC_AGGREGATES.items():
            self.assertTrue(meta["code"].startswith("TIC_"), label)
            self.assertGreater(len(meta["description"]), 40, label)


class TestTheSignal(unittest.TestCase):
    def test_none_before_anything_is_imported(self):
        # A source that has not run must not produce a confident zero.
        class Empty:
            def query(self, *a):
                return self

            def filter_by(self, **k):
                return self

            def filter(self, *a):
                return self

            def order_by(self, *a):
                return self

            def all(self):
                return []

            def first(self):
                return None

        self.assertIsNone(all_other_signal(Empty()))

    def test_the_share_is_computed_against_the_same_month(self):
        # A share built from All Other in one month and Grand Total in another
        # would move whenever either series was revised.
        ao = series(((2026, 6, 1), 1850.3), ((2026, 7, 1), 1842.4))
        gt = series(((2026, 6, 1), 9298.5), ((2026, 7, 1), 9248.1))
        sig = self._signal(ao, gt)
        self.assertAlmostEqual(sig["share_pct"], 19.92, places=2)

    def test_the_month_and_quarter_moves(self):
        ao = series(((2026, 4, 1), 1861.0), ((2026, 5, 1), 1859.6),
                    ((2026, 6, 1), 1850.3), ((2026, 7, 1), 1842.4))
        gt = series(((2026, 4, 1), 9350.1), ((2026, 5, 1), 9368.5),
                    ((2026, 6, 1), 9298.5), ((2026, 7, 1), 9248.1))
        sig = self._signal(ao, gt)
        self.assertAlmostEqual(sig["mom_pct"], -0.43, places=2)
        self.assertAlmostEqual(sig["three_month_pct"], -1.00, places=2)

    def test_consecutive_declines_count_back_from_the_newest(self):
        ao = series(((2026, 4, 1), 1861.0), ((2026, 5, 1), 1859.6),
                    ((2026, 6, 1), 1850.3), ((2026, 7, 1), 1842.4))
        self.assertEqual(self._signal(ao, [])["consecutive_declines"], 3)

    def test_a_rise_breaks_the_run(self):
        ao = series(((2026, 5, 1), 1859.6), ((2026, 6, 1), 1870.0),
                    ((2026, 7, 1), 1842.4))
        self.assertEqual(self._signal(ao, [])["consecutive_declines"], 1)

    def test_notability_is_judged_on_the_share_not_the_level(self):
        # The observed series rose 2.74% in level over twelve months while its
        # share of total FELL - foreign holdings grew faster. A level-based rule
        # would have called that accumulation by the non-reporters.
        self.assertGreater(SHARE_MOVE_PCT_POINTS, 0)
        import inspect as _i
        body = _i.getsource(tic_aggregate.all_other_signal)
        self.assertIn("share_move", body)
        self.assertIn("SHARE_MOVE_PCT_POINTS", body)

    def test_the_real_production_figures_are_not_flagged_as_notable(self):
        # -1.00% over three months with the share moving 0.04 points is ordinary
        # drift. A brand-new signal that fires on its first real reading is the
        # cry-wolf shape of F-0089, F-0091 and F-0095.
        ao = series(((2026, 4, 1), 1861.0), ((2026, 5, 1), 1859.6),
                    ((2026, 6, 1), 1850.3), ((2026, 7, 1), 1842.4))
        gt = series(((2026, 4, 1), 9350.1), ((2026, 5, 1), 9368.5),
                    ((2026, 6, 1), 9298.5), ((2026, 7, 1), 9248.1))
        self.assertFalse(self._signal(ao, gt)["notable"])

    def test_a_real_rotation_is_flagged(self):
        # Share falling from 19.9% to 18.5% is 1.4 points: something left.
        ao = series(((2026, 4, 1), 1861.0), ((2026, 5, 1), 1800.0),
                    ((2026, 6, 1), 1750.0), ((2026, 7, 1), 1710.0))
        gt = series(((2026, 4, 1), 9350.1), ((2026, 5, 1), 9350.0),
                    ((2026, 6, 1), 9300.0), ((2026, 7, 1), 9250.0))
        self.assertTrue(self._signal(ao, gt)["notable"])

    def _signal(self, ao_rows, gt_rows):
        """Run the real function against stubbed series."""
        original = tic_aggregate._series

        def fake(db, code):
            return ao_rows if code == tic_aggregate.ALL_OTHER_CODE else gt_rows

        tic_aggregate._series = fake
        try:
            return tic_aggregate.all_other_signal(object())
        finally:
            tic_aggregate._series = original


class TestItCannotBecomeACountryFinding(unittest.TestCase):
    """The part of this file that matters.

    All Other covers ~100 holders. A move says someone reduced; it does not say
    who. Attributing it to the 28 named countries inside it would be `F-0097`
    again - a number nobody observed, asserted about a named sovereign - and
    that defect cost 1,050 points across 32 countries.
    """

    def test_the_signal_lives_in_summary_not_on_a_country(self):
        body = inspect.getsource(composite_stress.compute_composite_stress)
        self.assertIn('"all_other": all_other_signal(db)', body)

    def test_no_per_country_field_carries_it(self):
        # The per-country dict is built inside the scoring loop. If All Other
        # appeared there it would be one payload field away from being scored.
        body = inspect.getsource(composite_stress.compute_composite_stress)
        loop = body[: body.index('"summary": {')]
        self.assertNotIn("all_other", loop)

    def test_the_composite_country_schema_has_no_aggregate_field(self):
        from api.schemas import CompositeCountry

        for field in CompositeCountry.model_fields:
            self.assertNotIn("all_other", field)

    def test_the_signal_module_never_reads_a_country(self):
        # A join to Country would be the first step toward attribution.
        body = inspect.getsource(tic_aggregate)
        self.assertNotIn("Country", body.replace("country_id", ""))

    def test_it_only_reads_global_series(self):
        # country_id IS NULL. Reading a country's rows into an aggregate would
        # double-count the twenty named holders, which are NOT in All Other.
        body = inspect.getsource(tic_aggregate._series)
        self.assertIn("country_id.is_(None)", body)

    def test_the_note_states_the_limit_in_words(self):
        # On the surface, not only in the register: a reader who sees the figure
        # must be told it is not about any one country.
        ao = series(((2026, 7, 1), 1842.4))
        sig = TestTheSignal()._signal.__func__(TestTheSignal(), ao, [])
        self.assertIn("does not say who", sig["note"])
        self.assertIn("not attributed", sig["note"])


if __name__ == "__main__":
    unittest.main()
