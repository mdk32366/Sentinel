"""D-0094 G7 — /pipeline-status gold price fields; /api/health unchanged."""
import datetime
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("AUTH_USERNAME", "test")
os.environ.setdefault("AUTH_PASSWORD", "test-password-not-a-secret")

import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.models import Base, UpdateLog


def _session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


class TestPipelineStatusGoldPrice(unittest.TestCase):
    def setUp(self):
        self.db = _session()
        self.addCleanup(self.db.close)
        now = datetime.datetime.utcnow()
        self.db.add(UpdateLog(
            pipeline_name="Gold_Reserves", status="success",
            records_inserted=1, records_updated=0, error_message=None,
            started_at=now - datetime.timedelta(days=2),
            completed_at=now - datetime.timedelta(days=2),
        ))
        self.db.add(UpdateLog(
            pipeline_name="Gold_Spot_Price", status="success",
            records_inserted=1, records_updated=0, error_message=None,
            started_at=now - datetime.timedelta(days=7),
            completed_at=now - datetime.timedelta(days=7),
        ))
        self.db.add(UpdateLog(
            pipeline_name="Gold_Spot_Price", status="failed",
            records_inserted=0, records_updated=0,
            error_message="FETCH_BLOCKED http=403 cf=1 host=prices.lbma.org.uk | x",
            started_at=now - datetime.timedelta(hours=1),
            completed_at=now - datetime.timedelta(hours=1),
        ))
        self.db.commit()

    def test_gold_price_fields_from_spot_pipeline(self):
        from api.routes import pipeline_status
        from api.schemas import HealthResponse
        with patch("api.routes.scheduler") as sched:
            sched.running = True
            result = pipeline_status(db=self.db)
        self.assertIsInstance(result, HealthResponse)
        self.assertEqual(result.last_gold_price_status, "failed")
        self.assertEqual(result.last_gold_price_failure, "blocked")
        self.assertIsNotNone(result.last_gold_price_run)
        self.assertIsNotNone(result.last_gold_price_success)
        self.assertIsNotNone(result.last_gold_update)
        self.assertLess(result.last_gold_price_success, result.last_gold_price_run)
        self.assertNotEqual(result.last_gold_update, result.last_gold_price_run)


class TestPipelineStatusAuthAndHealth(unittest.IsolatedAsyncioTestCase):
    async def test_requires_auth(self):
        from main import app
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.get("/api/pipeline-status")
        self.assertEqual(r.status_code, 401)

    async def test_health_unchanged(self):
        from main import app
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.get("/api/health")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"status": "healthy"})


if __name__ == "__main__":
    unittest.main()
