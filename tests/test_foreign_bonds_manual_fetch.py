"""Sentinel D-0111 follow-up: POST /api/fetch/foreign-bonds/{source}.

A manual trigger for the Foreign Bonds jobs (T-0111 addendum). It runs the
same wrapper the scheduler runs (`_scheduled_foreign_bonds`) and answers
{status, inserted, updated, latest_date}. Writes stay behind Basic Auth; the
D-0093 proof cookie is read-only, so a POST with it alone is a 403.

Every case first asserts the route is registered, so it goes red on a tree
without the route rather than passing on a generic 401/403/404. No network:
the Bundesbank transport is replaced by canned fixture bytes, and the
database is an in-memory SQLite shared across the request thread.
"""
import base64
import functools
import unittest
from datetime import timedelta
from pathlib import Path
from unittest import mock

import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from api import proof_access
from config import settings
from database.models import Base, TimeSeries, UpdateLog
from main import app
from tests.test_proof_access import _iso, _new_token, _sha, _utcnow

FIX = Path(__file__).resolve().parent / "fixtures" / "foreign_bonds"
ROUTE = "/api/fetch/foreign-bonds/{source}"


def _basic():
    raw = base64.b64encode(f"{settings.auth_username}:{settings.auth_password}".encode()).decode()
    return {"Authorization": f"Basic {raw}"}


async def _send(method, path, headers=None):
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.request(method, path, headers=headers or {})


class _Resp:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self.body


class Base_(unittest.IsolatedAsyncioTestCase):
    def assertRouteExists(self):
        paths = {getattr(r, "path", None) for r in app.routes}
        self.assertIn(ROUTE, paths, "the manual Foreign Bonds trigger is not registered")


class Auth(Base_):
    async def test_unauthenticated_post_is_401(self):
        self.assertRouteExists()
        with mock.patch("pipelines.scheduler._scheduled_foreign_bonds") as job:
            response = await _send("POST", "/api/fetch/foreign-bonds/bundesbank")
        self.assertEqual(response.status_code, 401)
        job.assert_not_called()

    async def test_a_proof_cookie_post_is_403(self):
        self.assertRouteExists()
        proof_access._reset_lockout()
        self.addCleanup(proof_access._reset_lockout)
        token = _new_token()
        expires = _iso(_utcnow() + timedelta(hours=1))
        with mock.patch.object(settings, "sentinel_proof_token_sha256", _sha(token)), \
                mock.patch.object(settings, "sentinel_proof_expires_at", expires):
            transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                grant = await client.post("/__proof", content=f"token={token}", headers={
                    "Fly-Forwarded-Proto": "https",
                    "Content-Type": "application/x-www-form-urlencoded",
                })
            self.assertEqual(grant.status_code, 303, grant.text)
            cookie = grant.headers["set-cookie"].split(";", 1)[0]
            with mock.patch("pipelines.scheduler._scheduled_foreign_bonds") as job:
                response = await _send("POST", "/api/fetch/foreign-bonds/bundesbank",
                                       headers={"Cookie": cookie})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.text, "Proof access is read-only")
        job.assert_not_called()


class Routing(Base_):
    async def test_an_unknown_source_is_404(self):
        self.assertRouteExists()
        with mock.patch("pipelines.scheduler._scheduled_foreign_bonds") as job:
            response = await _send("POST", "/api/fetch/foreign-bonds/ecb", headers=_basic())
        self.assertEqual(response.status_code, 404)
        job.assert_not_called()

    async def test_every_registered_source_is_one_line_in_the_table(self):
        self.assertRouteExists()
        from pipelines.scheduler import FOREIGN_BOND_JOBS
        self.assertEqual(set(FOREIGN_BOND_JOBS), {"bundesbank", "boe", "mof"})


class FailsClosed(Base_):
    def setUp(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                               poolclass=StaticPool)
        Base.metadata.create_all(engine)
        self.Session = sessionmaker(bind=engine)

    async def test_a_header_only_bundesbank_200_is_failed_with_0_rows(self):
        self.assertRouteExists()
        import pipelines.bundesbank_yields as bb
        from pipelines.foreign_bond_common import fetch_bytes as real_fetch
        header_only = (FIX / "bundesbank_header_only.csv").read_bytes()
        calls, sleeps = [], []

        def opener(url, headers=None):
            calls.append(url)
            return _Resp(header_only)

        fetch = functools.partial(real_fetch, opener=opener, sleep=sleeps.append)
        with mock.patch("pipelines.scheduler.get_session", side_effect=self.Session), \
                mock.patch.object(bb, "fetch_bytes", fetch):
            response = await _send("POST", "/api/fetch/foreign-bonds/bundesbank?backfill=1",
                                   headers=_basic())
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(set(body), {"status", "inserted", "updated", "latest_date"})
        self.assertNotEqual(body["status"], "success")
        self.assertEqual(body["status"], "failed")
        self.assertEqual((body["inserted"], body["updated"], body["latest_date"]), (0, 0, None))
        db = self.Session()
        self.assertEqual(db.query(TimeSeries).count(), 0)
        log = db.query(UpdateLog).one()
        self.assertEqual((log.pipeline_name, log.status, log.records_inserted),
                         ("Bundesbank_Yields", "failed", 0))
        self.assertEqual(len(calls), 3)          # retried, then refused
        self.assertIn("startPeriod=", calls[0])  # ?backfill=1 reached the run

    async def test_a_good_bundesbank_run_reports_its_counts(self):
        """The positive twin: the same path succeeds on real fixture bytes."""
        self.assertRouteExists()
        import pipelines.bundesbank_yields as bb
        from pipelines.foreign_bond_common import fetch_bytes as real_fetch

        def opener(url, headers=None):
            for t in ("R02XX", "R05XX", "R07XX", "R10XX", "R30XX"):
                if t in url:
                    return _Resp((FIX / f"bundesbank_{t}.csv").read_bytes())
            raise AssertionError(url)

        fetch = functools.partial(real_fetch, opener=opener, sleep=lambda s: None)
        with mock.patch("pipelines.scheduler.get_session", side_effect=self.Session), \
                mock.patch.object(bb, "fetch_bytes", fetch):
            response = await _send("POST", "/api/fetch/foreign-bonds/bundesbank", headers=_basic())
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), {"status": "success", "inserted": 40,
                                           "updated": 0, "latest_date": "2026-10-21"})


class StartupFill(unittest.TestCase):
    def test_the_startup_one_shot_runs_every_foreign_bond_job(self):
        from pipelines import scheduler
        self.assertTrue(hasattr(scheduler, "FOREIGN_BOND_JOBS"))
        with mock.patch.object(scheduler, "scheduled_fred_fetch"), \
                mock.patch.object(scheduler, "scheduled_treasury_fetch"), \
                mock.patch.object(scheduler, "scheduled_gold_fetch"), \
                mock.patch.object(scheduler, "scheduled_stress_score"), \
                mock.patch.object(scheduler, "_scheduled_foreign_bonds") as job:
            scheduler.scheduled_startup_fetches()
        labels = [c.args[0] for c in job.call_args_list]
        self.assertEqual(len(labels), len(scheduler.FOREIGN_BOND_JOBS))


class AdminButtons(unittest.TestCase):
    def test_the_admin_tab_lists_a_trigger_per_source(self):
        from pipelines.scheduler import FOREIGN_BOND_JOBS
        js = (Path(__file__).resolve().parents[1] / "ui" / "src" / "lib" / "adminActions.js").read_text()
        for source in FOREIGN_BOND_JOBS:
            with self.subTest(source=source):
                self.assertIn(f'endpoint: "/fetch/foreign-bonds/{source}"', js)


if __name__ == "__main__":
    unittest.main()
