"""ORDER-03 D4 — the persisted composite score must equal a fresh recompute.

Persisting creates a SECOND producer of the same number, which is the shape of
`D-0022` and gets the same treatment: a contract test, or the design does not
ship. A stale score served fast is worse than a slow correct one - it is the
plausible-artifact failure of Principle 11 with a performance justification
attached.

Offline. The scorer is stubbed with a fixed result, so what is under test is the
round trip - compute, serialise, store, read back, serve - rather than the
scoring logic, which has its own inputs and is not what persistence can break.

Equality on REAL data was measured separately on 2026-09-28: 29 countries,
0 tier or score disagreements, full payload identical. That is recorded in
testplan.md; it is a measurement at one moment and this test is what keeps the
property from regressing.
"""
import json
import unittest
from unittest import mock

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.models import Base, CompositeSnapshot
from pipelines import composite_stress

SCORED = {
    "crisis": [{"country_iso": "TUR", "composite_score": 168.0, "gold_score": 24}],
    "stressed": [{"country_iso": "RUS", "composite_score": 139.7, "gold_score": 9.9}],
    "elevated": [],
    "watch": [{"country_iso": "JPN", "composite_score": 21.0}],
    "summary": {"total": 3},
    "as_of": "2026-09-28",
}
TIERS = ("crisis", "stressed", "elevated", "watch")


def flatten(payload):
    return {
        c["country_iso"]: (tier, c.get("composite_score"))
        for tier in TIERS
        for c in payload.get(tier, [])
    }


class TestCompositeSnapshot(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.addCleanup(self.db.close)

    def _persist(self, result=SCORED):
        with mock.patch.object(composite_stress, "compute_composite_stress",
                               return_value=result):
            return composite_stress.persist_composite_snapshot(self.db)

    def test_persisted_equals_a_fresh_recompute(self):
        """D4. Unchanged inputs must give an unchanged answer."""
        self._persist()
        stored = json.loads(composite_stress.latest_composite_snapshot(self.db).payload)
        self.assertEqual(flatten(stored), flatten(SCORED))

    def test_the_whole_payload_survives_the_round_trip(self):
        """Not just the tiers - a dropped summary block would be invisible."""
        self._persist()
        stored = json.loads(composite_stress.latest_composite_snapshot(self.db).payload)
        self.assertEqual(stored, json.loads(json.dumps(SCORED, default=str)))

    def test_a_changed_score_is_detected(self):
        """Clause (c). A comparison that cannot fail proves nothing."""
        self._persist()
        stored = json.loads(composite_stress.latest_composite_snapshot(self.db).payload)
        tampered = json.loads(json.dumps(SCORED))
        tampered["crisis"][0]["composite_score"] = 999.0
        self.assertNotEqual(flatten(stored), flatten(tampered))

    def test_country_count_matches_the_payload(self):
        result = self._persist()
        self.assertEqual(result["countries"], len(flatten(SCORED)))
        self.assertEqual(
            composite_stress.latest_composite_snapshot(self.db).country_count,
            len(flatten(SCORED)),
        )

    def test_latest_is_the_newest_not_merely_the_last_written(self):
        self._persist()
        second = dict(SCORED, summary={"total": 99})
        self._persist(second)
        stored = json.loads(composite_stress.latest_composite_snapshot(self.db).payload)
        self.assertEqual(stored["summary"]["total"], 99)
        self.assertEqual(self.db.query(CompositeSnapshot).count(), 2)

    def test_no_snapshot_yet_returns_none_rather_than_an_empty_result(self):
        """The endpoint falls through to computing when this is None. Returning
        an empty payload here would serve a blank tab and call it success."""
        self.assertIsNone(composite_stress.latest_composite_snapshot(self.db))

    def test_a_failed_scoring_run_writes_no_snapshot(self):
        """A failure must not leave a half-result to be served as current."""
        with mock.patch.object(composite_stress, "compute_composite_stress",
                               return_value={"error": "No TIC data loaded"}):
            with self.assertRaises(RuntimeError):
                composite_stress.persist_composite_snapshot(self.db)
        self.assertEqual(self.db.query(CompositeSnapshot).count(), 0)
        self.assertIsNone(composite_stress.latest_composite_snapshot(self.db))


if __name__ == "__main__":
    unittest.main()
