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
import os
import re
import unittest
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from unittest import mock

import requests
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker

import pipelines.imf_gold_reserves as imf
from api.routes import router
from config import settings
from database.connection import get_db
from database.models import Base, Country, Metric, TimeSeries, UpdateLog
from pipelines.gold_fetcher import GOLD_METRIC
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

    def test_the_flow_ref_names_its_agency(self):
        # 2026-11-10: `/data/IRFCL/...` started resolving to all:IRFCL(latest)
        # and returning 404. Nothing asserted the agency, which is why it
        # regressed silently. T2 below holds the builder to the same rule.
        self.assertIn("/data/IMF.STA,IRFCL", IMF_GOLD_URL)
        self.assertNotIn("/data/IRFCL/", IMF_GOLD_URL)

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


# ---------------------------------------------------------------------------
# 2026-11-10: IRFCL 404 (SPEC @0.1 §5, T1-T15).
#
# The job asked for `/2.1/data/IRFCL/...` with no agency. IMF's gateway began
# resolving a missing agency to `all`, found no `all:IRFCL(latest)` and
# returned 404; `/2.1/data/IMF.STA,IRFCL/...` returns the same series. These
# cases pin the qualified flowRef, the response contract, the error class an
# upstream failure surfaces as, and the backfill's idempotency.
#
# New symbols are read off the module (`imf.<name>`) so that this file still
# imports on a tree without them, and the red-first run shows assertion
# failures rather than one ImportError.
# ---------------------------------------------------------------------------

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "imf"
SEEDED = ("USA", "CHN", "DEU", "GBR", "BEL", "BRA")


def fixture(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


def three_country_fixture():
    """T8: the real trimmed response with every series except USA/CHN/DEU removed."""
    return re.sub(
        r'<Series COUNTRY="(?!USA"|CHN"|DEU")[^"]*".*?</Series>', "",
        fixture("irfcl_gold_2026-11-10_trimmed.xml"), flags=re.S,
    )


def response(status, body, content_type="application/xml"):
    """A real `requests.Response`, so raise_for_status() behaves as on the wire."""
    r = requests.Response()
    r.status_code = status
    r._content = body.encode("utf-8")
    r.headers["Content-Type"] = content_type
    r.encoding = "utf-8"
    r.url = imf.IMF_GOLD_URL + "?startPeriod=2015-01"
    r.reason = {200: "OK", 404: "Not Found", 503: "Service Unavailable"}.get(status, "")
    return r


def not_found():
    return response(404, fixture("irfcl_404_no_such_dataflow.json"), "application/json")


def ok_trimmed():
    return response(200, fixture("irfcl_gold_2026-11-10_trimmed.xml"))


def memory_db(isos=SEEDED):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    db.add(Metric(**GOLD_METRIC))
    for iso in isos:
        db.add(Country(iso_code=iso, name=iso))
    db.commit()
    return db


def gold_rows(db):
    metric = db.query(Metric).filter_by(code=imf.GOLD_METRIC_CODE).one()
    return db.query(TimeSeries).filter_by(metric_id=metric.id)


def imf_logs(db, status=None):
    q = db.query(UpdateLog).filter_by(pipeline_name="Gold_Reserves_IMF")
    return q.filter_by(status=status).all() if status else q.all()


class T01ParserOnTheRecordedResponse(unittest.TestCase):
    """T1. The unchanged parser on the real 2026-11-10 response."""

    @classmethod
    def setUpClass(cls):
        cls.obs, cls.rejected, cls.duplicates = parse_imf_gold(
            fixture("irfcl_gold_2026-11-10_trimmed.xml"))
        cls.by_key = {(o["iso"], o["date"]): o["tonnes"] for o in cls.obs}

    def test_the_published_figures(self):
        for iso, when, tonnes in (
            ("USA", datetime(2026, 7, 1), 8133.53),
            ("CHN", datetime(2026, 9, 1), 2409.59),
            ("DEU", datetime(2026, 9, 1), 3349.12),
            ("GBR", datetime(2026, 10, 1), 310.29),
            # S1XS1311 chosen over S1311 (0.0) and S1X.
            ("BEL", datetime(2026, 9, 1), 227.4),
        ):
            self.assertEqual(self.by_key.get((iso, when)), tonnes, f"{iso} {when:%Y-%m}")

    def test_aggregates_are_absent(self):
        self.assertNotIn("G163", {o["iso"] for o in self.obs})

    def test_brazil_keeps_only_the_months_before_the_scale_break(self):
        self.assertEqual(
            sorted(o["date"] for o in self.obs if o["iso"] == "BRA"),
            [datetime(2026, 1, 1), datetime(2026, 2, 1)],
        )

    def test_the_rejects_are_the_known_defects(self):
        self.assertEqual(self.rejected, [
            "AGO/2026-M07=18,441.3t", "AGO/2026-M08=18,441.3t",
            "AGO/2026-M09=18,441.3t", "BRA/2026-M03=172,446.3t",
            "BRA/2026-M04=172,446.3t",
        ])

    def test_no_duplicates_and_seventeen_observations(self):
        self.assertEqual(self.duplicates, [])
        self.assertEqual(len(self.obs), 17)


class T02TheFlowRefIsQualified(unittest.TestCase):
    """T2. The exact regression of 2026-11-10."""

    def test_the_module_constant_names_the_agency(self):
        self.assertIn("/data/IMF.STA,IRFCL", imf.IMF_GOLD_URL)
        self.assertNotIn("/data/IRFCL/", imf.IMF_GOLD_URL)

    def test_the_url_builder_names_the_agency(self):
        url = imf.imf_gold_url()
        self.assertIn("/data/IMF.STA,IRFCL", url)
        self.assertNotIn("/data/IRFCL/", url)
        self.assertTrue(url.endswith(".IRFCLDT1_IRFCL56V_FTO..M"), url)


class T03TheUrlComesFromConfig(unittest.TestCase):
    def test_settings_override_the_base_and_flow_ref(self):
        with mock.patch.object(settings, "imf_sdmx_base", "https://example.test/sdmx/2.1/"), \
             mock.patch.object(settings, "imf_irfcl_flow_ref", "IMF.STA,IRFCL,13.0.0"):
            self.assertEqual(
                imf.imf_gold_url(),
                "https://example.test/sdmx/2.1/data/IMF.STA,IRFCL,13.0.0/.IRFCLDT1_IRFCL56V_FTO..M",
            )

    def test_the_defaults_are_the_verified_values(self):
        self.assertEqual(settings.imf_sdmx_base, "https://api.imf.org/external/sdmx/2.1")
        self.assertEqual(settings.imf_irfcl_flow_ref, "IMF.STA,IRFCL,latest")
        self.assertEqual(settings.imf_api_key, "")


class T04TheKeyHeader(unittest.TestCase):
    KEY = "test-only-key-must-not-leak-7f3a"

    def test_no_key_no_header_and_xml_is_asked_for(self):
        with mock.patch.object(settings, "imf_api_key", ""), \
             mock.patch.object(imf.requests, "get", return_value=ok_trimmed()) as get:
            imf.fetch_imf_gold()
        headers = get.call_args.kwargs["headers"]
        self.assertNotIn("Ocp-Apim-Subscription-Key", headers)
        self.assertEqual(headers.get("Accept"), "application/xml")

    def test_a_key_is_sent_when_set(self):
        with mock.patch.object(settings, "imf_api_key", "x"), \
             mock.patch.object(imf.requests, "get", return_value=ok_trimmed()) as get:
            imf.fetch_imf_gold()
        self.assertEqual(get.call_args.kwargs["headers"]["Ocp-Apim-Subscription-Key"], "x")

    def test_the_key_never_reaches_a_message_or_a_log(self):
        db = memory_db()
        with mock.patch.object(settings, "imf_api_key", self.KEY), \
             mock.patch.object(imf.requests, "get", return_value=not_found()), \
             self.assertLogs("pipelines.imf_gold_reserves", level="DEBUG") as logs:
            with self.assertRaises(Exception) as cm:
                imf.run_imf_gold_fetch(db)
        self.assertNotIn(self.KEY, str(cm.exception))
        self.assertNotIn(self.KEY, repr(cm.exception.args))
        for line in logs.output:
            self.assertNotIn(self.KEY, line)
        for log in imf_logs(db):
            self.assertNotIn(self.KEY, log.error_message or "")


class T05TheOldStyle404(unittest.TestCase):
    """T5. Today's failure, as it must now surface."""

    def test_a_404_is_an_upstream_error_and_writes_nothing(self):
        db = memory_db()
        with mock.patch.object(imf.requests, "get", return_value=not_found()) as get:
            with self.assertRaises(Exception) as cm:
                imf.run_imf_gold_fetch(db)
        exc = cm.exception
        self.assertEqual(type(exc).__name__, "ImfUpstreamError", f"{type(exc).__name__}: {exc}")
        self.assertIn("404", str(exc))
        self.assertIn("No such dataflow found", str(exc))
        self.assertEqual(gold_rows(db).count(), 0)
        failed = imf_logs(db, "failed")
        self.assertEqual(len(failed), 1)
        self.assertEqual(len(imf_logs(db)), 1)
        self.assertIn("No such dataflow found", failed[0].error_message)
        self.assertEqual(get.call_count, 1, "a 4xx was retried")


class T06SchemaDrift(unittest.TestCase):
    def test_a_renamed_indicator_is_a_contract_error(self):
        db = memory_db()
        drift = response(200, fixture("irfcl_drift_renamed_indicator.xml"))
        with mock.patch.object(imf.requests, "get", return_value=drift):
            with self.assertRaises(imf.ImfContractError) as cm:
                imf.run_imf_gold_fetch(db, min_countries=1)
        self.assertIn("IRFCLDT1_IRFCL56V_FTO_X", str(cm.exception))
        self.assertEqual(gold_rows(db).count(), 0)
        self.assertEqual(len(imf_logs(db, "failed")), 1)

    def test_a_different_dataflow_is_a_contract_error(self):
        body = fixture("irfcl_gold_2026-11-10_trimmed.xml").replace(
            '<Ref agencyID="IMF.STA" id="IRFCL"', '<Ref agencyID="IMF.STA" id="IFS"')
        with self.assertRaises(imf.ImfContractError):
            imf.validate_irfcl_header(body)

    def test_a_non_monthly_series_is_a_contract_error(self):
        body = fixture("irfcl_gold_2026-11-10_trimmed.xml").replace(
            'FREQUENCY="M"', 'FREQUENCY="Q"', 1)
        with self.assertRaises(imf.ImfContractError):
            imf.validate_irfcl_header(body)

    def test_no_reserve_asset_sector_is_a_contract_error(self):
        body = fixture("irfcl_gold_2026-11-10_trimmed.xml").replace(
            'SECTOR="S1XS1311"', 'SECTOR="S1X"')
        with self.assertRaises(imf.ImfContractError):
            imf.validate_irfcl_header(body)


class T07HeaderOnly(unittest.TestCase):
    def test_a_200_with_no_series_is_a_failure(self):
        # D-0045: no data is not news. The L112 rule, now via the guard.
        db = memory_db()
        empty = response(200, fixture("irfcl_header_only.xml"))
        with mock.patch.object(imf.requests, "get", return_value=empty):
            with self.assertRaises(ValueError):
                imf.run_imf_gold_fetch(db, min_countries=1)
        self.assertEqual(gold_rows(db).count(), 0)
        self.assertEqual(len(imf_logs(db, "failed")), 1)


class T08CoverageFloor(unittest.TestCase):
    def test_a_truncated_publication_does_not_succeed(self):
        db = memory_db()
        self.assertEqual(imf.IMF_MIN_COUNTRIES, 40)
        three = response(200, three_country_fixture())
        self.assertEqual(
            {o["iso"] for o in parse_imf_gold(three.text)[0]}, {"USA", "CHN", "DEU"})
        with mock.patch.object(imf.requests, "get", return_value=three):
            with self.assertRaises(imf.ImfContractError) as cm:
                imf.run_imf_gold_fetch(db)
        self.assertIn("3", str(cm.exception))
        self.assertEqual(gold_rows(db).count(), 0)
        self.assertEqual(len(imf_logs(db, "failed")), 1)


class T09RetryPolicy(unittest.TestCase):
    def test_one_5xx_is_retried_once_then_succeeds(self):
        db = memory_db()
        busy = response(503, "busy", "text/plain")
        with mock.patch.object(imf.requests, "get", side_effect=[busy, ok_trimmed()]) as get, \
             mock.patch.object(imf.time, "sleep") as slept:
            result = imf.run_imf_gold_fetch(db, min_countries=1)
        self.assertEqual(get.call_count, 2)
        slept.assert_called_once_with(10)
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["inserted"], 17)

    def test_two_5xx_fail_loudly(self):
        db = memory_db()
        with mock.patch.object(imf.requests, "get", side_effect=[
                response(503, "busy", "text/plain"), response(503, "busy", "text/plain")]) as get, \
             mock.patch.object(imf.time, "sleep"):
            with self.assertRaises(imf.ImfUpstreamError) as cm:
                imf.run_imf_gold_fetch(db, min_countries=1)
        self.assertEqual(get.call_count, 2)
        self.assertIn("503", str(cm.exception))
        self.assertEqual(len(imf_logs(db, "failed")), 1)
        self.assertEqual(gold_rows(db).count(), 0)

    def test_a_429_is_retried(self):
        with mock.patch.object(imf.requests, "get", side_effect=[
                response(429, "slow down", "text/plain"), ok_trimmed()]) as get, \
             mock.patch.object(imf.time, "sleep"):
            imf.fetch_imf_gold()
        self.assertEqual(get.call_count, 2)

    def test_a_connection_error_is_retried_then_classified(self):
        with mock.patch.object(imf.requests, "get", side_effect=[
                requests.ConnectionError("boom"), requests.Timeout("slow")]) as get, \
             mock.patch.object(imf.time, "sleep"):
            with self.assertRaises(imf.ImfUpstreamError) as cm:
                imf.fetch_imf_gold()
        self.assertEqual(get.call_count, 2)
        self.assertIn("Timeout", str(cm.exception))


class T10Mapping(unittest.TestCase):
    def test_the_aggregates_excluded_are_exactly_these(self):
        self.assertEqual(NOT_COUNTRIES, {"G163", "EZB", "WBG"})

    def test_it_writes_the_wgc_series(self):
        self.assertEqual(imf.GOLD_METRIC_CODE, GOLD_METRIC["code"])

    def test_the_ounce_conversion_round_trips(self):
        self.assertAlmostEqual(8133.53 * OZ_PER_TONNE, 261499000, delta=200)


class T11BackfillIsIdempotent(unittest.TestCase):
    def test_a_rerun_updates_and_never_duplicates(self):
        db = memory_db()
        with mock.patch.object(imf.requests, "get", side_effect=lambda *a, **k: ok_trimmed()):
            first = imf.run_imf_gold_fetch(db, min_countries=1)
            count_after_first = gold_rows(db).count()
            second = imf.run_imf_gold_fetch(db, min_countries=1)
        self.assertEqual((first["inserted"], first["updated"]), (17, 0))
        self.assertEqual((second["inserted"], second["updated"]), (0, 17))
        self.assertEqual(count_after_first, 17)
        self.assertEqual(gold_rows(db).count(), 17)
        self.assertEqual(first["structure_version"], "12.0.0")
        self.assertEqual(first["countries"], 6)
        dupes = (
            db.query(TimeSeries.metric_id, TimeSeries.country_id, TimeSeries.date, func.count())
            .group_by(TimeSeries.metric_id, TimeSeries.country_id, TimeSeries.date)
            .having(func.count() > 1).all()
        )
        self.assertEqual(dupes, [])
        self.assertEqual([l.status for l in imf_logs(db)], ["partial", "partial"])


class T12Continuity(unittest.TestCase):
    def test_a_stale_month_is_updated_in_place(self):
        db = memory_db()
        metric = db.query(Metric).filter_by(code=imf.GOLD_METRIC_CODE).one()
        usa = db.query(Country).filter_by(iso_code="USA").one()
        db.add(TimeSeries(metric_id=metric.id, country_id=usa.id,
                          date=datetime(2026, 6, 1), value=Decimal("8000.00")))
        db.commit()
        with mock.patch.object(imf.requests, "get", return_value=ok_trimmed()):
            imf.run_imf_gold_fetch(db, min_countries=1)
        june = gold_rows(db).filter_by(country_id=usa.id, date=datetime(2026, 6, 1)).all()
        self.assertEqual(len(june), 1, "a second row for USA 2026-06")
        self.assertEqual(june[0].value, Decimal("8133.53"))
        july = gold_rows(db).filter_by(country_id=usa.id, date=datetime(2026, 7, 1)).all()
        self.assertEqual(len(july), 1)


class T13TheRouteSaysUpstream(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_db] = lambda: None
        cls.client = TestClient(app, raise_server_exceptions=False)

    def test_an_upstream_error_is_a_502(self):
        boom = imf.ImfUpstreamError("IMF upstream HTTP 404 at /x: No such dataflow found")
        with mock.patch.object(imf, "run_imf_gold_fetch", side_effect=boom):
            r = self.client.post("/api/fetch/gold-reserves-imf")
        self.assertEqual(r.status_code, 502, r.text)
        self.assertIn("404", r.json()["detail"])

    def test_a_contract_error_is_a_502(self):
        with mock.patch.object(imf, "run_imf_gold_fetch",
                               side_effect=imf.ImfContractError("unexpected INDICATOR")):
            r = self.client.post("/api/fetch/gold-reserves-imf")
        self.assertEqual(r.status_code, 502, r.text)

    def test_our_own_bug_is_still_a_500(self):
        with mock.patch.object(imf, "run_imf_gold_fetch", side_effect=KeyError("oops")):
            r = self.client.post("/api/fetch/gold-reserves-imf")
        self.assertEqual(r.status_code, 500, r.text)


class T14SchedulerIsolation(unittest.TestCase):
    def test_a_failing_fetch_does_not_escape_into_apscheduler(self):
        with mock.patch.object(sched, "get_session", return_value=mock.MagicMock()), \
             mock.patch.object(sched, "run_imf_gold_fetch",
                               side_effect=RuntimeError("IMF upstream HTTP 404")), \
             self.assertLogs("pipelines.scheduler", level="ERROR") as logs:
            self.assertIsNone(sched.scheduled_imf_gold_fetch())
        self.assertTrue(any("IMF" in line for line in logs.output))


class TestGoldReserveChangesIsManual(unittest.TestCase):
    """SPEC @0.1 6a. A static workbook with no add_job is not a scheduled feed."""

    def _check(self, key):
        return next((s for s in CHECKS if s["key"] == key), None)

    def test_it_is_not_declared_as_scheduled(self):
        self.assertNotIn("Gold_Reserve_Changes", sched.SCHEDULED_PIPELINES)

    def test_it_no_longer_shares_the_imf_gold_verdict(self):
        self.assertNotIn("Gold_Reserve_Changes", self._check("gold_reserves")["pipelines"])

    def test_it_has_its_own_manual_check_on_its_own_metric(self):
        src = self._check("gold_reserve_changes")
        self.assertIsNotNone(src, "no freshness check for GOLD_RESERVE_CHANGES")
        self.assertEqual(src["patterns"], ["GOLD_RESERVE_CHANGES"])
        self.assertEqual(src["pipelines"], ["Gold_Reserve_Changes"])
        self.assertTrue(src.get("manual_upload"))
        self.assertIn("MANUAL", src["note"])
        # PROVISIONAL ~200 d: data runs to 2026-06, ~133 d old on 2026-11-10.
        self.assertGreater(src["max_age_days"], 133)
        self.assertLessEqual(src["max_age_days"], 240)


@unittest.skipUnless(os.environ.get("SENTINEL_LIVE_TESTS") == "1",
                     "live IMF call; set SENTINEL_LIVE_TESTS=1")
class T15LiveIrfcl(unittest.TestCase):
    """T15. One real GET to api.imf.org. No database."""

    def test_the_live_feed_meets_the_contract(self):
        start = (date.today() - timedelta(days=365)).strftime("%Y-%m")
        xml = imf.fetch_imf_gold(start_period=start)
        self.assertEqual(imf.validate_irfcl_response(xml), imf.structure_version(xml))
        obs, rejected, duplicates = parse_imf_gold(xml)
        countries = {o["iso"] for o in obs}
        self.assertGreaterEqual(len(countries), imf.IMF_MIN_COUNTRIES)
        usa = [o for o in obs if o["iso"] == "USA"]
        self.assertTrue(usa, "USA missing from the live feed")
        self.assertTrue(all(7000 < o["tonnes"] < 9000 for o in usa))
        newest = max(o["date"] for o in obs).date()
        self.assertGreaterEqual(newest, date.today() - timedelta(days=120))
        self.assertEqual(duplicates, [])
        print(f"\nT15 live: url={imf.imf_gold_url()} start={start} "
              f"structure_version={imf.structure_version(xml)} countries={len(countries)} "
              f"obs={len(obs)} newest={newest} rejected={len(rejected)} "
              f"usa_latest={usa[-1]['date']:%Y-%m}={usa[-1]['tonnes']}t")


if __name__ == "__main__":
    unittest.main()
