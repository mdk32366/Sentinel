"""D-0094 G2 / Phase B — fetcher classification, gold-api parse, no CF retry."""
import json
import logging
import unittest
from datetime import datetime, timedelta
from email.message import Message
from io import BytesIO
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.models import Base, UpdateLog
from pipelines import gold_price_fetcher as gpf
from pipelines.fetch_failure import parse_failure_prefix


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _http(code, body=b"", headers=None, url=gpf.PRIMARY_URL):
    import urllib.error
    hdrs = Message()
    for k, v in (headers or {}).items():
        hdrs[k] = v
    return urllib.error.HTTPError(url, code, "err", hdrs, BytesIO(body))


class TestFetchBytesNoRetryOnBlock(unittest.TestCase):
    def test_403_cf_one_attempt(self):
        calls = {"n": 0}

        def boom(req, timeout=45):
            calls["n"] += 1
            raise _http(
                403,
                body=b"Sorry, you have been blocked",
                headers={"server": "cloudflare"},
            )

        with patch("urllib.request.urlopen", side_effect=boom):
            with self.assertRaises(Exception):
                gpf.fetch_bytes(gpf.PRIMARY_URL, attempts=3, backoff=0.01)
        self.assertEqual(calls["n"], 1)

    def test_503_non_cf_retries_three(self):
        calls = {"n": 0}

        def boom(req, timeout=45):
            calls["n"] += 1
            raise _http(503, body=b"upstream", headers={"server": "nginx"})

        with patch("urllib.request.urlopen", side_effect=boom):
            with patch("time.sleep"):
                with self.assertRaises(Exception):
                    gpf.fetch_bytes(gpf.PRIMARY_URL, attempts=3, backoff=0.01)
        self.assertEqual(calls["n"], 3)


class TestRunClassifies(unittest.TestCase):
    def test_403_writes_fetch_blocked(self):
        db = _session()
        self.addCleanup(db.close)

        def boom(req, timeout=45):
            raise _http(
                403,
                body=b"Sorry, you have been blocked cf-error-details",
                headers={"server": "cloudflare"},
                url="https://api.gold-api.com/price/XAU",
            )

        # Primary fails blocked; fallback also fails so the run is failed.
        def boom_any(req, timeout=45):
            url = req.full_url if hasattr(req, "full_url") else str(req)
            if "worldbank" in url or "thedocs" in url:
                raise _http(500, body=b"no", headers={"server": "nginx"}, url=url)
            return boom(req, timeout)

        with patch("urllib.request.urlopen", side_effect=boom_any):
            with patch("time.sleep"):
                with self.assertLogs(level="ERROR") as cm:
                    with self.assertRaises(RuntimeError):
                        gpf.run_gold_price_fetch(db)

        row = db.query(UpdateLog).filter_by(pipeline_name="Gold_Spot_Price").one()
        self.assertEqual(row.status, "failed")
        self.assertTrue(row.error_message.startswith("FETCH_BLOCKED"))
        self.assertIn("http=403", row.error_message)
        self.assertIn("host=", row.error_message)
        self.assertNotIn("apikey=", row.error_message or "")
        self.assertEqual(parse_failure_prefix(row.error_message), "blocked")
        self.assertTrue(any("FETCH_BLOCKED" in r.getMessage() for r in cm.records))


class TestParseGoldApi(unittest.TestCase):
    def test_uses_updated_at_date(self):
        payload = {
            "price": 4165.80,
            "updatedAt": "2026-10-03T15:19:40Z",
            "symbol": "XAU",
            "currency": "USD",
        }
        # "now" is Oct 6 — age 3 days, inside 4-day window
        row = gpf.parse_gold_api(payload, now=datetime(2026, 10, 6, 12, 0, 0))
        self.assertEqual(row["date"], datetime(2026, 10, 3))
        self.assertEqual(float(row["usd"]), 4165.80)

    def test_stale_upstream(self):
        payload = {
            "price": 4165.80,
            "updatedAt": "2026-09-20T15:19:40Z",
            "symbol": "XAU",
        }
        with self.assertRaises(ValueError) as cm:
            gpf.parse_gold_api(payload, now=datetime(2026, 10, 6, 12, 0, 0))
        self.assertIn("stale_upstream", str(cm.exception))

    def test_weekend_keeps_friday(self):
        # Provider stamp Friday; fetch ostensibly Saturday — still Friday's row.
        payload = {
            "price": 4100.0,
            "updatedAt": "2026-10-02T22:00:00Z",  # Friday
        }
        row = gpf.parse_gold_api(payload, now=datetime(2026, 10, 3, 8, 0, 0))  # Sat
        self.assertEqual(row["date"], datetime(2026, 10, 2))


class TestWorldBankParse(unittest.TestCase):
    def test_parse_fixture_bytes(self):
        # Minimal synthetic xlsx via openpyxl
        import io
        import openpyxl
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Monthly Prices"
        ws.append(["World Bank Commodity Price Data (The Pink Sheet)"])
        ws.append(["monthly"])
        ws.append(["nominal"])
        ws.append(["Updated"])
        header = [None] * 70
        header[0] = None
        header[69] = "Gold ($/troy oz)"
        ws.append(header)
        ws.append([None] * 70)  # units row skipped by parser (header already set)
        # Actually parser: rows 1-4 skip, row 5 = header. So next rows are data.
        # We already appended header as row 5. Row 6+ data — but parser treats
        # first non-skipped as header. Good.
        # Wait — we also appended a units row as row 6. Fix: don't.
        # Rebuild cleanly.
        wb2 = openpyxl.Workbook()
        ws2 = wb2.active
        ws2.title = "Monthly Prices"
        for _ in range(4):
            ws2.append(["meta"])
        header = [None] * 70
        header[69] = "Gold"
        ws2.append(header)
        row = [None] * 70
        row[0] = "2026M09"
        row[69] = 4319
        ws2.append(row)
        buf = io.BytesIO()
        wb2.save(buf)
        rows = gpf.parse_world_bank_monthly(buf.getvalue())
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["date"], datetime(2026, 9, 1))
        self.assertEqual(float(rows[0]["usd"]), 4319)


if __name__ == "__main__":
    unittest.main()
