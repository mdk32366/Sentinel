"""D-0114: why DEU gains +7.5 and GBR +5.0 from the same dim4 = 5.

Dimension 4 enters the raw sum once (composite_stress.py raw_score line); the
whole raw sum is then scaled by the pre-existing cross-asset multiplier
(1.5x when a country sells Treasuries AND gold; module docstring
"MULTIPLIERS"). Germany is cross-asset in prod, the UK is not. Pinned from the
read-only prod decomposition in tests/fixtures/d0114_deu_gbr_decomp.json.
"""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipelines import composite_stress as cs  # noqa: E402

FX = json.loads((Path(__file__).parent / "fixtures" / "d0114_deu_gbr_decomp.json").read_text(encoding="utf-8"))
DIMS = ("tic_score", "gold_score", "monetary_score", "petro_score", "cds_score", "dim4_score")


class D0114Decomposition(unittest.TestCase):
    def check(self, iso, side):
        p = FX[iso][side]
        raw, comp = cs.composite_from_parts({k: p[k] for k in DIMS}, p["multiplier"])
        self.assertEqual(round(raw, 1), p["raw_score"])
        self.assertEqual(round(comp, 1), p["composite_score"])
        return comp

    def test_deu_composite_pinned_at_67_3(self):
        self.assertEqual(round(self.check("DEU", "new"), 1), 67.3)
        self.check("DEU", "old")

    def test_gbr_composite(self):
        self.check("GBR", "old")
        self.assertEqual(round(self.check("GBR", "new"), 1), 10.0)

    def test_dim4_counted_once_then_multiplied(self):
        for iso, gain in (("DEU", 7.5), ("GBR", 5.0)):
            o, n = FX[iso]["old"], FX[iso]["new"]
            self.assertEqual(o["multiplier"], n["multiplier"])
            dd = n["dim4_score"] - o["dim4_score"]
            self.assertAlmostEqual(dd * n["multiplier"], gain)
            _, co = cs.composite_from_parts({k: o[k] for k in DIMS}, o["multiplier"])
            _, cn = cs.composite_from_parts({k: n[k] for k in DIMS}, n["multiplier"])
            self.assertAlmostEqual(cn - co, gain, places=6)


if __name__ == "__main__":
    unittest.main()
