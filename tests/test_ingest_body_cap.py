"""Sentinel D-0116 follow-up: ingest routes refuse oversized bodies early.

Self-contained: no fixtures, no database, no network. The route function is
called directly with a fake Request, so the test sees whether the body was
read at all. Cases T-0146..T-0149 (heading T-0116).
"""
import asyncio
import unittest
from unittest import mock

from fastapi import HTTPException

from api import routes
from pipelines import bdi_bmk

CAP = bdi_bmk.MAX_BODY_BYTES


class FakeRequest:
    def __init__(self, headers=None, chunks=()):
        self.headers = {k.lower(): v for k, v in (headers or {}).items()}
        self._chunks = list(chunks)
        self.body_calls = 0
        self.chunks_read = 0

    async def body(self):
        self.body_calls += 1
        return b"".join(self._chunks)

    async def stream(self):
        for c in self._chunks:
            self.chunks_read += 1
            yield c


def call(req):
    return asyncio.run(routes.ingest_bdi_mfn_bmk(req, db=object()))


def ingest_routes():
    return [r for r in routes.router.routes
            if "/ingest/" in getattr(r, "path", "") and "POST" in getattr(r, "methods", set())]


class IngestBodyCap(unittest.TestCase):
    def test_t0146_content_length_over_cap_is_413_before_reading(self):
        req = FakeRequest({"Content-Length": str(CAP + 1)}, [b"x"])
        with mock.patch.object(bdi_bmk, "ingest") as ing:
            with self.assertRaises(HTTPException) as ctx:
                call(req)
        self.assertEqual(ctx.exception.status_code, 413)
        self.assertEqual((req.body_calls, req.chunks_read), (0, 0), "body was read")
        ing.assert_not_called()

    def test_t0147_bad_content_length_is_400_before_reading(self):
        for bad in ("abc", "-5"):
            req = FakeRequest({"Content-Length": bad}, [b"x"])
            with mock.patch.object(bdi_bmk, "ingest") as ing:
                with self.assertRaises(HTTPException) as ctx:
                    call(req)
            self.assertEqual(ctx.exception.status_code, 400, bad)
            self.assertEqual((req.body_calls, req.chunks_read), (0, 0))
            ing.assert_not_called()

    def test_t0148_no_content_length_stops_reading_past_cap(self):
        chunk = b"y" * (256 * 1024)
        n = CAP // len(chunk) + 4
        req = FakeRequest({}, [chunk] * n)
        with mock.patch.object(bdi_bmk, "ingest") as ing:
            with self.assertRaises(HTTPException) as ctx:
                call(req)
        self.assertEqual(ctx.exception.status_code, 413)
        self.assertEqual(req.body_calls, 0, "whole body buffered via request.body()")
        self.assertLess(req.chunks_read, n, "kept reading after the cap")
        ing.assert_not_called()

    def test_t0149_body_at_cap_still_ingests(self):
        body = b"z" * CAP
        req = FakeRequest({"Content-Length": str(CAP)}, [body[:CAP // 2], body[CAP // 2:]])
        with mock.patch.object(bdi_bmk, "ingest", return_value={"ok": True}) as ing:
            self.assertEqual(call(req), {"ok": True})
        self.assertEqual(ing.call_args[0][1], body)

    def test_every_ingest_route_is_capped(self):
        found = ingest_routes()
        self.assertTrue(found, "no POST /ingest/ routes found")
        for r in found:
            req = FakeRequest({"Content-Length": str(CAP + 1)}, [b"x"])
            with self.assertRaises(HTTPException) as ctx:
                asyncio.run(r.endpoint(req, db=object()))
            self.assertEqual(ctx.exception.status_code, 413, r.path)
            self.assertEqual((req.body_calls, req.chunks_read), (0, 0), r.path)


class T0150FullAppBasicAuth(unittest.TestCase):
    """Through the whole app: BasicAuthMiddleware runs before the route, and
    an authenticated oversized upload still gets the early 413. The credential
    is a throwaway set only here (settings patched), never the real secret."""

    USER, PASSWORD = "t0150-user", "t0150-not-a-real-password"

    def setUp(self):
        from config import settings
        from database.connection import get_db
        from main import app
        for name, val in (("auth_username", self.USER), ("auth_password", self.PASSWORD)):
            p = mock.patch.object(settings, name, val)
            p.start()
            self.addCleanup(p.stop)

        def _no_db():
            yield object()

        app.dependency_overrides[get_db] = _no_db
        self.addCleanup(app.dependency_overrides.pop, get_db, None)
        self.app = app

    def post(self, body, auth):
        import httpx

        async def go():
            transport = httpx.ASGITransport(app=self.app, raise_app_exceptions=False)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
                return await c.post("/api/ingest/bdi-mfn-bmk", content=body, auth=auth)
        return asyncio.run(go())

    def test_t0150_auth_then_413(self):
        big = b"x" * (CAP + 1)
        with mock.patch.object(bdi_bmk, "ingest") as ing:
            self.assertEqual(self.post(big, None).status_code, 401)
            self.assertEqual(self.post(big, (self.USER, "wrong")).status_code, 401)
            r = self.post(big, (self.USER, self.PASSWORD))
        self.assertEqual(r.status_code, 413, r.text)
        ing.assert_not_called()


class T0151MonthlyLimit55(unittest.TestCase):
    """F-0129: Italy BMK0100 and ECB IRS monthly are fresh to 55 days after
    the month ends, stale at 56 (the F-0089 precedent)."""

    def test_t0151_fresh_at_55_stale_at_56(self):
        from datetime import datetime, timedelta
        from pipelines.freshness_watchdog import CHECKS, _age_from_coverage, _classify, coverage_end
        got = {c["key"]: c for c in CHECKS}
        start = datetime(2026, 9, 1)
        end = coverage_end(start, "month")
        self.assertEqual(end, datetime(2026, 9, 30))
        for key in ("foreign_bonds_it", "ecb_irs_monthly"):
            c = got[key]
            self.assertEqual((c["period"], c["max_age_days"]), ("month", 55), key)
            for days, want in ((55, "ok"), (56, "stale")):
                age = _age_from_coverage(start, c["period"], end + timedelta(days=days))
                self.assertEqual(_classify(age, c["max_age_days"]), want, f"{key} at {days}")


if __name__ == "__main__":
    unittest.main()
