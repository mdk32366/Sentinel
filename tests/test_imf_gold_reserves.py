"""D-0076 / F-0093 / F-0094 — the ticker behind the gold download.

`pipelines/gold_reserves.py` reads a World Gold Council CSV that a person
downloads by hand. The files in `data/incoming/` are named
`World_official_gold_holdings_..._IFS.xlsx`: WGC's source is IMF International
Financial Statistics. We were reading a quarterly re-publication of a monthly
feed, three months behind it, manually.

The monthly feed is IMF **IRFCL**, indicator `IRFCLDT1_IRFCL56V_FTO` - Reserves
Data Template line 56, gold, in fine troy ounces.

Validated against the WGC data already in the database before being wired in:
68 countries overlap, 55 agree within 10%, and every large holder agrees to the
decimal. Most disagreements are real accumulation the 272-day-old CSV had
missed (Turkey 534.9 -> 791.4 tonnes).

Every case parses **text**, never a URL, so the file runs offline.
"""
import unittest
from datetime import datetime

from fastapi.routing import APIRoute

from api.routes import router
from pipelines import scheduler as sched
from pipelines.composite_stress import GOLD_WINDOW_DAYS, _last_per_quarter
from pipelines.freshness_watchdog import CHECKS
from pipelines.imf_gold_reserves import (
    RESERVE_ASSET_SECTOR,
    IMF_GOLD_INDICATOR,
    IMF_GOLD_URL,
    MAX_PLAUSIBLE_TONNES,
    NOT_COUNTRIES,
    OZ_PER_TONNE,
    parse_imf_gold,
)


def sdmx(*series):
    return (
        "<?xml version='1.0' encoding='UTF-8'?><message:StructureSpecificData>"
        "<message:DataSet>" + "".join(series) + "</message:DataSet>"
        "</message:StructureSpecificData>"
    )


def series(iso, *obs, sector="S1XS1311"):
    body = "".join(
        f'<Obs TIME_PERIOD="{p}" OBS_VALUE="{v}" DERIVATION_TYPE="O"/>' for p, v in obs
    )
    return (
        f'<Series COUNTRY="{iso}" INDICATOR="{IMF_GOLD_INDICATOR}" '
        f'SECTOR="{sector}" FREQUENCY="M" SCALE="6">{body}</Series>'
    )


# The real values, which is the point of the cases below.
USA_OZ = "261499000"           # -> 8,133.5 t, the published figure
DEU_OZ = "107676802.209"       # -> 3,349.1 t
BRA_GOOD_OZ = "5544278.72299948"    # -> 172.4 t  (2026-M01/M02)
BRA_BAD_OZ = "5544278722.99971"     # -> 172,446 t (2026-M03 onward)


class TestTheConversion(unittest.TestCase):
    def test_one_tonne_is_32150_fine_troy_ounces(self):
        # 1,000,000 g / 31.1034768 g per fine troy ounce.
        self.assertAlmostEqual(OZ_PER_TONNE, 1e6 / 31.1034768, places=3)

    def test_the_us_holding_comes_out_at_the_published_figure(self):
        # 8,133.5 tonnes is the universally quoted US official gold reserve.
        # If the conversion is wrong this is the case that says so.
        obs, _, _ = parse_imf_gold(sdmx(series("USA", ("2026-M07", USA_OZ))))
        self.assertEqual(len(obs), 1)
        self.assertAlmostEqual(obs[0]["tonnes"], 8133.5, places=1)

    def test_germany_too(self):
        obs, _, _ = parse_imf_gold(sdmx(series("DEU", ("2026-M08", DEU_OZ))))
        self.assertAlmostEqual(obs[0]["tonnes"], 3349.1, places=1)


class TestThePeriodConvention(unittest.TestCase):
    def test_a_monthly_period_lands_on_the_first_of_that_month(self):
        # Matches the WGC importer, which dates a quarter to its first day.
        # A-0016 records why that convention is what it is and what it costs.
        obs, _, _ = parse_imf_gold(sdmx(series("USA", ("2026-M07", USA_OZ))))
        self.assertEqual(obs[0]["date"], datetime(2026, 7, 1))

    def test_a_malformed_period_is_dropped_not_guessed(self):
        obs, _, _ = parse_imf_gold(sdmx(series("USA", ("2026-Q3", USA_OZ))))
        self.assertEqual(obs, [])


class TestThePlausibilityCeiling(unittest.TestCase):
    """F-0093. The feed's scale defects are real and are not uniform."""

    def test_brazils_rescaled_series_is_rejected(self):
        # The same constant holding appears as 5544278.72 in 2026-M01 and
        # 5544278722.99 from 2026-M03 - rescaled by exactly 1000 mid-series.
        # Read naively the later value is 172,446 tonnes: roughly five times
        # all the gold every central bank on earth holds.
        obs, rejected, _ = parse_imf_gold(sdmx(series(
            "BRA", ("2026-M01", BRA_GOOD_OZ), ("2026-M03", BRA_BAD_OZ),
        )))
        self.assertEqual(len(obs), 1, "the 172,446-tonne reading was accepted")
        self.assertAlmostEqual(obs[0]["tonnes"], 172.4, places=1)
        self.assertEqual(len(rejected), 1)
        self.assertIn("BRA", rejected[0])

    def test_the_ceiling_sits_above_the_largest_real_holder(self):
        # The US at 8,133.5 t is the largest holder there has ever been. A
        # ceiling below it would reject the one value most certainly correct.
        self.assertGreater(MAX_PLAUSIBLE_TONNES, 8133.5)

    def test_the_ceiling_sits_below_the_world_total(self):
        # All official holdings together are roughly 36,000 tonnes. Any single
        # country near that is arithmetic, not news.
        self.assertLess(MAX_PLAUSIBLE_TONNES, 36000)

    def test_a_negative_holding_is_rejected(self):
        _, rejected, _ = parse_imf_gold(sdmx(series("USA", ("2026-M07", "-500000"))))
        self.assertEqual(len(rejected), 1)

    def test_a_rejection_names_the_country_and_period(self):
        # A count alone cannot be acted on, and these need chasing upstream.
        _, rejected, _ = parse_imf_gold(sdmx(series("AGO", ("2026-M07", "592900000"))))
        self.assertTrue(rejected)
        self.assertIn("AGO", rejected[0])
        self.assertIn("2026-M07", rejected[0])


class TestAggregatesAreNotCountries(unittest.TestCase):
    def test_country_groups_and_institutions_are_excluded(self):
        # IRFCL puts these in the same COUNTRY dimension as real countries.
        # G163 read as 10,807 tonnes, which would have outranked the USA.
        for code in ("G163", "EZB", "WBG"):
            obs, _, _ = parse_imf_gold(sdmx(series(code, ("2026-M08", "347000000"))))
            self.assertEqual(obs, [], f"{code} parsed as a country")

    def test_real_countries_are_not_caught_by_that_rule(self):
        for iso in ("USA", "DEU", "CHN", "GBR"):
            self.assertNotIn(iso, NOT_COUNTRIES)


class TestOnlyTheReserveAssetSectorIsTaken(unittest.TestCase):
    """F-0095. One series per country-month, and the right one.

    This class originally asserted that BOTH sector series came out, to guard
    against losing one - while exploring the feed I keyed a dict by country and
    kept whichever came last, which reported Brazil at 172,446 tonnes and hid
    the correct 172.4 in the same response.

    It pinned the wrong contract, and it passed while the pipeline was broken.
    `ix_metric_country_date` is unique on (metric, country, date), so two
    observations for one country-month is a constraint violation, not a second
    data point - and the pre-flush existence check cannot see a sibling in the
    same uncommitted batch. Production's first run returned
    `duplicate key value violates unique constraint "ix_metric_country_date"
    ... (36, 4, 2015-02-01) already exists`.
    """

    def test_only_the_reserve_asset_sector_survives(self):
        obs, _, _ = parse_imf_gold(sdmx(
            series("DEU", ("2026-M08", DEU_OZ), sector="S1X"),
            series("DEU", ("2026-M08", DEU_OZ), sector=RESERVE_ASSET_SECTOR),
        ))
        self.assertEqual(len(obs), 1, "two rows for one country-month")
        self.assertEqual(obs[0]["sector"], RESERVE_ASSET_SECTOR)
        self.assertAlmostEqual(obs[0]["tonnes"], 3349.1, places=1)

    def test_no_country_month_appears_twice(self):
        obs, _, _ = parse_imf_gold(sdmx(
            series("DEU", ("2026-M07", DEU_OZ), ("2026-M08", DEU_OZ), sector="S1X"),
            series("DEU", ("2026-M07", DEU_OZ), ("2026-M08", DEU_OZ)),
            series("USA", ("2026-M07", USA_OZ)),
        ))
        keys = [(o["iso"], o["date"]) for o in obs]
        self.assertEqual(len(keys), len(set(keys)), f"duplicate keys: {keys}")

    def test_the_choice_does_not_depend_on_document_order(self):
        for order in (("S1X", RESERVE_ASSET_SECTOR),
                      (RESERVE_ASSET_SECTOR, "S1X")):
            obs, _, _ = parse_imf_gold(sdmx(*[
                series("DEU", ("2026-M08", DEU_OZ if sec == RESERVE_ASSET_SECTOR else "0"),
                       sector=sec)
                for sec in order
            ]))
            self.assertEqual(len(obs), 1)
            self.assertAlmostEqual(obs[0]["tonnes"], 3349.1, places=1)

    def test_central_government_gold_is_not_reserve_assets(self):
        # S1311 is central government's OWN holding. Usually zero, because a
        # country's gold sits at its central bank: Belgium reads
        # S1XS1311=227.4t and S1311=0.0t and both are correct.
        obs, _, _ = parse_imf_gold(sdmx(
            series("BEL", ("2026-M08", "7310000")),
            series("BEL", ("2026-M08", "0"), sector="S1311"),
        ))
        self.assertEqual(len(obs), 1)
        self.assertGreater(obs[0]["tonnes"], 200)

    def test_s1x_is_not_used_as_a_fallback(self):
        # It reads 0 for the United Kingdom and equals S1XS1311 for Germany, so
        # whatever it decomposes it is not reliably the same measure. A country
        # carrying only S1X yields nothing rather than a zero holding - and no
        # country in the feed is in that state.
        obs, _, _ = parse_imf_gold(sdmx(
            series("GBR", ("2026-M08", "0"), sector="S1X"),
        ))
        self.assertEqual(obs, [])

    def test_no_warning_fires_on_the_normal_shape(self):
        # Ranked fallbacks with a disagreement report produced 868 "conflicts"
        # against the live feed, then 140 after excluding S1311 - every one two
        # different concepts correctly disagreeing, and every run marked
        # `partial` forever. That is F-0089's cry-wolf shape in a brand-new
        # guard, so the guard went and the rule got simpler.
        _, rejected, duplicates = parse_imf_gold(sdmx(
            series("DEU", ("2026-M08", DEU_OZ), sector="S1X"),
            series("DEU", ("2026-M08", DEU_OZ)),
            series("DEU", ("2026-M08", "0"), sector="S1311"),
            series("USA", ("2026-M07", USA_OZ)),
        ))
        self.assertEqual(rejected, [])
        self.assertEqual(duplicates, [], "the normal feed shape raised a warning")


class TestTheUrl(unittest.TestCase):
    def test_it_asks_for_monthly_data_across_all_countries(self):
        # Key order is COUNTRY.INDICATOR.SECTOR.FREQUENCY; blanks mean "all".
        self.assertTrue(IMF_GOLD_URL.endswith(f".{IMF_GOLD_INDICATOR}..M"))

    def test_it_uses_the_host_that_still_resolves(self):
        # dataservices.imf.org, the endpoint every older example uses, no
        # longer resolves at all - not a 404, no connection.
        self.assertIn("api.imf.org", IMF_GOLD_URL)
        self.assertNotIn("dataservices.imf.org", IMF_GOLD_URL)


class TestQuarterlyResampling(unittest.TestCase):
    """F-0094 — the fix that stops the better source corrupting the score."""

    class Row:
        def __init__(self, date, value):
            self.date, self.value = date, value

    def rows(self, *pairs):
        return [self.Row(datetime(*d), v) for d, v in pairs]

    def test_monthly_rows_collapse_to_one_per_quarter(self):
        # Three monthly dips are a quarter of movement, not three quarters.
        # Scored as rows, they earned 12 points; dimension 2 says "consecutive
        # QUARTERS" and used to count consecutive ROWS, which was only ever
        # true because the WGC CSV is quarterly.
        out = _last_per_quarter(self.rows(
            ((2026, 1, 1), 100), ((2026, 2, 1), 99), ((2026, 3, 1), 98),
            ((2026, 4, 1), 97),
        ))
        self.assertEqual(len(out), 2)

    def test_the_last_reading_in_a_quarter_is_the_one_kept(self):
        out = _last_per_quarter(self.rows(
            ((2026, 1, 1), 100), ((2026, 2, 1), 99), ((2026, 3, 1), 98),
        ))
        self.assertEqual(out[0].value, 98)

    def test_quarterly_rows_pass_through_unchanged(self):
        # The WGC series must score exactly as it did before, or this "fix"
        # silently rescored every country that IRFCL does not cover.
        pairs = (((2025, 7, 1), 100), ((2025, 10, 1), 99),
                 ((2026, 1, 1), 98), ((2026, 4, 1), 97))
        out = _last_per_quarter(self.rows(*pairs))
        self.assertEqual([r.value for r in out], [100, 99, 98, 97])

    def test_the_result_is_in_ascending_date_order(self):
        # The consecutive-decline walk reads backwards from the end and would
        # report nonsense on an unsorted list.
        out = _last_per_quarter(self.rows(
            ((2026, 4, 1), 97), ((2025, 7, 1), 100), ((2026, 1, 1), 98),
        ))
        self.assertEqual([r.date for r in out], sorted(r.date for r in out))

    def test_a_mixed_cadence_does_not_double_count_a_quarter(self):
        # The real state of the series after this change: quarterly WGC history
        # then monthly IMF rows, and for a while both in the same quarter.
        out = _last_per_quarter(self.rows(
            ((2026, 1, 1), 100),   # WGC Q1
            ((2026, 1, 1), 100),   # IMF 2026-M01, same date
            ((2026, 2, 1), 99), ((2026, 3, 1), 98),
        ))
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].value, 98)

    def test_the_window_makes_the_documented_cap_reachable(self):
        # The cap is five consecutive quarters at 4 points = 20. 400 days holds
        # at most five quarterly rows, so at most FOUR consecutive declines and
        # 16 points: the last 4 were unreachable for every country. Needs six
        # quarters of history, so > 540 days.
        self.assertGreater(GOLD_WINDOW_DAYS, 545)


class TestItIsWiredIn(unittest.TestCase):
    def test_the_pipeline_is_scheduled(self):
        self.assertIn("Gold_Reserves_IMF", sched.SCHEDULED_PIPELINES)

    def test_the_watchdog_expects_it(self):
        src = next(s for s in CHECKS if s["key"] == "gold_reserves")
        self.assertIn("Gold_Reserves_IMF", src["pipelines"])

    def test_the_tolerance_suits_a_monthly_source_now(self):
        # IRFCL publishes ~3 weeks after month end. D-0077 measures age from the
        # end of the data month rather than its first day, so the cycle is 28-55
        # days: the 2026-09-28 release covered to 2026-08-31, 28 days earlier.
        # 200 was set for a quarterly hand-downloaded CSV and marked PROVISIONAL;
        # 95 was the label-based figure; this is the coverage-based one.
        src = next(s for s in CHECKS if s["key"] == "gold_reserves")
        self.assertGreaterEqual(src["max_age_days"], 55)
        self.assertLess(src["max_age_days"], 86)  # a missed release reaches ~86

    def test_the_note_no_longer_says_MANUAL(self):
        src = next(s for s in CHECKS if s["key"] == "gold_reserves")
        self.assertNotIn("MANUAL", src["note"])

    def test_a_route_can_trigger_it(self):
        paths = [r.path for r in router.routes
                 if isinstance(r, APIRoute) and "POST" in r.methods]
        self.assertIn("/api/fetch/gold-reserves-imf", paths)

    def test_it_writes_to_the_existing_gold_series(self):
        # Not a parallel metric. The UI, the composite and the watchdog all
        # read GOLD_RESERVES; a second code would have left the tab showing the
        # stale one while the fresh data sat beside it unread - which is
        # F-0090's shape.
        from pipelines.imf_gold_reserves import GOLD_METRIC_CODE
        from pipelines.gold_fetcher import GOLD_METRIC

        self.assertEqual(GOLD_METRIC_CODE, GOLD_METRIC["code"])


if __name__ == "__main__":
    unittest.main()
