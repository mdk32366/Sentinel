"""Sentinel D-0112: France - Banque de France Webstat TEC, daily, 2/5/7/10/30Y.

Fixtures are SYNTHETIC-FROM-DOCS (tests/fixtures/foreign_bonds/PROVENANCE.md):
no Webstat key was available, so the CSV is shaped from Banque de France's API
guide (https://webstat.banque-france.fr/pages/guide-migration-api/?flg=fr-fr)
with invented values. Nothing here reaches a network.

Each fail-closed negative has a positive twin on the same path, so a guard
that failed unconditionally could not pass on its own:
  - no WEBSTAT_API_KEY      -> logged and skipped, no request, nothing written
  - 404 "dataset observations does not exist" (the guide's bad/missing-key
    answer) -> failed at once, nothing written, the key never logged
  - a 200 with only the header -> retried, then failed, nothing written
  - a series missing from the answer, or one we did not ask for -> failed
"""
import io
import logging
import unittest
import urllib.error
from datetime import datetime, timedelta
from decimal import Decimal
from email.message import Message
from unittest import mock
from urllib.parse import parse_qs, unquote, urlparse

from sqlalchemy import func

from database.models import Metric, TimeSeries, UpdateLog
from tests.test_foreign_bonds import Opener, Sleeps, fixture, session, ts_count

KEY = "test-webstat-key-not-real"
TENORS = (2, 5, 7, 10, 30)
SERIES = [f"FM.D.FR.EUR.FR2.BB.FRMOYTEC{t}.HSTA" for t in TENORS]
CODES = [f"FB_FR_{t:02d}Y" for t in TENORS]
EXPORT = "webstat.banque-france.fr/api/explore/v2.1/catalog/datasets/observations/exports/csv"


class HeaderOpener(Opener):
    """An Opener that also records the headers each request carried."""

    def __init__(self, routes):
        super().__init__(routes)
        self.headers = []

    def __call__(self, url, headers=None):
        self.headers.append(dict(headers or {}))
        return super().__call__(url, headers)


def ok():
    return HeaderOpener([("observations/exports/csv", [fixture("bdf_tec.csv")])])


def not_found(url="https://" + EXPORT):
    body = fixture("bdf_tec_404.json")
    return urllib.error.HTTPError(url, 404, "Not Found", Message(), io.BytesIO(body))


def rejected(url="https://" + EXPORT):
    # Measured 2026-10-22 (F-0118): a key the gateway does not know, sent in
    # the documented header, answers 401 - not the guide's 404.
    body = fixture("bdf_tec_401.json")
    return urllib.error.HTTPError(url, 401, "Unauthorized", Message(), io.BytesIO(body))


def query_of(url):
    q = parse_qs(urlparse(url).query)
    return {k: unquote(v[0]) for k, v in q.items()}


class Parse(unittest.TestCase):
    def test_the_fixture_parses_to_forty_rows_in_five_series(self):
        from pipelines.bdf_tec import parse_bdf_tec
        rows = parse_bdf_tec(fixture("bdf_tec.csv"))
        self.assertEqual(len(rows), 40)
        self.assertEqual(sorted({r[0] for r in rows}), sorted(CODES))
        latest = {code: max((r for r in rows if r[0] == code), key=lambda r: r[1]) for code in CODES}
        self.assertEqual(latest["FB_FR_10Y"][1], datetime(2026, 10, 21))
        self.assertEqual(latest["FB_FR_10Y"][2], Decimal("3.35"))
        self.assertEqual(latest["FB_FR_30Y"][2], Decimal("4.26"))

    def test_a_null_obs_value_is_skipped_not_zero(self):
        # The guide: obs_value "peut etre null"; in CSV that is an empty cell.
        from pipelines.bdf_tec import parse_bdf_tec
        body = fixture("bdf_tec.csv").replace(b";2026-10-21;2026-10-21;3.35", b";2026-10-21;2026-10-21;", 1)
        self.assertNotEqual(body, fixture("bdf_tec.csv"))
        rows = parse_bdf_tec(body)
        self.assertEqual(len(rows), 39)
        self.assertNotIn(Decimal("0"), {r[2] for r in rows})

    def test_a_series_we_did_not_ask_for_is_drift(self):
        from pipelines.bdf_tec import parse_bdf_tec
        from pipelines.foreign_bond_common import SchemaDrift
        body = fixture("bdf_tec.csv") + b"FM.D.FR.EUR.FR2.BB.FRMOYTEC15.HSTA;2026-10-21;2026-10-21;3.70\n"
        with self.assertRaises(SchemaDrift):
            parse_bdf_tec(body)

    def test_a_missing_series_is_drift(self):
        from pipelines.bdf_tec import parse_bdf_tec
        from pipelines.foreign_bond_common import SchemaDrift
        body = b"\n".join(l for l in fixture("bdf_tec.csv").split(b"\n") if b"TEC30." not in l)
        with self.assertRaises(SchemaDrift):
            parse_bdf_tec(body)

    def test_a_renamed_column_is_drift(self):
        from pipelines.bdf_tec import parse_bdf_tec
        from pipelines.foreign_bond_common import SchemaDrift
        body = fixture("bdf_tec.csv").replace(b";obs_value", b";value", 1)
        with self.assertRaises(SchemaDrift):
            parse_bdf_tec(body)


class Request(unittest.TestCase):
    def test_the_documented_export_endpoint_and_filter(self):
        from pipelines.bdf_tec import series_url
        url = series_url(start="2026-10-08")
        self.assertTrue(url.startswith("https://" + EXPORT + "?"), url)
        q = query_of(url)
        where = q["where"]
        self.assertTrue(where.startswith("series_key in ("), where)
        for key in SERIES:
            self.assertIn(f'"{key}"', where)
        self.assertIn("time_period_start>=date'2026-10-08'", where)
        self.assertEqual(q["order_by"], "time_period_start")
        self.assertNotIn("apikey", url.lower())

    def test_the_key_goes_in_the_authorization_header(self):
        from pipelines.bdf_tec import run_bdf_tec
        opener = ok()
        result = run_bdf_tec(session(), api_key=KEY, opener=opener, sleep=Sleeps())
        self.assertEqual(result["status"], "success")
        self.assertEqual(len(opener.calls), 1)
        self.assertEqual(opener.headers[0]["Authorization"], f"Apikey {KEY}")
        self.assertNotIn(KEY, opener.calls[0])

    def test_daily_window_and_five_year_backfill(self):
        from pipelines.bdf_tec import run_bdf_tec
        today = datetime.utcnow().date()
        for backfill, lo, hi in ((False, 7, 21), (True, 1825, 1826)):
            with self.subTest(backfill=backfill):
                opener = ok()
                run_bdf_tec(session(), backfill=backfill, api_key=KEY, opener=opener, sleep=Sleeps())
                where = query_of(opener.calls[0])["where"]
                start = datetime.strptime(where.split("date'")[1][:10], "%Y-%m-%d").date()
                self.assertTrue(lo <= (today - start).days <= hi, (today, start))


class Run(unittest.TestCase):
    def test_success_writes_forty_rows(self):
        from pipelines.bdf_tec import PIPELINE_NAME, run_bdf_tec
        db = session()
        result = run_bdf_tec(db, api_key=KEY, opener=ok(), sleep=Sleeps())
        self.assertEqual((result["status"], result["inserted"], result["updated"], result["latest_date"]),
                         ("success", 40, 0, "2026-10-21"))
        self.assertEqual(ts_count(db), 40)
        self.assertEqual(sorted(m.code for m in db.query(Metric).all()), sorted(CODES))
        self.assertEqual({m.category for m in db.query(Metric).all()}, {"foreign_bond"})
        log = db.query(UpdateLog).one()
        self.assertEqual((log.pipeline_name, log.status, log.records_inserted), (PIPELINE_NAME, "success", 40))

    def test_twice_is_idempotent(self):
        from pipelines.bdf_tec import run_bdf_tec
        db = session()
        run_bdf_tec(db, api_key=KEY, opener=ok(), sleep=Sleeps())
        again = run_bdf_tec(db, api_key=KEY, opener=ok(), sleep=Sleeps())
        self.assertEqual((again["inserted"], again["updated"]), (0, 40))
        self.assertEqual(ts_count(db), 40)


class MissingKey(unittest.TestCase):
    def test_no_key_is_logged_and_skipped(self):
        from pipelines.bdf_tec import run_bdf_tec
        for missing in ("", "   ", None):
            with self.subTest(key=repr(missing)):
                db = session()
                opener = ok()
                with mock.patch("pipelines.bdf_tec.settings") as s:
                    s.webstat_api_key = missing
                    with self.assertLogs("pipelines.bdf_tec", level="WARNING") as logs:
                        result = run_bdf_tec(db, opener=opener, sleep=Sleeps())
                self.assertEqual(result["status"], "skipped")
                self.assertEqual((result["inserted"], result["updated"], result["latest_date"]), (0, 0, None))
                self.assertEqual(opener.calls, [])
                self.assertEqual(ts_count(db), 0)
                self.assertEqual(db.query(func.count(UpdateLog.id)).scalar(), 0)
                self.assertTrue(any("WEBSTAT_API_KEY" in line for line in logs.output), logs.output)

    def test_the_positive_twin_reads_the_key_from_settings(self):
        from pipelines.bdf_tec import run_bdf_tec
        opener = ok()
        with mock.patch("pipelines.bdf_tec.settings") as s:
            s.webstat_api_key = KEY
            result = run_bdf_tec(session(), opener=opener, sleep=Sleeps())
        self.assertEqual(result["status"], "success")
        self.assertEqual(opener.headers[0]["Authorization"], f"Apikey {KEY}")

    def test_settings_accepts_the_env_var(self):
        # Settings forbids unknown inputs; without the field, setting the
        # secret would stop the app booting.
        from config import Settings
        self.assertEqual(Settings.model_fields["webstat_api_key"].default, "")
        with mock.patch.dict("os.environ", {"WEBSTAT_API_KEY": KEY, "AUTH_PASSWORD": "x"}):
            self.assertEqual(Settings().webstat_api_key, KEY)

    def test_the_scheduled_job_never_crashes_without_a_key(self):
        from pipelines import scheduler as sched
        db = session()
        with mock.patch.object(sched, "get_session", return_value=db), \
             mock.patch("pipelines.bdf_tec.settings") as s, \
             mock.patch("pipelines.foreign_bond_common._urlopen",
                        side_effect=AssertionError("no request without a key")):
            s.webstat_api_key = ""
            sched.scheduled_bdf_tec_fetch()
        self.assertEqual(ts_count(db), 0)


class FailClosed(unittest.TestCase):
    def test_404_dataset_does_not_exist_fails_at_once(self):
        from pipelines.bdf_tec import PIPELINE_NAME, run_bdf_tec
        db = session()
        opener = HeaderOpener([("observations/exports/csv", [not_found()])])
        sleeps = Sleeps()
        result = run_bdf_tec(db, api_key=KEY, opener=opener, sleep=sleeps)
        self.assertEqual(result["status"], "failed")
        self.assertEqual((result["inserted"], result["updated"]), (0, 0))
        self.assertEqual(len(opener.calls), 1)       # a 4xx is not retried
        self.assertEqual(list(sleeps), [])
        self.assertEqual(ts_count(db), 0)
        log = db.query(UpdateLog).one()
        self.assertEqual((log.pipeline_name, log.status, log.records_inserted), (PIPELINE_NAME, "failed", 0))
        self.assertIn("http=404", log.error_message)
        self.assertIn("WEBSTAT_API_KEY", log.error_message)
        self.assertNotIn(KEY, log.error_message)
        self.assertNotIn(KEY, " ".join(result["errors"]))

    def test_401_invalid_key_fails_at_once_and_names_the_key(self):
        from pipelines.bdf_tec import PIPELINE_NAME, run_bdf_tec
        db = session()
        opener = HeaderOpener([("observations/exports/csv", [rejected()])])
        sleeps = Sleeps()
        result = run_bdf_tec(db, api_key=KEY, opener=opener, sleep=sleeps)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(len(opener.calls), 1)
        self.assertEqual(list(sleeps), [])
        self.assertEqual(ts_count(db), 0)
        log = db.query(UpdateLog).one()
        self.assertEqual((log.pipeline_name, log.status, log.records_inserted), (PIPELINE_NAME, "failed", 0))
        self.assertIn("http=401", log.error_message)
        self.assertIn("WEBSTAT_API_KEY", log.error_message)
        self.assertNotIn(KEY, log.error_message)

    def test_the_error_fixtures_are_the_measured_bodies(self):
        import json
        self.assertEqual(json.loads(fixture("bdf_tec_404.json")),
                         {"error_code": "NotFoundResource",
                          "message": "The requested dataset observations does not exist."})
        self.assertEqual(json.loads(fixture("bdf_tec_401.json")), {"error": "API key is not valid"})

    def test_header_only_200_is_retried_then_failed(self):
        from pipelines.bdf_tec import PIPELINE_NAME, run_bdf_tec
        db = session()
        opener = HeaderOpener([("observations/exports/csv", [fixture("bdf_tec_header_only.csv")])])
        sleeps = Sleeps()
        result = run_bdf_tec(db, api_key=KEY, opener=opener, sleep=sleeps)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(len(opener.calls), 3)
        self.assertEqual(list(sleeps), [4.0, 8.0])
        self.assertEqual(ts_count(db), 0)
        log = db.query(UpdateLog).one()
        self.assertEqual((log.pipeline_name, log.status, log.records_inserted), (PIPELINE_NAME, "failed", 0))

    def test_header_only_then_data_succeeds(self):
        from pipelines.bdf_tec import run_bdf_tec
        db = session()
        opener = HeaderOpener([("observations/exports/csv",
                                [fixture("bdf_tec_header_only.csv"), fixture("bdf_tec.csv")])])
        result = run_bdf_tec(db, api_key=KEY, opener=opener, sleep=Sleeps())
        self.assertEqual((result["status"], result["inserted"]), ("success", 40))
        self.assertEqual(len(opener.calls), 2)

    def test_a_missing_series_writes_nothing(self):
        from pipelines.bdf_tec import run_bdf_tec
        db = session()
        body = b"\n".join(l for l in fixture("bdf_tec.csv").split(b"\n") if b"TEC7." not in l)
        result = run_bdf_tec(db, api_key=KEY, opener=HeaderOpener([("exports/csv", [body])]), sleep=Sleeps())
        self.assertEqual(result["status"], "failed")
        self.assertEqual(ts_count(db), 0)


class Wiring(unittest.TestCase):
    def test_metrics(self):
        from pipelines.bdf_tec import METRICS
        self.assertEqual([m["code"] for m in METRICS], CODES)
        for m, key in zip(METRICS, SERIES):
            self.assertEqual(m["category"], "foreign_bond")
            self.assertIn(key, m["description"])
            self.assertIn("D-0112", m["description"])
            self.assertLessEqual(len(m["description"]), 500)

    def test_scheduled_weekdays_at_10_utc(self):
        from tests.test_scheduler_jobs import SchedulerHarness
        harness = SchedulerHarness()
        harness.addCleanup = self.addCleanup
        trigger = str(harness._register()["bdf_tec"].trigger)
        self.assertIn("day_of_week='mon-fri'", trigger)
        self.assertIn("hour='10'", trigger)
        self.assertIn("minute='0'", trigger)

    def test_pipeline_name_declared(self):
        from pipelines import scheduler as sched
        from pipelines.freshness_watchdog import declared_pipeline_names
        self.assertIn("BdF_TEC", sched.SCHEDULED_PIPELINES)
        self.assertIn("BdF_TEC", declared_pipeline_names())

    def test_first_run_backfills(self):
        from pipelines import scheduler as sched
        db = session()
        seen = []

        def fake(db_, backfill=False, **kw):
            seen.append(backfill)
            return {"status": "success", "inserted": 0, "updated": 0, "errors": [], "latest_date": None}

        with mock.patch.object(sched, "get_session", return_value=db), \
             mock.patch.object(sched, "run_bdf_tec", fake):
            sched.scheduled_bdf_tec_fetch()
        self.assertEqual(seen, [True])


class Freshness(unittest.TestCase):
    def _status(self, days_ago):
        from pipelines.freshness_watchdog import get_freshness_report
        db = session()
        m = Metric(code="FB_FR_10Y", name="x", category="foreign_bond", unit="%", source="t")
        db.add(m)
        db.commit()
        db.add(TimeSeries(metric_id=m.id, country_id=None,
                          date=datetime.utcnow() - timedelta(days=days_ago), value=3.0))
        db.commit()
        return next(s for s in get_freshness_report(db)["sources"] if s["key"] == "foreign_bonds_fr")

    def test_four_day_window(self):
        self.assertEqual(self._status(3)["status"], "ok")
        self.assertEqual(self._status(3)["max_age_days"], 4)
        self.assertEqual(self._status(5)["status"], "stale")

    def test_the_check(self):
        from pipelines.freshness_watchdog import CHECKS
        fr = next(c for c in CHECKS if c["key"] == "foreign_bonds_fr")
        self.assertEqual((fr["pipelines"], fr["max_age_days"], fr["period"], fr["patterns"]),
                         (["BdF_TEC"], 4, "day", ["FB\\_FR\\_%"]))


if __name__ == "__main__":
    unittest.main()
