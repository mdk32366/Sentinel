"""Sentinel D-0115, Foreign Bonds batch 2 phase 2a (spec@0.3 §15).

Six keyless daily fetchers: Bank of Canada Valet, Riksbank SWEA, RBA F2,
Norges Bank, Banco de España TI_1_3 and the ECB euro-area yield curves.
Display only. Every fixture is synthetic (fixtures/foreign_bonds/PROVENANCE.md).
"""
import hashlib
import io
import json
import re
import sys
import unittest
import urllib.error
from datetime import datetime
from decimal import Decimal
from email.message import Message
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
# Captured on 48b6ea0 before any batch 2a change (T-0121).
GOLDEN_SHA256 = "05e1a1d3705383332ac4ef2c09b76fe59f6ab2e0763f785e144ad83f612a3f89"
COMPOSITE_SHA256 = "72d700db24ec41384b1f1a5aab35a7097d04c477540ab4a19bcd2876c46bad23"


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
    """Returns ``items`` in turn (the last repeats); exceptions are raised."""

    def __init__(self, *items):
        self.items = list(items)
        self.calls = []

    def __call__(self, url, headers=None):
        self.calls.append(url)
        item = self.items.pop(0) if len(self.items) > 1 else self.items[0]
        if isinstance(item, BaseException):
            raise item
        return _Resp(item)


def http_error(status):
    return urllib.error.HTTPError("https://example.invalid/x", status, "err", Message(), io.BytesIO(b""))


def by_code(rows):
    out = {}
    for code, when, value in rows:
        out.setdefault(code, {})[when.strftime("%Y-%m-%d")] = value
    return out


# ------------------------------------------------------------------ T-0115
class T0115Parsers(unittest.TestCase):
    def test_boc_valet(self):
        from pipelines.boc_valet import parse_boc
        got = by_code(parse_boc(fx("boc_valet.json")))
        self.assertEqual(set(got), {"FB_CA_02Y", "FB_CA_03Y", "FB_CA_05Y", "FB_CA_07Y",
                                    "FB_CA_10Y", "FB_CA_30Y"})
        self.assertEqual(got["FB_CA_10Y"], {"2026-10-19": Decimal("3.40"), "2026-10-20": Decimal("3.50")})
        # LONG is the 30Y slot (A-entry); RRB is not a nominal tenor and is ignored.
        self.assertEqual(got["FB_CA_30Y"]["2026-10-19"], Decimal("3.50"))
        # A blank cell is missing, not zero.
        self.assertEqual(set(got["FB_CA_07Y"]), {"2026-10-19"})

    def test_riksbank(self):
        from pipelines.riksbank_swea import parse_riksbank
        got = by_code(parse_riksbank(fx("riksbank_SEGVB10YC.json"), 10))
        self.assertEqual(got, {"FB_SE_10Y": {"2026-10-19": Decimal("2.501"),
                                             "2026-10-20": Decimal("2.512")}})

    def test_rba_with_cr_and_blank_tails(self):
        from pipelines.rba_f2 import parse_rba
        got = by_code(parse_rba(fx("rba_f2.csv")))
        self.assertEqual(set(got), {"FB_AU_02Y", "FB_AU_03Y", "FB_AU_05Y", "FB_AU_10Y"})
        self.assertEqual(got["FB_AU_10Y"], {"2026-10-13": Decimal("4.104"), "2026-10-14": Decimal("4.114")})
        self.assertEqual(set(got["FB_AU_03Y"]), {"2026-10-13"})

    def test_norges(self):
        from pipelines.norges_govt import parse_norges
        got = by_code(parse_norges(fx("norges_govt.csv")))
        self.assertEqual(set(got), {"FB_NO_03Y", "FB_NO_05Y", "FB_NO_07Y", "FB_NO_10Y"})
        self.assertEqual(got["FB_NO_10Y"], {"2026-10-19": Decimal("4.200"), "2026-10-20": Decimal("4.210")})

    def test_runs_write_rows(self):
        from pipelines import boc_valet, norges_govt, rba_f2, riksbank_swea
        cases = (
            (boc_valet.run_boc_valet, fx("boc_valet.json"), 11),
            (riksbank_swea.run_riksbank_swea, fx("riksbank_SEGVB10YC.json"), 8),
            (rba_f2.run_rba_f2, fx("rba_f2.csv"), 7),
            (norges_govt.run_norges_govt, fx("norges_govt.csv"), 8),
        )
        for run, body, rows in cases:
            with self.subTest(run=run.__name__):
                db = session()
                res = run(db, backfill=True, opener=Opener(body), sleep=lambda s: None)
                self.assertEqual(res["status"], "success", res)
                self.assertEqual(db.query(func.count(TimeSeries.id)).scalar(), rows)
                for m in db.query(Metric).all():
                    self.assertEqual(m.category, "foreign_bond")
                    self.assertIn("D-0115", m.description)


# ------------------------------------------------------------------ T-0116
class T0116FailClosed(unittest.TestCase):
    def _assert_failed(self, run, opener):
        db = session()
        res = run(db, backfill=True, opener=opener, sleep=lambda s: None)
        self.assertEqual(res["status"], "failed", res)
        self.assertEqual(res["inserted"], 0)
        self.assertEqual(db.query(func.count(TimeSeries.id)).scalar(), 0)

    def test_header_only_and_empty(self):
        from pipelines import boc_valet, ecb_yc, norges_govt, rba_f2, riksbank_swea
        for run, body in ((boc_valet.run_boc_valet, fx("boc_valet_empty.json")),
                          (riksbank_swea.run_riksbank_swea, fx("riksbank_empty.json")),
                          (rba_f2.run_rba_f2, fx("rba_f2_header_only.csv")),
                          (norges_govt.run_norges_govt, fx("norges_header_only.csv")),
                          (ecb_yc.run_ecb_yc, fx("ecb_yc_header_only.csv")),
                          (rba_f2.run_rba_f2, b""),
                          (norges_govt.run_norges_govt, b"")):
            with self.subTest(run=run.__name__, n=len(body)):
                self._assert_failed(run, Opener(body))

    def test_http_errors(self):
        from pipelines import bde_ti13, boc_valet, ecb_yc, norges_govt, rba_f2
        for run in (boc_valet.run_boc_valet, rba_f2.run_rba_f2, norges_govt.run_norges_govt,
                    bde_ti13.run_bde_ti13, ecb_yc.run_ecb_yc):
            for status in (404, 503):
                with self.subTest(run=run.__name__, status=status):
                    self._assert_failed(run, Opener(http_error(status)))

    def test_riksbank_429_stops_after_one_call(self):
        from pipelines import riksbank_swea
        opener = Opener(http_error(429), fx("riksbank_SEGVB10YC.json"))
        self._assert_failed(riksbank_swea.run_riksbank_swea, opener)
        self.assertEqual(len(opener.calls), 1, opener.calls)


# ------------------------------------------------------------------ T-0117
class T0117Jobs(unittest.TestCase):
    def test_ten_sources_and_six_job_ids(self):
        from pipelines import scheduler
        # Sentinel D-0116 (batch 2b-1) adds three: 13 (T-0141).
        self.assertEqual(len(scheduler.FOREIGN_BOND_JOBS), 13)
        for name in ("BoC_Valet", "Riksbank_SWEA", "RBA_F2", "Norges_GOVT", "BdE_TI13", "ECB_YC"):
            self.assertIn(name, scheduler.SCHEDULED_PIPELINES)
        src = (ROOT / "pipelines" / "scheduler.py").read_text(encoding="utf-8")
        for job_id in ("boc_valet", "riksbank_yields", "rba_f2", "norges_yields", "bde_ti13", "ecb_yc"):
            self.assertIn(f'"{job_id}"', src)


# ------------------------------------------------------------------ T-0118
class T0118Freshness(unittest.TestCase):
    def test_limits(self):
        from pipelines.freshness_watchdog import CHECKS
        got = {c["key"]: c["max_age_days"] for c in CHECKS}
        for key, days in (("foreign_bonds_ca", 4), ("foreign_bonds_se", 4), ("foreign_bonds_au", 12),
                          ("foreign_bonds_no", 4), ("foreign_bonds_es", 4), ("foreign_bonds_ea", 4)):
            self.assertEqual(got.get(key), days, key)


# ------------------------------------------------------------------ T-0119
class T0119HtmlBody(unittest.TestCase):
    def test_every_csv_fetcher_rejects_html(self):
        from pipelines import bde_ti13, boc_valet, ecb_yc, norges_govt, rba_f2, riksbank_swea
        html = fx("html_body.html")
        for run in (rba_f2.run_rba_f2, norges_govt.run_norges_govt, bde_ti13.run_bde_ti13,
                    ecb_yc.run_ecb_yc, boc_valet.run_boc_valet, riksbank_swea.run_riksbank_swea):
            with self.subTest(run=run.__name__):
                db = session()
                res = run(db, backfill=True, opener=Opener(html), sleep=lambda s: None)
                self.assertEqual(res["status"], "failed", res)
                self.assertEqual(db.query(func.count(TimeSeries.id)).scalar(), 0)
        # with a BOM and in lower case too
        from pipelines.foreign_bond_common import SchemaDrift, reject_html
        with self.assertRaises(SchemaDrift):
            reject_html(b"\xef\xbb\xbf  <!doctype html>", "x")
        reject_html(b"Series ID,FCMYGBAG2D", "x")


# ------------------------------------------------------------------ T-0121 / T-0131
class T0121CompositeInvariant(unittest.TestCase):
    def test_golden_and_scorer_hashes_unchanged(self):
        self.assertEqual(hashlib.sha256(GOLDEN.read_bytes()).hexdigest(), GOLDEN_SHA256)
        self.assertEqual(hashlib.sha256(COMPOSITE.read_bytes()).hexdigest(), COMPOSITE_SHA256)

    def test_batch2a_rows_change_no_composite_byte(self):
        """The golden fixture (stand-in for the 41 countries) plus fresh FB rows for CA, SE, AU,
        NO, ES and both EA curves scores byte-identically to the golden."""
        sys.path.insert(0, str(ROOT / "tests"))
        import composite_golden_fixture as cgf
        import test_d0113_scorer_golden as g

        real_build = cgf.build

        def build_plus():
            db = real_build()
            codes = ([f"FB_CA_{t:02d}Y" for t in (2, 3, 5, 7, 10, 30)]
                     + [f"FB_ES_{t:02d}Y" for t in (3, 5, 10, 15)]
                     + [f"FB_{c}_10Y" for c in ("SE", "AU", "NO")]
                     + [f"FB_EA_{k}_{t:02d}Y" for k in ("AAA", "ALL") for t in (2, 5, 7, 10, 30)])
            for code in codes:
                m = Metric(code=code, name=code, category="foreign_bond", unit="%", source="fixture")
                db.add(m)
                db.flush()
                for d in (datetime(2026, 10, 20), datetime(2026, 10, 21)):
                    db.add(TimeSeries(metric_id=m.id, country_id=None, date=d, value=3.0))
            db.commit()
            return db

        with mock.patch.object(g, "build", build_plus):
            out = g.payload()
        self.assertEqual(out, GOLDEN.read_text(encoding="utf-8"))
        # The 41-country list lives in the production countries table, not in
        # code; the offline golden fixture is its stand-in. The new codes carry
        # no country_id and no country is named EA, so none can join the list.
        self.assertNotIn("EA", {iso for iso, _ in cgf.COUNTRIES})


# ------------------------------------------------------------------ T-0122 / T-0131
class T0122ScoringSurfaceUnchanged(unittest.TestCase):
    def test_sovereign_and_dim4_sets(self):
        js = CONSTANTS.read_text(encoding="utf-8")
        sov = js[js.index("export const SOVEREIGN_YIELD_CODES"):]
        sov = sov[: sov.index("};")]
        self.assertEqual(hashlib.sha256(sov.encode()).hexdigest()[:16], SOV_SHA16)
        self.assertNotIn("FB_", sov)
        tracked = (ROOT / "ui" / "src" / "hooks" / "useMarketSeries.js").read_text(encoding="utf-8")
        tracked = tracked[tracked.index("export const TRACKED_CODES"):]
        tracked = tracked[: tracked.index("];")]
        self.assertEqual(hashlib.sha256(tracked.encode()).hexdigest()[:16], TRACKED_SHA16)
        from pipelines import composite_stress
        self.assertEqual(composite_stress.FB_DIM4_CODES, {"DEU": "FB_DE_10Y", "GBR": "FB_GB_10Y",
                                                          "JPN": "FB_JP_10Y", "FRA": "FB_FR_10Y"})
        scorer = COMPOSITE.read_text(encoding="utf-8")
        for cc in ("CA", "SE", "AU", "NO", "ES", "EA"):
            self.assertNotIn(f"FB_{cc}", scorer)
        for iso in ("CAN", "SWE", "AUS", "NOR", "ESP"):
            self.assertNotIn(iso, composite_stress.FB_DIM4_CODES)

    def test_ea_is_not_a_country(self):
        js = CONSTANTS.read_text(encoding="utf-8")
        card = js[js.index("export const FB_CARD_COUNTRY"):]
        card = card[: card.index("};")]
        card = re.sub(r"//[^\n]*", "", card)
        self.assertNotIn("EA", re.findall(r"\b[A-Z]{2,3}\b", card))
        self.assertNotIn('"EA"', js[js.index("export const COUNTRIES"):][:6000]
                         if "export const COUNTRIES" in js else "")


# ------------------------------------------------------------------ T-0123
class T0123EcbYieldCurves(unittest.TestCase):
    def test_both_curves_and_tenors(self):
        from pipelines.ecb_yc import key_to_code, parse_ecb
        got = by_code(parse_ecb(fx("ecb_yc.csv")))
        expect = {f"FB_EA_{k}_{t:02d}Y" for k in ("AAA", "ALL") for t in (2, 5, 7, 10, 30)}
        self.assertEqual(set(got), expect)
        self.assertEqual(got["FB_EA_AAA_10Y"]["2026-10-20"], Decimal("2.51"))
        self.assertEqual(got["FB_EA_ALL_30Y"]["2026-10-19"], Decimal("4.00"))
        self.assertEqual(key_to_code("YC.B.U2.EUR.4F.G_N_A.SV_C_YM.SR_10Y"), "FB_EA_AAA_10Y")
        self.assertEqual(key_to_code("YC.B.U2.EUR.4F.G_N_C.SV_C_YM.SR_2Y"), "FB_EA_ALL_02Y")

    def test_an_unrequested_key_is_schema_drift(self):
        from pipelines.ecb_yc import parse_ecb
        from pipelines.foreign_bond_common import SchemaDrift
        body = fx("ecb_yc.csv").replace(b"SR_30Y", b"SR_15Y")
        with self.assertRaises(SchemaDrift):
            parse_ecb(body)

    def test_run(self):
        from pipelines.ecb_yc import run_ecb_yc
        db = session()
        res = run_ecb_yc(db, backfill=True, opener=Opener(fx("ecb_yc.csv")), sleep=lambda s: None)
        self.assertEqual(res["status"], "success", res)
        self.assertEqual(db.query(func.count(TimeSeries.id)).scalar(), 20)


# ------------------------------------------------------------------ T-0127..T-0130
class T0127BdeLatin1(unittest.TestCase):
    def test_accented_headers_survive(self):
        from pipelines.bde_ti13 import decode, parse_bde
        body = fx("bde_ti_1_3.csv")
        self.assertTrue(decode(body).startswith('"CÓDIGO DE LA SERIE"'))
        garbled = body.decode("utf-8", errors="replace")
        self.assertFalse(garbled.startswith('"CÓDIGO'))
        self.assertTrue(parse_bde(body))


class T0128BdeUnderscore(unittest.TestCase):
    def test_underscore_is_missing(self):
        from pipelines.bde_ti13 import parse_bde, run_bde_ti13
        got = by_code(parse_bde(fx("bde_ti_1_3.csv")))
        self.assertEqual(set(got["FB_ES_05Y"]), {"2026-10-19"})
        db = session()
        res = run_bde_ti13(db, backfill=True, opener=Opener(fx("bde_ti_1_3.csv")), sleep=lambda s: None)
        self.assertEqual(res["status"], "success", res)
        self.assertEqual(db.query(func.count(TimeSeries.id)).scalar(), 7)


class T0129BdeMonths(unittest.TestCase):
    def test_all_spanish_and_english_months(self):
        from pipelines.bde_ti13 import RowDateError, parse_date
        es = ["ENE", "FEB", "MAR", "ABR", "MAY", "JUN", "JUL", "AGO", "SEP", "OCT", "NOV", "DIC"]
        en = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
        for i, (a, b) in enumerate(zip(es, en), start=1):
            self.assertEqual(parse_date(f"15 {a} 2026"), datetime(2026, i, 15))
            self.assertEqual(parse_date(f"15 {b} 2026"), datetime(2026, i, 15))
        with self.assertRaises(RowDateError):
            parse_date("15 XYZ 2026")

    def test_unknown_month_skips_that_row_only(self):
        from pipelines.bde_ti13 import parse_bde
        body = fx("bde_ti_1_3.csv").replace(b'"19 OCT 2026"', b'"19 XYZ 2026"')
        got = by_code(parse_bde(body))
        self.assertEqual(set(got["FB_ES_10Y"]), {"2026-10-20"})


class T0130BdeColumnsAndFooter(unittest.TestCase):
    def test_columns_by_code_and_footer_stop(self):
        from pipelines.bde_ti13 import parse_bde
        a = by_code(parse_bde(fx("bde_ti_1_3.csv")))
        b = by_code(parse_bde(fx("bde_ti_1_3_shuffled.csv")))
        self.assertEqual(a, b)
        self.assertEqual(a["FB_ES_10Y"], {"2026-10-19": Decimal("4.001"), "2026-10-20": Decimal("4.011")})
        self.assertEqual(set(a), {"FB_ES_03Y", "FB_ES_05Y", "FB_ES_10Y", "FB_ES_15Y"})
        # the row after FUENTE/NOTAS (9.9 everywhere) is never read
        self.assertNotIn("2026-10-21", a["FB_ES_10Y"])


# Pinned from 48b6ea0 (T-0122); see test_sovereign_and_dim4_sets.
SOV_SHA16 = "4f56c542484124fc"
TRACKED_SHA16 = "1d2822fa5bd72e33"

if __name__ == "__main__":
    unittest.main()
