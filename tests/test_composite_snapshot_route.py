"""F-0090 — a manual data refresh could not refresh the score that reads it.

`POST /fetch/treasury-holdings` has always existed and invites a manual data
refresh. `GET /stress/composite` serves a *stored* snapshot (`D-0042`), and
only the 04:45 UTC job wrote one. So a manual fetch moved the data and left
the score behind, with nothing able to catch it up.

Observed for real: minutes after the `F-0088` TIC fix landed, HOLDINGS served
`2026-07` while COMPOSITE served `2025-12`.
"""
import unittest

from fastapi.routing import APIRoute

from api.routes import router


def _route(path: str, method: str):
    for r in router.routes:
        if isinstance(r, APIRoute) and r.path == path and method in r.methods:
            return r
    return None


class TestTheSnapshotCanBeRefreshed(unittest.TestCase):
    def test_a_post_route_exists_to_store_a_fresh_snapshot(self):
        self.assertIsNotNone(
            _route("/api/snapshot/composite", "POST"),
            "there is no way to refresh the stored composite between nightly "
            "runs, so a manual data fetch leaves the score behind",
        )

    def test_it_calls_the_same_function_the_scheduler_calls(self):
        # Not a second scoring path. F-0047 is the standing example: two jobs
        # that looked equivalent ran different scorers, and the endpoint served
        # the wrong one's output.
        import inspect

        from pipelines import composite_stress, scheduler

        route = _route("/api/snapshot/composite", "POST")
        body = inspect.getsource(route.endpoint)
        self.assertIn("persist_composite_snapshot", body)
        self.assertIn(
            "persist_composite_snapshot",
            inspect.getsource(scheduler.scheduled_composite_snapshot),
        )
        self.assertTrue(hasattr(composite_stress, "persist_composite_snapshot"))

    def test_the_read_path_still_serves_the_stored_snapshot_by_default(self):
        # D-0042 is the reason the gap existed; closing the gap must not close
        # it by making every tab click recompute ~230 queries.
        import inspect

        route = _route("/api/stress/composite", "GET")
        self.assertIsNotNone(route)
        sig = inspect.signature(route.endpoint)
        self.assertIn("recompute", sig.parameters)
        self.assertIs(
            sig.parameters["recompute"].default.default, False,
            "recompute must default to False or every reader pays for a "
            "full rescore",
        )

    def test_the_refresh_is_a_post_not_a_get(self):
        # It writes. A GET that writes is the shape that gets called by a
        # link prefetch and a crawler.
        self.assertIsNone(_route("/api/snapshot/composite", "GET"))


if __name__ == "__main__":
    unittest.main()
