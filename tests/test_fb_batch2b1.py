"""Sentinel D-0116, Foreign Bonds batch 2 phase 2b-1: PL, IT and ECB IRS.

  * MinFin PL  - Obligacje_Hurtowe.xlsm, wholesale auction yields (FB_PL_02Y/05Y/10Y)
  * BdI BMK0100 - Banca d'Italia monthly benchmark yields (FB_IT_03Y/05Y/10Y/30Y),
                  plus the manual backup POST /api/ingest/bdi-mfn-bmk
  * ECB IRS    - monthly 10Y convergence rate for IT, ES, GR, PT, PL (FB_xx_10Y_ECB_M)

Display only. Every fixture is synthetic (fixtures/foreign_bonds/PROVENANCE.md,
rebuilt by make_fb2b1_fixtures.py). No network.
"""
import base64
import hashlib
import io
import sys
import unittest
import zipfile
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from unittest import mock

from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker

from database.models import Base, Metric, TimeSeries

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures" / "foreign_bonds"
CONSTANTS = ROOT / "ui" / "src" / "lib" / "constants.js"
GOLDEN = ROOT / "tests" / "fixtures" / "d0113_scorer_golden.json"
COMPOSITE = ROOT / "pipelines" / "composite_stress.py"
GOLDEN_SHA256 = "05e1a1d3705383332ac4ef2c09b76fe59f6ab2e0763f785e144ad83f612a3f89"
COMPOSITE_SHA256 = "72d700db24ec41384b1f1a5aab35a7097d04c477540ab4a19bcd2876c46bad23"
INGEST_ROUTE = "/api/ingest/bdi-mfn-bmk"


def fx(name):
    return (FIX / name).read_bytes()


def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


class _Resp:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self.body


class Opener:
    def __init__(self, *items):
        self.items = list(items)
        self.calls = []

    def __call__(self, url, headers=None):
        self.calls.append(url)
        item = self.items.pop(0) if len(self.items) > 1 else self.items[0]
        if isinstance(item, BaseException):
            raise item
        return _Resp(item)


def latest(db):
    out = {}
    for code, d, v in (db.query(Metric.code, TimeSeries.date, TimeSeries.value)
                       .join(TimeSeries, TimeSeries.metric_id == Metric.id).all()):
        if code not in out or d > out[code][0]:
            out[code] = (d, float(v))
    return out


def rows_count(db):
    return db.query(func.count(TimeSeries.id)).scalar()


def zip_members(*members):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in members:
            zf.writestr(name, data)
    return buf.getvalue()


NOW = datetime(2026, 10, 22)


# ------------------------------------------------------------------ T-0133
class T0133EcbIrsRun(unittest.TestCase):
    def test_backfill_writes_five_countries_month_end(self):
        from pipelines.ecb_irs import run_ecb_irs
        db = session()
        op = Opener(fx("ecb_irs.csv"))
        res = run_ecb_irs(db, backfill=True, opener=op, sleep=lambda s: None)
        self.assertEqual(res["status"], "success", res)
        self.assertEqual(rows_count(db), 9)  # PT 2026-09 is blank: missing, not zero
        got = latest(db)
        self.assertEqual(got["FB_IT_10Y_ECB_M"], (datetime(2026, 9, 30), 4.0))
        self.assertEqual(got["FB_PL_10Y_ECB_M"], (datetime(2026, 9, 30), 5.6))
        self.assertEqual(got["FB_PT_10Y_ECB_M"], (datetime(2026, 8, 31), 3.4))
        self.assertIn("IRS/M.IT+ES+GR+PT+PL.L.L40.CI.0000..N.Z", op.calls[0])
        self.assertIn("format=csvdata", op.calls[0])

    def test_rerun_is_idempotent(self):
        from pipelines.ecb_irs import run_ecb_irs
        db = session()
        run_ecb_irs(db, backfill=True, opener=Opener(fx("ecb_irs.csv")), sleep=lambda s: None)
        res = run_ecb_irs(db, backfill=True, opener=Opener(fx("ecb_irs.csv")), sleep=lambda s: None)
        self.assertEqual(res["status"], "success", res)
        self.assertEqual(rows_count(db), 9)

    def test_fail_closed(self):
        from pipelines.ecb_irs import run_ecb_irs
        bad_key = fx("ecb_irs.csv").replace(b"IRS.M.GR.L.L40", b"IRS.M.DE.L.L40", 1)
        for body in (fx("ecb_irs_header_only.csv"), b"<!DOCTYPE html><html>", bad_key,
                     fx("ecb_irs.csv").replace(b"2026-09", b"2026-9X", 1)):
            with self.subTest(body=body[:30]):
                db = session()
                res = run_ecb_irs(db, backfill=True, opener=Opener(body), sleep=lambda s: None)
                self.assertEqual(res["status"], "failed", res)
                self.assertEqual(rows_count(db), 0)


# ------------------------------------------------------------------ T-0134
class T0134BmkParse(unittest.TestCase):
    def test_csv_zip_and_italian_decimal_agree(self):
        from pipelines.bdi_bmk import parse_bmk
        a = parse_bmk(fx("bdi_bmk0100.csv"))
        self.assertEqual(a, parse_bmk(fx("bdi_bmk0100.zip")))
        self.assertEqual(a, parse_bmk(fx("bdi_bmk0100_it_decimal.csv")))
        self.assertEqual(len(a), 11)  # 3 months x 4 tenors, one blank 30Y
        by = {(c, d): float(v) for c, d, v in a}
        self.assertEqual(by[("FB_IT_10Y", datetime(2026, 9, 30))], 3.9)
        self.assertEqual(by[("FB_IT_03Y", datetime(2026, 7, 31))], 2.9)
        self.assertNotIn(("FB_IT_30Y", datetime(2026, 8, 31)), by)
        self.assertEqual({c for c, _, _ in a}, {"FB_IT_03Y", "FB_IT_05Y", "FB_IT_10Y", "FB_IT_30Y"})

    def test_run_writes_and_names_the_bmk0100_cube(self):
        from pipelines.bdi_bmk import run_bdi_bmk
        db = session()
        op = Opener(fx("bdi_bmk0100.zip"))
        res = run_bdi_bmk(db, backfill=True, opener=op, sleep=lambda s: None)
        self.assertEqual(res["status"], "success", res)
        self.assertEqual(rows_count(db), 11)
        self.assertTrue(op.calls[0].startswith("https://a2a.bancaditalia.it/"))
        self.assertTrue(op.calls[0].endswith("/BMK0100"))


# ------------------------------------------------------------------ T-0135
class T0135BmkFailClosed(unittest.TestCase):
    def test_rejects(self):
        from pipelines.bdi_bmk import run_bdi_bmk
        csv_ = fx("bdi_bmk0100.csv")
        header_only = csv_.split(b"\n", 1)[0] + b"\n"
        cases = {
            "html": b"<!DOCTYPE html><html><body>maintenance</body></html>",
            "header only": header_only,
            "daily key": csv_.replace(b"MFN_BMK.M.020.922.0.EUR.210", b"MFN_BMK.D.020.922.0.EUR.210"),
            "missing 30Y": csv_.replace(b"EUR.230", b"EUR.231"),
            "first cell": csv_.replace(b'"DATA_OSS"', b'"DATE"'),
            "bad date": csv_.replace(b"2026/09/30", b"30/09/2026"),
            "out of range": csv_.replace(b'"3.9"', b'"39"'),
            "two csv in zip": zip_members(("a.csv", csv_), ("b.csv", csv_)),
            "no csv in zip": zip_members(("a.txt", csv_)),
        }
        for name, body in cases.items():
            with self.subTest(case=name):
                db = session()
                res = run_bdi_bmk(db, backfill=True, opener=Opener(body), sleep=lambda s: None)
                self.assertEqual(res["status"], "failed", res)
                self.assertEqual(rows_count(db), 0)

    def test_zip_bomb_is_refused(self):
        from pipelines import bdi_bmk
        from pipelines.foreign_bond_common import SchemaDrift
        bomb = io.BytesIO()
        with zipfile.ZipFile(bomb, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("x.csv", b"0" * (bdi_bmk.MAX_UNZIPPED_BYTES + 1))
        with self.assertRaises(SchemaDrift):
            bdi_bmk.parse_bmk(bomb.getvalue())


# ------------------------------------------------------------------ T-0136
class T0136Ingest(unittest.TestCase):
    def test_accept_then_idempotent_with_provenance(self):
        from database.models import IngestProvenance
        from pipelines.bdi_bmk import ingest
        db = session()
        body = fx("bdi_bmk0100.zip")
        first = ingest(db, body, "matt")
        self.assertEqual((first["inserted"], first["updated"], first["unchanged"]), (11, 0, 0))
        self.assertEqual((first["min_date"], first["max_date"]), ("2026-07-31", "2026-09-30"))
        second = ingest(db, body, "matt")
        self.assertEqual((second["inserted"], second["updated"], second["unchanged"]), (0, 0, 11))
        self.assertEqual(rows_count(db), 11)
        prov = db.query(IngestProvenance).order_by(IngestProvenance.id).all()
        self.assertEqual(len(prov), 2)
        self.assertEqual(prov[0].source, "bdi-mfn-bmk")
        self.assertEqual(prov[0].uploader, "matt")
        self.assertEqual(prov[0].sha256, hashlib.sha256(body).hexdigest())
        self.assertEqual(prov[1].rows_unchanged, 11)

    def test_a_revision_counts_as_updated(self):
        from pipelines.bdi_bmk import ingest
        db = session()
        ingest(db, fx("bdi_bmk0100.csv"), "matt")
        res = ingest(db, fx("bdi_bmk0100.csv").replace(b'"3.9"', b'"3.95"'), "matt")
        self.assertEqual((res["inserted"], res["updated"], res["unchanged"]), (0, 1, 10))

    def test_rejected_upload_writes_nothing(self):
        from database.models import IngestProvenance
        from pipelines.bdi_bmk import IngestRejected, MAX_BODY_BYTES, ingest
        db = session()
        for body in (b"<html></html>", fx("bdi_bmk0100.csv").replace(b".D.", b".D.").replace(
                b"EUR.205", b"EUR.299"), b"x" * (MAX_BODY_BYTES + 1)):
            with self.assertRaises(IngestRejected):
                ingest(db, body, "matt")
        self.assertEqual(rows_count(db), 0)
        self.assertEqual(db.query(func.count(IngestProvenance.id)).scalar(), 0)


class T0136IngestRoute(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        from sqlalchemy.pool import StaticPool
        from database.connection import get_db
        from main import app
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                               poolclass=StaticPool)
        Base.metadata.create_all(engine)
        self.Session = sessionmaker(bind=engine)

        def _db():
            db = self.Session()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = _db
        self.addCleanup(app.dependency_overrides.pop, get_db, None)
        self.app = app
        paths = {getattr(r, "path", None) for r in app.routes}
        self.assertIn(INGEST_ROUTE, paths, "the BMK manual ingest route is not registered")

    async def send(self, body, headers=None):
        import httpx
        transport = httpx.ASGITransport(app=self.app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.post(INGEST_ROUTE, content=body, headers=headers or {})

    def basic(self):
        from config import settings
        raw = f"{settings.auth_username}:{settings.auth_password}".encode()
        return {"Authorization": "Basic " + base64.b64encode(raw).decode(),
                "Content-Type": "application/zip"}

    async def test_status_codes(self):
        from pipelines.bdi_bmk import MAX_BODY_BYTES
        self.assertEqual((await self.send(fx("bdi_bmk0100.zip"))).status_code, 401)
        r = await self.send(fx("bdi_bmk0100.zip"), self.basic())
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["inserted"], 11)
        r = await self.send(fx("bdi_bmk0100.zip"), self.basic())
        self.assertEqual(r.json()["unchanged"], 11)
        self.assertEqual((await self.send(b"<html>", self.basic())).status_code, 422)
        big = await self.send(b"x" * (MAX_BODY_BYTES + 1), self.basic())
        self.assertEqual(big.status_code, 413)
        with self.Session() as db:
            self.assertEqual(rows_count(db), 11)

    async def test_proof_cookie_is_403(self):
        import httpx
        from api import proof_access
        from config import settings
        from tests.test_proof_access import _iso, _new_token, _sha, _utcnow
        proof_access._reset_lockout()
        self.addCleanup(proof_access._reset_lockout)
        token = _new_token()
        with mock.patch.object(settings, "sentinel_proof_token_sha256", _sha(token)), \
                mock.patch.object(settings, "sentinel_proof_expires_at",
                                  _iso(_utcnow() + timedelta(hours=1))):
            transport = httpx.ASGITransport(app=self.app, raise_app_exceptions=False)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                grant = await client.post("/__proof", content=f"token={token}", headers={
                    "Fly-Forwarded-Proto": "https",
                    "Content-Type": "application/x-www-form-urlencoded"})
            cookie = grant.headers["set-cookie"].split(";", 1)[0]
            r = await self.send(fx("bdi_bmk0100.zip"), {"Cookie": cookie})
        self.assertEqual(r.status_code, 403)
        with self.Session() as db:
            self.assertEqual(rows_count(db), 0)


# ------------------------------------------------------------------ T-0137
class T0137AdminSurface(unittest.TestCase):
    def test_ingest_route_and_jobs_are_documented(self):
        js = (ROOT / "ui" / "src" / "lib" / "adminActions.js").read_text(encoding="utf-8")
        for needle in ("/ingest/bdi-mfn-bmk", 'id: "minfin_auctions"', 'id: "bdi_bmk"',
                       'id: "ecb_irs"', 'id: "ecb_irs_mondays"'):
            self.assertIn(needle, js)


# ------------------------------------------------------------------ T-0138
class T0138PlParse(unittest.TestCase):
    def test_auction_picks(self):
        from pipelines.minfin_pl_auctions import parse_auctions
        rows = parse_auctions(fx("minfin_obligacje_hurtowe.xlsm"))
        got = {(c, d.date().isoformat()): float(v) for c, d, v in rows}
        self.assertEqual(got, {
            ("FB_PL_02Y", "2026-10-08"): 4.8,
            ("FB_PL_05Y", "2026-10-08"): 5.6,
            ("FB_PL_10Y", "2026-10-08"): 6.0,
            ("FB_PL_02Y", "2026-10-22"): 5.0,
            ("FB_PL_05Y", "2026-10-22"): 5.8,
            ("FB_PL_10Y", "2026-10-22"): 6.2,   # DS0436 (9.5y) beats DS1034 (8.0y)
        })

    def test_since_window(self):
        from pipelines.minfin_pl_auctions import parse_auctions
        rows = parse_auctions(fx("minfin_obligacje_hurtowe.xlsm"), since=datetime(2026, 10, 9))
        self.assertEqual({d.date().isoformat() for _, d, _ in rows}, {"2026-10-22"})

    def test_buckets_and_tie(self):
        from pipelines.minfin_pl_auctions import bucket_for
        self.assertIsNone(bucket_for(1.49))
        self.assertEqual(bucket_for(1.5), 2)
        self.assertEqual(bucket_for(3.5), 5)
        self.assertEqual(bucket_for(7.0), 10)
        self.assertEqual(bucket_for(12.0), 10)
        self.assertIsNone(bucket_for(12.01))

    def test_macros_never_kept(self):
        import openpyxl
        from pipelines import minfin_pl_auctions as m
        real = openpyxl.load_workbook
        seen = {}

        def spy(*a, **k):
            seen.update(k)
            return real(*a, **k)

        with mock.patch("openpyxl.load_workbook", spy):
            m.parse_auctions(fx("minfin_obligacje_hurtowe.xlsm"))
        self.assertIs(seen.get("keep_vba"), False)
        self.assertIs(seen.get("read_only"), True)


# ------------------------------------------------------------------ T-0139
class T0139PlResolveAndFailClosed(unittest.TestCase):
    XLSM = "application/vnd.ms-excel.sheet.macroEnabled.12"

    def head_for(self, name="Obligacje_Hurtowe.xlsm", ctype=XLSM, length="22789"):
        def head(url):
            if url.endswith("000000000002"):
                return {"Content-Disposition": f"attachment; filename*=UTF-8''{name}",
                        "Content-Type": ctype, "Content-Length": length}
            return {"Content-Disposition": 'attachment; filename="Bony.xlsm"',
                    "Content-Type": self.XLSM}
        return head

    def test_resolves_by_content_disposition(self):
        from pipelines.minfin_pl_auctions import resolve_attachment
        url = resolve_attachment(fx("minfin_page.html"), self.head_for())
        self.assertEqual(url, "https://www.gov.pl/attachment/2b7486af-0000-4000-8000-000000000002")

    def test_resolve_refusals(self):
        from pipelines.foreign_bond_common import SchemaDrift
        from pipelines.minfin_pl_auctions import resolve_attachment
        for head in (self.head_for(name="Other.xlsm"), self.head_for(ctype="text/html"),
                     self.head_for(length=str(11 * 1024 * 1024))):
            with self.assertRaises(SchemaDrift):
                resolve_attachment(fx("minfin_page.html"), head)

    def test_bad_workbooks(self):
        sys.path.insert(0, str(FIX))
        import make_fb2b1_fixtures as mk
        from pipelines.foreign_bond_common import EmptyResponse, SchemaDrift
        from pipelines.minfin_pl_auctions import parse_auctions
        bad_header = [h if h != "RentŚr" else "Rentownosc" for h in mk.PL_HEADER]
        for body in (b"<!DOCTYPE html>", b"not a zip", mk.pl_xlsm(sheet="Arkusz1"),
                     mk.pl_xlsm(header=bad_header)):
            with self.assertRaises((SchemaDrift, EmptyResponse)):
                parse_auctions(body)


# ------------------------------------------------------------------ T-0140
class T0140PlRun(unittest.TestCase):
    def test_end_to_end(self):
        from pipelines.minfin_pl_auctions import run_minfin_auctions
        db = session()
        op = Opener(fx("minfin_page.html"), fx("minfin_obligacje_hurtowe.xlsm"))
        head = T0139PlResolveAndFailClosed().head_for()
        res = run_minfin_auctions(db, backfill=True, head=head, opener=op, sleep=lambda s: None)
        self.assertEqual(res["status"], "success", res)
        self.assertEqual(rows_count(db), 6)
        self.assertEqual(op.calls[0], "https://www.gov.pl/web/finance/transaction-database")
        self.assertEqual(latest(db)["FB_PL_10Y"], (datetime(2026, 10, 22), 6.2))

    def test_page_drift_writes_nothing(self):
        from pipelines.minfin_pl_auctions import run_minfin_auctions
        db = session()
        res = run_minfin_auctions(db, backfill=True, head=lambda u: {},
                                  opener=Opener(b"<html><body>no links</body></html>"),
                                  sleep=lambda s: None)
        self.assertEqual(res["status"], "failed", res)
        self.assertEqual(rows_count(db), 0)


# ------------------------------------------------------------------ T-0141
class T0141Jobs(unittest.TestCase):
    def test_thirteen_sources(self):
        from pipelines import scheduler
        self.assertEqual(len(scheduler.FOREIGN_BOND_JOBS), 13)
        for job_id in ("minfin_auctions", "bdi_bmk", "ecb_irs"):
            self.assertIn(job_id, scheduler.FOREIGN_BOND_JOBS)
        for name in ("MinFin_PL", "BdI_BMK", "ECB_IRS"):
            self.assertIn(name, scheduler.SCHEDULED_PIPELINES)

    def test_cron_triggers(self):
        from apscheduler.schedulers.background import BackgroundScheduler
        from pipelines import scheduler as sched
        fake = BackgroundScheduler(job_defaults=sched.JOB_DEFAULTS)
        real_start = fake.start
        self.addCleanup(lambda: fake.running and fake.shutdown(wait=False))
        with mock.patch.object(sched, "scheduler", fake), \
                mock.patch.object(fake, "start", lambda *a, **k: real_start(paused=True)), \
                mock.patch.object(sched.settings, "scheduler_enabled", True):
            sched.start_scheduler()
        jobs = {j.id: j for j in fake.get_jobs()}

        def fields(job_id):
            return {f.name: str(f) for f in jobs[job_id].trigger.fields}

        # Hours are UTC on the Fly host (the scheduler takes the host zone, like every job).
        f = fields("minfin_auctions")
        self.assertEqual((f["day_of_week"], f["hour"], f["minute"]), ("mon-fri", "15", "0"))
        f = fields("bdi_bmk")
        self.assertEqual((f["day_of_week"], f["day"], f["hour"], f["minute"]), ("*", "*", "8", "0"))
        f = fields("ecb_irs")
        self.assertEqual((f["day"], f["day_of_week"], f["hour"], f["minute"]), ("1-10", "*", "7", "15"))
        f = fields("ecb_irs_mondays")
        self.assertEqual((f["day"], f["day_of_week"], f["hour"], f["minute"]), ("*", "mon", "7", "15"))


# ------------------------------------------------------------------ T-0142
class T0142Freshness(unittest.TestCase):
    def test_limits_and_patterns(self):
        import fnmatch
        from pipelines.freshness_watchdog import CHECKS
        got = {c["key"]: c for c in CHECKS}
        self.assertEqual(got["foreign_bonds_pl"]["max_age_days"], 40)
        self.assertEqual(got["foreign_bonds_it"]["max_age_days"], 55)
        self.assertEqual(got["ecb_irs_monthly"]["max_age_days"], 55)
        self.assertEqual(got["foreign_bonds_it"]["period"], "month")
        self.assertEqual(got["ecb_irs_monthly"]["pipelines"], ["ECB_IRS"])

        def like(pattern, code):  # SQL LIKE with ESCAPE '\\'
            glob = pattern.replace("\\_", "\0").replace("_", "?").replace("%", "*").replace("\0", "_")
            return fnmatch.fnmatchcase(code, glob)

        # The country checks must not swallow the monthly IRS fallbacks.
        for key, own, foreign in (("foreign_bonds_pl", "FB_PL_10Y", "FB_PL_10Y_ECB_M"),
                                  ("foreign_bonds_it", "FB_IT_30Y", "FB_IT_10Y_ECB_M"),
                                  ("foreign_bonds_es", "FB_ES_15Y", "FB_ES_10Y_ECB_M")):
            pat = got[key]["patterns"][0]
            self.assertTrue(like(pat, own), key)
            self.assertFalse(like(pat, foreign), key)
        for cc in ("IT", "ES", "GR", "PT", "PL"):
            self.assertTrue(like(got["ecb_irs_monthly"]["patterns"][0], f"FB_{cc}_10Y_ECB_M"))
        self.assertFalse(like(got["ecb_irs_monthly"]["patterns"][0], "FB_IT_10Y"))


# ------------------------------------------------------------------ T-0143
class T0143CompositeInvariant(unittest.TestCase):
    def test_hashes(self):
        self.assertEqual(hashlib.sha256(GOLDEN.read_bytes()).hexdigest(), GOLDEN_SHA256)
        self.assertEqual(hashlib.sha256(COMPOSITE.read_bytes()).hexdigest(), COMPOSITE_SHA256)

    def test_batch2b1_rows_change_no_composite_byte(self):
        sys.path.insert(0, str(ROOT / "tests"))
        import composite_golden_fixture as cgf
        import test_d0113_scorer_golden as g
        real_build = cgf.build

        def build_plus():
            db = real_build()
            codes = ([f"FB_PL_{t:02d}Y" for t in (2, 5, 10)]
                     + [f"FB_IT_{t:02d}Y" for t in (3, 5, 10, 30)]
                     + [f"FB_{c}_10Y_ECB_M" for c in ("IT", "ES", "GR", "PT", "PL")])
            for code in codes:
                m = Metric(code=code, name=code, category="foreign_bond", unit="%", source="fixture")
                db.add(m)
                db.flush()
                for d in (datetime(2026, 9, 30), datetime(2026, 10, 21)):
                    db.add(TimeSeries(metric_id=m.id, country_id=None, date=d, value=4.0))
            db.commit()
            return db

        with mock.patch.object(g, "build", build_plus):
            out = g.payload()
        self.assertEqual(out, GOLDEN.read_text(encoding="utf-8"))

    def test_not_in_scoring_sets(self):
        js = CONSTANTS.read_text(encoding="utf-8")
        sov = js[js.index("export const SOVEREIGN_YIELD_CODES"):]
        sov = sov[: sov.index("};")]
        self.assertNotIn("FB_", sov)
        self.assertNotIn("ECB_M", sov)


# ------------------------------------------------------------------ T-0144
class T0144IrsParse(unittest.TestCase):
    def test_keys_and_month_end(self):
        from pipelines.ecb_irs import key_to_code, month_end, parse_irs
        self.assertEqual(key_to_code("IRS.M.PL.L.L40.CI.0000.PLN.N.Z"), "FB_PL_10Y_ECB_M")
        self.assertEqual(key_to_code("IRS.M.IT.L.L40.CI.0000.EUR.N.Z"), "FB_IT_10Y_ECB_M")
        self.assertIsNone(key_to_code("IRS.M.DE.L.L40.CI.0000.EUR.N.Z"))
        self.assertIsNone(key_to_code("IRS.M.IT.L.L22.CI.0000.EUR.N.Z"))
        self.assertEqual(month_end("2024-02"), datetime(2024, 2, 29))
        rows = parse_irs(fx("ecb_irs.csv"))
        self.assertEqual(len(rows), 9)
        self.assertTrue(all(isinstance(v, Decimal) for _, _, v in rows))
        self.assertTrue(all(d.day in (31, 30) for _, d, _ in rows))


# ------------------------------------------------------------------ T-0145
class T0145MonthlyCards(unittest.TestCase):
    """The card rules live in constants.js; vitest (fbBatch2b1.dom.test.jsx)
    renders them. This pins the static half so a Python-only run sees drift."""

    def test_constants(self):
        js = CONSTANTS.read_text(encoding="utf-8")
        self.assertIn("FB_NO_CURVE", js)
        self.assertIn("ECB_IRS_MAX_AGE_DAYS = 55", js)
        for iso in ("ITA", "POL", "GRC", "PRT"):
            self.assertIn(iso, js[js.index("FB_CARD_COUNTRY"):])


if __name__ == "__main__":
    unittest.main()
