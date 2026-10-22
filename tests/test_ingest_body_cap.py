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


if __name__ == "__main__":
    unittest.main()
