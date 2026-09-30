"""F-0098 — the ADMIN and ABOUT surfaces must describe the system that exists.

ADMIN listed **four** actions against eleven scheduled jobs and ten POST
triggers. It described TIC as "45 countries" when SLT Table 5 names twenty,
filed Gold Reserves under a heading of "Manual (CSV import)" with instructions
to re-download quarterly from gold.org months after `D-0076` automated it from
IMF IRFCL, and omitted CDS, Treasury Direct, Gold Price, Gold Reserve Changes,
Broad Money, IMF Gold, the composite snapshot and the freshness watchdog.

These are operator surfaces. A missing trigger is a job an operator cannot run;
a wrong schedule is one they will not know has stopped. Unlike a data tab,
nothing here is self-evidently wrong on screen.

**Why the guard is in Python.** The drift is between `api/routes.py` and
`pipelines/scheduler.py` on one side and two JavaScript files on the other. A
vitest case cannot read the Python; this can read both. `F-0096` moved the ABOUT
catalogue out of its component for exactly this reason and `F-0098` does the same
for ADMIN.
"""
import re
import unittest
from pathlib import Path

from fastapi.routing import APIRoute

from api.routes import router
from pipelines import scheduler as sched

ROOT = Path(__file__).resolve().parents[1]
ADMIN_JS = ROOT / "ui" / "src" / "lib" / "adminActions.js"
ABOUT_JS = ROOT / "ui" / "src" / "lib" / "dataSources.js"


def admin_text():
    return ADMIN_JS.read_text(encoding="utf-8")


def about_text():
    return ABOUT_JS.read_text(encoding="utf-8")


def strip_js_comments(text: str) -> str:
    """JS source with comments removed.

    Every "this surface must not say X" assertion in this file needs it,
    because the files DOCUMENT the wrong claims they replaced - "45 countries",
    "re-download", "mfhhis01.txt" all appear in the header comment explaining
    why they are wrong. A whole-file substring search matches that explanation
    and fails the test on its own documentation.

    Fifth time today I wrote an assertion that matched my own comment (F-0087,
    F-0095 and three earlier). One helper rather than remembering five times.
    """
    without_block = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return "\n".join(
        ln for ln in without_block.splitlines()
        if not ln.lstrip().startswith("//")
    )


def post_paths():
    return {
        r.path
        for r in router.routes
        if isinstance(r, APIRoute) and "POST" in r.methods
    }


def registered_job_ids():
    """Job ids as `scheduler.py` registers them."""
    return set(re.findall(r'id="([a-z_]+)"', Path(
        ROOT / "pipelines" / "scheduler.py").read_text(encoding="utf-8")))


class TestEveryTriggerIsOffered(unittest.TestCase):
    def test_every_post_route_appears_in_the_admin_catalogue(self):
        # A POST route absent from ADMIN is a capability an operator has no way
        # to reach. Six were missing.
        body = admin_text()
        missing = sorted(
            p for p in post_paths()
            if p.replace("/api", "", 1) not in body
        )
        self.assertEqual(missing, [], f"POST routes not offered in ADMIN: {missing}")

    def test_the_catalogue_offers_nothing_that_does_not_exist(self):
        # Drift runs both ways. A button calling a route that was renamed or
        # removed fails at the moment an operator most needs it to work.
        offered = set(re.findall(r'endpoint: "([^"]+)"', admin_text()))
        real = {p.replace("/api", "", 1) for p in post_paths()} | {
            r.path.replace("/api", "", 1)
            for r in router.routes
            if isinstance(r, APIRoute) and "GET" in r.methods
        }
        phantom = sorted(offered - real)
        self.assertEqual(phantom, [], f"ADMIN offers routes that do not exist: {phantom}")

    def test_the_methods_match_the_routes(self):
        # A GET rendered as a POST button silently 405s. /stress-score and
        # /diagnostics/data-age are both GETs among a list of POSTs.
        pairs = re.findall(
            r'endpoint: "([^"]+)", method: "(GET|POST)"', admin_text()
        )
        self.assertTrue(pairs, "no endpoint/method pairs found")
        for path, method in pairs:
            full = "/api" + path
            actual = {
                m
                for r in router.routes
                if isinstance(r, APIRoute) and r.path == full
                for m in r.methods
            }
            self.assertIn(method, actual, f"{full} is not a {method}")


class TestEveryScheduledJobIsListed(unittest.TestCase):
    def test_all_registered_job_ids_appear(self):
        body = admin_text()
        # Startup one-shots are not schedule entries an operator reads as a
        # cadence; each is covered by the cron job it duplicates.
        one_shots = {"startup_fetches", "startup_cds_fetch"}
        missing = sorted(
            j for j in registered_job_ids() - one_shots
            if f'id: "{j}"' not in body
        )
        self.assertEqual(missing, [], f"scheduled jobs not listed in ADMIN: {missing}")

    def test_the_catalogue_lists_no_job_that_is_not_registered(self):
        listed = set(re.findall(r'id: "([a-z_]+)"', admin_text()))
        phantom = sorted(listed - registered_job_ids())
        self.assertEqual(phantom, [], f"ADMIN lists unregistered jobs: {phantom}")

    def test_every_job_states_a_schedule_and_a_pipeline_name(self):
        # The pipeline name is what appears in the PIPELINE LOG below, so
        # without it an operator cannot connect a job to its last run.
        jobs = re.findall(
            r'\{ id: "[a-z_]+", name: "[^"]+", schedule: "([^"]+)",\s*\n\s*pipeline: "([^"]+)"',
            admin_text(),
        )
        self.assertEqual(
            len(jobs), len(re.findall(r'\{ id: "[a-z_]+"', admin_text())),
            "a job is missing its schedule or pipeline name",
        )
        for schedule, pipeline in jobs:
            self.assertTrue(schedule.strip(), pipeline)
            self.assertTrue(pipeline.strip(), schedule)

    def test_the_pipeline_names_are_the_ones_the_scheduler_owns(self):
        # These must match UpdateLog.pipeline_name, which is what the log table
        # shows. SCHEDULED_PIPELINES is the scheduler's own declaration (F-0091).
        listed = set(re.findall(r'pipeline: "([A-Za-z_]+)"', admin_text()))
        known = sched.SCHEDULED_PIPELINES | {
            "Stress_Score", "Composite_Snapshot", "Freshness",
        }
        unknown = sorted(listed - known)
        self.assertEqual(unknown, [], f"pipeline names ADMIN invented: {unknown}")


class TestNeitherSurfaceRepeatsAKnownFalsehood(unittest.TestCase):
    """The specific claims that were wrong, held shut by name."""

    def test_neither_says_TIC_covers_45_countries(self):
        # Table 5 names twenty and folds the rest into "All Other". The 45 was
        # the count of countries with any TIC row at all, most of them years old
        # — and reading absence as zero is F-0097.
        for name, body in (("ADMIN", admin_text()), ("ABOUT", about_text())):
            self.assertNotIn(
                "45 countries", strip_js_comments(body), f"{name} still claims 45"
            )

    def test_neither_calls_gold_reserves_a_manual_csv_download(self):
        for name, body in (("ADMIN", admin_text()), ("ABOUT", about_text())):
            lowered = strip_js_comments(body).lower()
            self.assertNotIn("re-download", lowered, f"{name} still says re-download")
            self.assertNotIn("manual (csv", lowered, f"{name} still has a manual group")

    def test_neither_points_an_operator_at_the_frozen_TIC_file(self):
        # F-0088. mfhhis01.txt is served, returns 200, and ends December 2025.
        # It may be NAMED as the thing not to use; it must not be given as the
        # source.
        for name, body in (("ADMIN", admin_text()), ("ABOUT", about_text())):
            for line in strip_js_comments(body).splitlines():
                if "mfhhis01" in line:
                    self.assertIn(
                        "NOT", line,
                        f"{name} names mfhhis01 without marking it as wrong",
                    )

    def test_admin_names_the_composite_snapshot_consequence(self):
        # F-0090: a manual fetch leaves the stored score behind until 04:45. An
        # operator who does not know that will read a stale score as current.
        self.assertIn("F-0090", admin_text())


if __name__ == "__main__":
    unittest.main()
