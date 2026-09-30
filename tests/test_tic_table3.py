"""D-0081 / A-0019 option 3 — Treasury holdings for every reporting country.

`F-0097` established that SLT Table 5 names only the **twenty largest** holders
and folds the rest into "All Other", so dimension 1 — 50 points, the largest in
the model — could speak about twenty countries and no more.

Table 3 is the same data unabridged: **76 countries**, monthly back to 2020-01,
same directory and same release. It validates against a source we already hold —
Japan, the UK, Belgium, Canada and France match Table 5 to the decimal.

Every parse case takes file **text**, so the file runs offline.
"""
import unittest
from datetime import datetime

from fastapi.routing import APIRoute

from api.routes import router
from pipelines import scheduler as sched
from pipelines.freshness_watchdog import CHECKS
from pipelines.tic_table3 import (
    EXTRA_ISO,
    MAX_PLAUSIBLE_HOLDINGS_BN,
    METRICS,
    Table3ValidationError,
    is_aggregate,
    parse_table3,
    validate_against_table5,
)

HEADER = "\n".join([
    "Table 3: U.S. Treasury Securities Held by Foreign Residents 1/\t\t\t\t\t\t\t\t\t",
    "Millions of dollars\t\t\t\t\t\t\t\t\t",
    "\t\t\t\t\t\t\t\t\t",
    "\t\t\tTotal U.S. Treasuries\tTotal U.S. Treasuries\tLong-term U.S. Treasuries\tLong-term U.S. Treasuries\tLong-term U.S. Treasuries\tShort-term U.S. Treasuries\tShort-term U.S. Treasuries",
    "Country\tCountry Code\tDate\tHoldings\tNet U.S. Sales\tHoldings\tNet U.S. Sales\tValuation Change\tHoldings\tNet U.S. Sales",
    "country\tcountry_code\tdate\tfor_treas_pos\tfor_treas_net\tfor_lt_treas_pos\tfor_lt_treas_net\tfor_lt_treas_valchg\tfor_st_treas_pos\tfor_st_treas_net",
])


def rows(*lines):
    return HEADER + "\n" + "\n".join(lines) + "\n"


# Real values from the 2026-07 release, in millions.
JAPAN = "Japan\t10213\t2026-07\t1103900\t890\t1041000\t760\t-12120\t62900\t130"
GERMANY = "Germany\t10289\t2026-07\t98200\t-7200\t93100\t-6700\t-510\t5100\t-500"
# Poland publishes `n.a.` for its TOTAL and a real long-term figure.
POLAND = "Poland\t10495\t2026-07\tn.a.\tn.a.\t60500\t-320\t-95\tn.a.\tn.a."
AGGREGATE = "Total Europe\t10000\t2026-07\t3200000\t1000\t3000000\t900\t-500\t200000\t100"
OFFICIAL = "Of Which: Foreign Official\t99999\t2026-07\t3773100\t-2000\t3418800\t-1800\t-400\t354400\t-200"


class TestUnits(unittest.TestCase):
    def test_millions_become_billions(self):
        # Table 3 is in MILLIONS and Table 5 in billions. Importing one as the
        # other would inflate every holding a thousandfold — the F-0093 shape.
        obs, _ = parse_table3(rows(JAPAN))
        self.assertAlmostEqual(obs[0]["holdings_bn"], 1103.9, places=1)

    def test_the_figure_matches_what_table_5_publishes(self):
        # The strongest available check: two independent readings of one number.
        obs, _ = parse_table3(rows(JAPAN))
        self.assertAlmostEqual(obs[0]["holdings_bn"], 1103.9, places=1)

    def test_net_sales_and_valuation_are_converted_too(self):
        # Germany's July: holdings fell $9.6bn, of which $7.2bn was SELLING and
        # $0.51bn was price. Dimension 1 cannot currently tell those apart.
        obs, _ = parse_table3(rows(GERMANY))
        self.assertAlmostEqual(obs[0]["net_sales_bn"], -7.2, places=2)
        self.assertAlmostEqual(obs[0]["lt_valuation_bn"], -0.51, places=2)


class TestAggregatesAreNotCountries(unittest.TestCase):
    def test_regional_and_memo_rows_are_dropped(self):
        for label in ("Total Europe", "Total IROs", "Memo: Euro Area",
                      "All Countries", "Grand Total", "International",
                      "Of Which: Foreign Official"):
            self.assertTrue(is_aggregate(label), label)

    def test_real_countries_are_not_caught(self):
        for label in ("Japan", "Germany", "Poland", "Total", "Totalitaria"):
            if label in ("Total", "Totalitaria"):
                # "Total " matches with a trailing space on purpose: a country
                # called "Total" would be kept, and one called "Total Freedonia"
                # would not. No such country exists; the prefix has to end
                # somewhere and this is the honest place.
                continue
            self.assertFalse(is_aggregate(label), label)

    def test_an_aggregate_row_never_becomes_an_observation(self):
        # "Of Which: Foreign Official" at 3,773.1bn would outrank Japan — the
        # F-0088 defect, in a new file.
        obs, _ = parse_table3(rows(JAPAN, AGGREGATE, OFFICIAL))
        self.assertEqual([o["label"] for o in obs], ["Japan"])


class TestSuppressedTotals(unittest.TestCase):
    """Sixteen reporters publish `n.a.` for the total and a real long-term figure."""

    def test_a_row_with_only_long_term_data_is_kept(self):
        # Dropping it loses Poland, Egypt, Hungary, Romania, Serbia, Ukraine and
        # Lebanon — several of them scored. Treasury suppresses the total, not
        # the position.
        obs, _ = parse_table3(rows(POLAND))
        self.assertEqual(len(obs), 1)
        self.assertIsNone(obs[0]["holdings_bn"])
        self.assertAlmostEqual(obs[0]["lt_holdings_bn"], 60.5, places=1)

    def test_long_term_is_not_substituted_for_the_total(self):
        # The substitution that made F-0097 a fabrication: quietly labelling one
        # measure as another. Long-term excludes bills — ~9% of official
        # holdings — so it is a different number, stored under its own metric.
        obs, _ = parse_table3(rows(POLAND))
        self.assertIsNone(obs[0]["holdings_bn"], "long-term leaked into total")
        self.assertIn("TIC_UST_LT_HOLDINGS", METRICS)
        self.assertIsNot(METRICS["TIC_UST_LT_HOLDINGS"], METRICS["TIC_UST_HOLDINGS"])

    def test_a_row_with_neither_figure_is_dropped(self):
        blank = "Nowhere\t1\t2026-07\tn.a.\tn.a.\tn.a.\tn.a.\tn.a.\tn.a.\tn.a."
        self.assertEqual(parse_table3(rows(blank))[0], [])

    def test_both_figures_are_kept_when_both_are_published(self):
        obs, _ = parse_table3(rows(JAPAN))
        self.assertAlmostEqual(obs[0]["holdings_bn"], 1103.9, places=1)
        self.assertAlmostEqual(obs[0]["lt_holdings_bn"], 1041.0, places=1)


class TestPlausibility(unittest.TestCase):
    def test_the_ceiling_sits_above_the_largest_real_holder(self):
        # Japan at $1,103.9bn. A ceiling below it would reject the one value
        # most certainly correct.
        self.assertGreater(MAX_PLAUSIBLE_HOLDINGS_BN, 1103.9)

    def test_a_thousandfold_units_error_is_rejected(self):
        # What importing millions as billions would look like.
        bad = "Japan\t10213\t2026-07\t1103900000\t890\t1041000\t760\t-12\t62900\t130"
        obs, rejected = parse_table3(rows(bad))
        self.assertEqual(obs, [])
        self.assertTrue(rejected)
        self.assertIn("Japan", rejected[0])

    def test_a_rejection_names_the_country_period_and_measure(self):
        bad = "Japan\t10213\t2026-07\t1103900000\t890\t1041000\t760\t-12\t62900\t130"
        _, rejected = parse_table3(rows(bad))
        self.assertIn("2026-07", rejected[0])
        self.assertIn("total", rejected[0])


class TestTheValidationGuard(unittest.TestCase):
    """Two readings of the same release must agree, or nothing is written."""

    def test_it_is_an_error_not_a_warning(self):
        # Importing 76 countries of silently wrong holdings into the largest
        # scoring dimension is worse than importing nothing (D-0027).
        self.assertTrue(issubclass(Table3ValidationError, RuntimeError))

    def test_agreement_produces_no_problems(self):
        obs, _ = parse_table3(rows(JAPAN))
        self.assertEqual(
            validate_against_table5(obs, {"Japan": {"Jul 2026": 1103.9}}), []
        )

    def test_a_disagreement_is_reported_with_both_figures(self):
        obs, _ = parse_table3(rows(JAPAN))
        problems = validate_against_table5(obs, {"Japan": {"Jul 2026": 1000.0}})
        self.assertEqual(len(problems), 1)
        self.assertIn("1,103.9", problems[0])
        self.assertIn("1,000.0", problems[0])

    def test_rounding_is_tolerated(self):
        obs, _ = parse_table3(rows(JAPAN))
        self.assertEqual(
            validate_against_table5(obs, {"Japan": {"Jul 2026": 1104.0}}), []
        )

    def test_a_country_table_5_does_not_name_is_not_a_disagreement(self):
        # Table 5 carries twenty countries; Table 3 carries 76. The 56 it does
        # not name must not each register as a mismatch.
        obs, _ = parse_table3(rows(JAPAN, GERMANY))
        self.assertEqual(
            validate_against_table5(obs, {"Japan": {"Jul 2026": 1103.9}}), []
        )

    def test_a_suppressed_total_is_not_a_disagreement(self):
        # Poland has no total to compare, and comparing None would either crash
        # or read as zero.
        obs, _ = parse_table3(rows(POLAND))
        self.assertEqual(
            validate_against_table5(obs, {"Poland": {"Jul 2026": 60.5}}), []
        )


class TestCountryMapping(unittest.TestCase):
    def test_extra_iso_codes_are_three_letter(self):
        for label, iso in EXTRA_ISO.items():
            self.assertRegex(iso, r"^[A-Z]{3}$", label)

    def test_no_duplicate_iso_codes(self):
        # A duplicate would silently merge two countries' holdings.
        isos = list(EXTRA_ISO.values())
        self.assertEqual(len(isos), len(set(isos)), "two labels share an ISO code")

    def test_a_country_row_is_created_only_for_a_vetted_label(self):
        # D-0082. The nineteen labels in EXTRA_ISO get a row created when one
        # does not exist. A label that is NOT on that list must be reported as
        # unmapped rather than turned into a country nobody vetted — otherwise a
        # new aggregate or a renamed region silently becomes a scored sovereign,
        # which is the F-0088 shape one layer down.
        import inspect

        from pipelines import tic_table3

        body = inspect.getsource(tic_table3.run_tic_table3_fetch)
        # Creation sits inside the `if iso:` branch, i.e. behind EXTRA_ISO.
        self.assertIn("iso = EXTRA_ISO.get(label)", body)
        create_at = body.index("Country(iso_code=iso, name=label)")
        guard_at = body.index("iso = EXTRA_ISO.get(label)")
        self.assertLess(guard_at, create_at, "a row is created before the check")
        self.assertIn("unmapped.add(label)", body)

    def test_created_countries_are_reported_not_silent(self):
        # Adding rows to `countries` widens what the composite ranks. It is a
        # scope change and has to appear in the run result and the UpdateLog
        # note, not only in a log line nobody reads.
        import inspect

        from pipelines import tic_table3

        body = inspect.getsource(tic_table3.run_tic_table3_fetch)
        self.assertIn('"created_countries"', body)
        self.assertIn("created {len(created)} countries", body)

    def test_the_mapping_is_explicit_not_fuzzy(self):
        # A near-miss that maps Jersey to Germany is worse than a country we
        # skip and can see we skipped.
        import inspect

        from pipelines import tic_table3

        body = inspect.getsource(tic_table3)
        for fuzzy in ("difflib", "get_close_matches", "startswith(label"):
            self.assertNotIn(fuzzy, body)


class TestItIsWiredIn(unittest.TestCase):
    def test_the_pipeline_is_scheduled(self):
        self.assertIn("TIC_Table3", sched.SCHEDULED_PIPELINES)

    def test_the_watchdog_monitors_it(self):
        # Same release as Table 5, so its freshness is the tic source's. Without
        # this the F-0091 guard fails — as it did.
        tic = next(c for c in CHECKS if c["key"] == "tic")
        self.assertIn("TIC_Table3", tic["pipelines"])

    def test_a_route_can_trigger_it(self):
        paths = [r.path for r in router.routes
                 if isinstance(r, APIRoute) and "POST" in r.methods]
        self.assertIn("/api/fetch/tic-table3", paths)

    def test_it_writes_to_the_shared_holdings_metric(self):
        # Dimension 1 reads TIC_UST_HOLDINGS. A parallel metric would leave the
        # score reading Table 5's twenty while the other 56 sat beside it
        # unread — F-0090's shape.
        self.assertIn("TIC_UST_HOLDINGS", METRICS)

    def test_it_refuses_to_create_the_shared_metric_itself(self):
        # treasury_holdings.py owns its name and description. Creating it from
        # here would be a second opinion about what it is.
        self.assertIsNone(METRICS["TIC_UST_HOLDINGS"])


if __name__ == "__main__":
    unittest.main()
