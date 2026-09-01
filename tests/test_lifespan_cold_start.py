"""D-0019 / AT-0012 / T-0018: cold-start must not block health on FRED.

Lifespan keeps init_db + start_scheduler, then yields. Heavy FRED/TIC/gold/stress
work is a one-shot APScheduler job and must not run synchronously before readiness.
"""
import inspect
import unittest
from unittest.mock import MagicMock, patch

from main import lifespan
from pipelines import scheduler as sched


class TestLifespanDoesNotBlockOnFred(unittest.IsolatedAsyncioTestCase):
    async def test_lifespan_yields_without_calling_fred_tic_gold_stress(self):
        with patch("main.init_db") as mock_init, \
             patch("main.start_scheduler") as mock_start, \
             patch("main.stop_scheduler") as mock_stop, \
             patch("pipelines.fred_fetcher.run_fred_fetch") as mock_fred, \
             patch("pipelines.treasury_holdings.run_treasury_holdings_fetch") as mock_tic, \
             patch("pipelines.gold_reserves.run_gold_reserves_fetch") as mock_gold, \
             patch("pipelines.stress_score_v2.run_stress_score_calculation") as mock_stress, \
             patch("main.run_fred_fetch", create=True) as mock_fred_main, \
             patch("main.run_treasury_holdings_fetch", create=True) as mock_tic_main:
            async with lifespan(MagicMock()):
                mock_init.assert_called_once()
                mock_start.assert_called_once()
                mock_fred.assert_not_called()
                mock_tic.assert_not_called()
                mock_gold.assert_not_called()
                mock_stress.assert_not_called()
                mock_fred_main.assert_not_called()
                mock_tic_main.assert_not_called()
            mock_stop.assert_called_once()

    def test_lifespan_source_has_no_blocking_fetch_calls(self):
        source = inspect.getsource(lifespan)
        self.assertIn("init_db()", source)
        self.assertIn("start_scheduler()", source)
        self.assertNotIn("run_fred_fetch", source)
        self.assertNotIn("run_treasury_holdings_fetch", source)
        self.assertNotIn("run_gold_reserves_fetch", source)
        self.assertNotIn("run_stress_score_calculation", source)
        self.assertNotIn("run_cds_fetch", source)


class TestStartupFetchJob(unittest.TestCase):
    def test_start_scheduler_queues_immediate_startup_job_after_start(self):
        with patch.object(sched.settings, "scheduler_enabled", True), \
             patch.object(sched, "scheduler") as mock_sched:
            sched.start_scheduler()

            names = [name for name, _, _ in mock_sched.method_calls]
            self.assertEqual(names[-2], "start")
            self.assertEqual(names[-1], "add_job")

            startup = mock_sched.add_job.call_args_list[-1]
            self.assertIs(startup.args[0], sched.scheduled_startup_fetches)
            self.assertEqual(startup.kwargs.get("id"), "startup_fetches")
            self.assertIsNotNone(startup.kwargs.get("next_run_time"))

    def test_startup_fetches_continue_after_fred_failure(self):
        with patch.object(sched, "scheduled_fred_fetch", side_effect=RuntimeError("fred down")), \
             patch.object(sched, "scheduled_treasury_fetch") as mock_tic, \
             patch.object(sched, "scheduled_gold_fetch") as mock_gold, \
             patch.object(sched, "scheduled_stress_score") as mock_stress:
            sched.scheduled_startup_fetches()
            mock_tic.assert_called_once()
            mock_gold.assert_called_once()
            mock_stress.assert_called_once()


class TestCdsSessionClosed(unittest.TestCase):
    def test_scheduled_cds_fetch_closes_session(self):
        db = MagicMock()
        with patch.object(sched, "get_session", return_value=db), \
             patch.object(
                 sched,
                 "run_cds_fetch",
                 return_value={"status": "success", "inserted": 0, "updated": 0},
             ):
            sched.scheduled_cds_fetch()
        db.close.assert_called_once()

    def test_scheduled_cds_fetch_closes_session_on_error(self):
        db = MagicMock()
        with patch.object(sched, "get_session", return_value=db), \
             patch.object(sched, "run_cds_fetch", side_effect=RuntimeError("scrape failed")):
            sched.scheduled_cds_fetch()
        db.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
