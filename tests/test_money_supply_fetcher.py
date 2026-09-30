"""F-0091 — the money supply pipeline had no fetch, no schedule, and an
unreachable tolerance.

`money_supply` sat 637 days stale feeding composite dimension 3 (35 of 165
points). Three separate defects, and the noisy one hid the other two:

  1. No HTTP fetch. It read a local JSON and raised `FileNotFoundError` with a
     `curl` command in the message.
  2. **No scheduled job at all.** Nine pipelines had `add_job` entries; this
     one did not, so it ran only when called by hand.
  3. The watchdog's tolerance was 420 days against a series that is ~558 days
     old the day it is published — so it reported stale every night whether or
     not anyone had done anything wrong, which is how (2) went unnoticed.

Every case works on payload **objects**, never a URL, so the file runs offline.
"""
import unittest
from unittest import mock

from fastapi.routing import APIRoute

from api.routes import router
from pipelines import scheduler as sched
from pipelines.freshness_watchdog import CHECKS
from pipelines.money_supply_fetcher import (
    PLAUSIBLE_PCT_RANGE,
    WB_COUNTRIES,
    WB_INDICATOR,
    WB_URL,
    SourceRegressionError,
    fetch_money_supply,
    newest_year_offered,
)


def payload(*rows, lastupdated="2026-07-13"):
    return [{"page": 1, "lastupdated": lastupdated}, list(rows)]


def row(iso3, year, value):
    return {"countryiso3code": iso3, "date": str(year), "value": value}


class TestNewestYearOffered(unittest.TestCase):
    def test_ignores_years_whose_value_is_null(self):
        # The World Bank returns a row per country-year and nulls the years a
        # country has not reported. The newest year in the response is usually
        # null for most countries, so max(date) would claim data we do not have
        # and then the regression guard would fire on every single run.
        p = payload(
            row("ARG", 2026, None),
            row("TUR", 2026, None),
            row("ARG", 2025, 44.85),
        )
        self.assertEqual(newest_year_offered(p), 2025)

    def test_none_when_nothing_has_a_value(self):
        self.assertIsNone(newest_year_offered(payload(row("ARG", 2026, None))))

    def test_survives_a_non_numeric_date(self):
        p = payload(row("ARG", "MRV", 1.0), row("ARG", 2024, 2.0))
        self.assertEqual(newest_year_offered(p), 2024)


class TestTheUrlMatchesTheCountryList(unittest.TestCase):
    def test_every_configured_country_is_in_the_url(self):
        # The list used to exist only as a 47-code string inlined in a docstring
        # and again in an error message. Two copies of a country list is how one
        # of them loses a country.
        for code in WB_COUNTRIES:
            self.assertIn(code, WB_URL)

    def test_the_indicator_is_broad_money_growth(self):
        self.assertIn(WB_INDICATOR, WB_URL)
        self.assertEqual(WB_INDICATOR, "FM.LBL.BMNY.ZG")

    def test_no_duplicate_countries(self):
        self.assertEqual(len(WB_COUNTRIES), len(set(WB_COUNTRIES)))


class TestTheApiIsPreferredAndTheFallbackIsNamed(unittest.TestCase):
    def test_a_good_response_is_used_and_reported_as_api(self):
        good = payload(row("ARG", 2025, 44.85))
        with mock.patch("pipelines.money_supply_fetcher.requests.get") as get:
            get.return_value = mock.Mock(
                raise_for_status=mock.Mock(), json=mock.Mock(return_value=good)
            )
            out, origin = fetch_money_supply()
        self.assertEqual(origin, "api")
        self.assertEqual(out, good)

    def test_a_failed_fetch_falls_back_but_says_so(self):
        # The fallback exists so a World Bank outage does not take the tab
        # down. It must never be silent: a run that quietly served a frozen
        # file while reporting plain `success` is F-0088 with a new source.
        with mock.patch("pipelines.money_supply_fetcher.requests.get",
                        side_effect=OSError("no route to host")):
            _, origin = fetch_money_supply()
        self.assertEqual(origin, "cache")

    def test_an_empty_response_is_treated_as_a_failure_not_as_no_data(self):
        # 200 with an empty record list would otherwise wipe nothing and
        # report success, which is the "completion, not success" shape D-0045
        # was written for.
        with mock.patch("pipelines.money_supply_fetcher.requests.get") as get:
            get.return_value = mock.Mock(
                raise_for_status=mock.Mock(),
                json=mock.Mock(return_value=[{"page": 1}, []]),
            )
            _, origin = fetch_money_supply()
        self.assertEqual(origin, "cache", "an empty payload was accepted as data")


class TestPlausibility(unittest.TestCase):
    def test_the_range_admits_a_real_hyperinflation(self):
        # Argentina 2024 was 123%. Zimbabwe 2008 was orders of magnitude more.
        # A ceiling that rejected those would be discarding the exact countries
        # this metric exists to flag.
        low, high = PLAUSIBLE_PCT_RANGE
        for real in (123.09, 158.55, 44.85, -5.0):
            self.assertTrue(low <= real <= high, f"{real} rejected")

    def test_the_range_rejects_a_units_change(self):
        # An index LEVEL arriving where a percentage belongs is the F-0075
        # shape: Russia's 13,775bps "CDS spread" was an ISDA coupon.
        low, high = PLAUSIBLE_PCT_RANGE
        self.assertFalse(low <= 1e9 <= high)
        self.assertFalse(low <= -250.0 <= high, "money supply cannot fall 250%")


class TestTheRegressionGuardExists(unittest.TestCase):
    def test_it_is_an_error_not_a_log_line(self):
        # D-0027: a guard that stands aside is not a guard. For an annual
        # series dated to 1 January, "is the newest offered year in the
        # database" is the only sharp question available.
        self.assertTrue(issubclass(SourceRegressionError, RuntimeError))


class TestItIsActuallyScheduled(unittest.TestCase):
    """Defect 2, and the one that made the other two matter."""

    def test_a_job_function_exists(self):
        self.assertTrue(hasattr(sched, "scheduled_money_supply_fetch"))

    def test_the_job_is_registered_with_the_scheduler(self):
        import inspect

        body = inspect.getsource(sched)
        self.assertIn("scheduled_money_supply_fetch,", body)
        self.assertIn('id="money_supply"', body)

    def test_the_job_calls_the_pipeline(self):
        import inspect

        self.assertIn(
            "run_money_supply_fetch",
            inspect.getsource(sched.scheduled_money_supply_fetch),
        )

    def test_every_pipeline_the_watchdog_monitors_is_scheduled(self):
        # The general form of defect 2, and the reason it is asserted
        # structurally rather than by grepping the module: a job id is a
        # scheduler handle ("money_supply") while a pipeline name is what lands
        # in UpdateLog ("Broad_Money_Growth"), and no rule maps one to the
        # other. A string sweep over the source would have passed on the token
        # "money_supply" while Broad_Money_Growth remained unscheduled.
        #
        # Note the watchdog's own "declared but not yet run" report would NOT
        # have caught this: Broad_Money_Growth had run once, by hand. "Ran at
        # some point" and "is scheduled" are different facts, and only the
        # second one keeps data fresh.
        expected = {n for c in CHECKS for n in c.get("pipelines", [])}
        missing = sorted(expected - sched.SCHEDULED_PIPELINES)
        self.assertEqual(
            missing, [],
            f"the watchdog monitors these but nothing schedules them: {missing}",
        )

    def test_the_declaration_does_not_claim_pipelines_that_do_not_exist(self):
        # A set maintained by hand drifts in both directions. An entry here
        # that no source monitors is either a dead pipeline or a typo, and a
        # typo would make the check above pass for the wrong reason.
        expected = {n for c in CHECKS for n in c.get("pipelines", [])}
        extra = sorted(sched.SCHEDULED_PIPELINES - expected)
        self.assertEqual(extra, [], f"declared but monitored by no source: {extra}")


class TestTheToleranceIsReachable(unittest.TestCase):
    """F-0091 / F-0089's second instance, predicted by A-0015."""

    # D-0077 retargeted these to the period end. The 2026-07-13 release carried
    # calendar 2025, which ENDED 2025-12-31 - 194 days earlier, not 558. The
    # 1 January date is the year's label, not the age of the observation, and
    # this is the series where that convention did the most damage: a tolerance
    # of 960 days is wide enough to be nearly decorative.
    BEST_CASE_AGE = 194   # calendar 2025, available 2026-07-13
    WORST_CASE_AGE = 559  # still newest when the next annual release lands

    def _src(self):
        src = next((s for s in CHECKS if s["key"] == "money_supply"), None)
        self.assertIsNotNone(src)
        return src

    def test_a_current_source_can_report_current(self):
        # At 420 this could never be green: the newest row the World Bank has
        # ever offered is older than that on the day it appears. So it reported
        # stale every night whether or not anything was wrong - and the real
        # failure, that nothing fetched or scheduled it, looked identical.
        self.assertGreaterEqual(self._src()["max_age_days"], self.WORST_CASE_AGE)

    def test_it_still_catches_a_wholly_missed_annual_release(self):
        # A skipped annual release puts the newest observation past ~925 days
        # from its coverage end.
        self.assertLess(self._src()["max_age_days"], self.WORST_CASE_AGE + 366)

    def test_the_note_no_longer_says_MANUAL(self):
        # It is not manual any more. A note describing a fixed condition is
        # what D-0074 caught in the CDS entry.
        self.assertNotIn("MANUAL", self._src()["note"])


class TestTheRouteExists(unittest.TestCase):
    def test_a_post_route_can_trigger_the_fetch(self):
        paths = [
            r.path for r in router.routes
            if isinstance(r, APIRoute) and "POST" in r.methods
        ]
        self.assertIn("/api/fetch/money-supply", paths)


if __name__ == "__main__":
    unittest.main()
