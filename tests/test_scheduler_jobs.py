"""ORDER-01 B5 — the scheduler registers what it claims, and nothing when off.

Offline. `scheduler.start()` is stubbed, so jobs are registered and inspected
but never executed; no pipeline runs and nothing touches a database.

Two properties, both previously untested:

  1. Every job carries a misfire grace period, coalescing and a single
     instance. Only the CDS job used to, because it was a per-job keyword that
     every other job forgot.
  2. `SCHEDULER_ENABLED=false` registers NOTHING. A job added at import time
     bypasses that switch entirely, so the switch has to be proved rather than
     read.
"""
import unittest
from unittest import mock

from apscheduler.schedulers.background import BackgroundScheduler

from pipelines import scheduler as sched

EXPECTED_CRON_JOBS = {
    "fred_fetch",
    "treasury_fetch",
    "stress_score",
    "gold_fetch",
    "cds_multi_tenor_job",
    "treasury_direct",
    "freshness_check",
    "gold_price",
    "composite_snapshot",
    # F-0091. Added when the job was: broad money growth had no entry here
    # because it had no entry in the scheduler, and this set pins what exists
    # rather than what ought to. It catches a job that DISAPPEARS, not one that
    # was never there - which is why the pipeline-name coverage check lives in
    # tests/test_money_supply_fetcher.py against the watchdog's own list of
    # sources, the only place that says what is supposed to stay fresh.
    "money_supply",
}
EXPECTED_ONE_SHOTS = {"startup_fetches", "startup_cds_fetch"}


class SchedulerHarness(unittest.TestCase):
    def _register(self, enabled=True):
        """Run start_scheduler against a throwaway scheduler, started PAUSED.

        Paused rather than stubbed. APScheduler 3.x applies `job_defaults` when
        a pending job is really added at start-up, so a scheduler whose start()
        is stubbed leaves every job pending with its defaults unset - and a test
        reading them would report absent settings for a correctly configured
        scheduler. Paused gives the real registration path with nothing
        executing, including the one-shots whose next_run_time is now.
        """
        fake = BackgroundScheduler(job_defaults=sched.JOB_DEFAULTS)
        real_start = fake.start
        self.addCleanup(lambda: fake.running and fake.shutdown(wait=False))
        with mock.patch.object(sched, "scheduler", fake), \
             mock.patch.object(fake, "start",
                               lambda *a, **k: real_start(paused=True)), \
             mock.patch.object(sched.settings, "scheduler_enabled", enabled):
            sched.start_scheduler()
        return {job.id: job for job in fake.get_jobs()}


class TestJobRegistration(SchedulerHarness):
    def test_every_expected_job_is_registered(self):
        jobs = self._register()
        missing = (EXPECTED_CRON_JOBS | EXPECTED_ONE_SHOTS) - set(jobs)
        self.assertEqual(missing, set(), f"jobs not registered: {sorted(missing)}")

    def test_the_two_new_jobs_are_present(self):
        """The whole point of ORDER-01 B5."""
        jobs = self._register()
        self.assertIn("treasury_direct", jobs)
        self.assertIn("freshness_check", jobs)

    def test_treasury_direct_runs_weekdays_at_21_utc(self):
        """After Treasury publishes, before FRED's 02:00 run."""
        trigger = str(self._register()["treasury_direct"].trigger)
        self.assertIn("hour='21'", trigger)
        self.assertIn("day_of_week='mon-fri'", trigger)

    def test_freshness_runs_daily_at_05_utc(self):
        trigger = str(self._register()["freshness_check"].trigger)
        self.assertIn("hour='5'", trigger)

    def test_money_supply_runs_monthly_after_the_watchdog(self):
        """F-0091. Monthly on the 14th, at 05:30 - after the 05:00 watchdog, so
        a failed fetch shows up in the next night's report rather than a month
        later."""
        trigger = str(self._register()["money_supply"].trigger)
        self.assertIn("day='14'", trigger)
        self.assertIn("hour='5'", trigger)
        self.assertIn("minute='30'", trigger)

    def test_no_unexpected_job_appeared(self):
        jobs = self._register()
        extra = set(jobs) - (EXPECTED_CRON_JOBS | EXPECTED_ONE_SHOTS)
        self.assertEqual(extra, set(), f"unexpected jobs: {sorted(extra)}")


class TestJobDefaults(SchedulerHarness):
    def test_every_job_has_a_misfire_grace_period(self):
        """A missed fire - restart, deploy, sleep - must still run, not vanish."""
        for job_id, job in self._register().items():
            self.assertEqual(job.misfire_grace_time, 3600, f"{job_id} has none")

    def test_every_job_coalesces(self):
        """Several missed fires collapse into one run, not a burst."""
        for job_id, job in self._register().items():
            self.assertTrue(job.coalesce, f"{job_id} does not coalesce")

    def test_no_job_may_overlap_itself(self):
        """A 3-minute FRED run must not start again while still writing."""
        for job_id, job in self._register().items():
            self.assertEqual(job.max_instances, 1, f"{job_id} allows overlap")


class TestDisableSwitch(SchedulerHarness):
    def test_disabled_registers_nothing_at_all(self):
        """Including CDS, which used to be added at import time and so ignored
        this setting completely."""
        self.assertEqual(self._register(enabled=False), {})

    def test_the_switch_actually_discriminates(self):
        """An always-empty result would pass the test above and prove nothing."""
        self.assertGreater(len(self._register(enabled=True)), 0)


if __name__ == "__main__":
    unittest.main()
