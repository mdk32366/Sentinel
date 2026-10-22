"""Sentinel D-0113 hard invariant: the country-card change is display-only.

Both scorers run on a fixed offline fixture (tests/composite_golden_fixture.py,
which includes FB_ daily bond rows) with the clock frozen, and their output must
equal the golden captured from master 0680d4b byte for byte. Regenerate only
under a decision that changes scoring: `python tests/test_d0113_scorer_golden.py --write`.
"""
import json
import sys
import unittest
from datetime import datetime as _dt
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from composite_golden_fixture import build  # noqa: E402
from pipelines import composite_stress, stress_score_v2  # noqa: E402

GOLDEN = Path(__file__).resolve().parent / "fixtures" / "d0113_scorer_golden.json"


class _Frozen(_dt):
    @classmethod
    def utcnow(cls):
        return cls(2026, 10, 22, 12, 0, 0)

    @classmethod
    def now(cls, tz=None):
        return cls(2026, 10, 22, 12, 0, 0)


def payload():
    with mock.patch.object(composite_stress, "datetime", _Frozen), \
         mock.patch.object(stress_score_v2, "datetime", _Frozen):
        out = {
            "composite": composite_stress.compute_composite_stress(build()),
            "v2": stress_score_v2.calculate_stress_score_v2(build()),
        }
    return json.dumps(out, default=str, sort_keys=True, indent=1) + "\n"


class ScorerOutputIsByteIdenticalToMaster(unittest.TestCase):
    def test_the_fixture_reaches_real_scoring(self):
        data = json.loads(payload())
        self.assertNotIn("error", data["composite"])
        self.assertTrue(data["composite"]["summary"]["countries_with_spread_data"] > 0)

    def test_output_equals_the_master_golden(self):
        self.assertEqual(payload(), GOLDEN.read_text(encoding="utf-8"))


if __name__ == "__main__" and "--write" in sys.argv:
    GOLDEN.write_text(payload(), encoding="utf-8")
