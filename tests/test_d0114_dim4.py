"""Sentinel D-0114: composite dimension 4 reads the daily FB 10Y for
DEU/GBR/JPN/FRA, falls back to the monthly IRLTLT when the daily leg is stale,
and adds an own-history OAT-Bund percentile term for euro-area members with
both legs (today FRA). dim4 = max(level, spread). Every other country is
byte-identical to the pre-D-0114 scorer (baseline captured from master cb0f460).
"""
import json
import sys
import unittest
from datetime import datetime, datetime as _dt
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import d0114_fixture as fx  # noqa: E402
from pipelines import composite_stress as cs  # noqa: E402
from pipelines import freshness_watchdog  # noqa: E402

BASELINE = Path(__file__).resolve().parent / "fixtures" / "d0114_non_fb_baseline.json"
FB_ISOS = ("DEU", "GBR", "JPN", "FRA")


class _Frozen(_dt):
    @classmethod
    def utcnow(cls):
        return cls(2026, 10, 22, 12, 0, 0)

    @classmethod
    def now(cls, tz=None):
        return cls(2026, 10, 22, 12, 0, 0)


def rows(**kw):
    with mock.patch.object(cs, "datetime", _Frozen):
        out = cs.compute_composite_stress(fx.build(**kw))
    return {r["country_iso"]: r for t in ("crisis", "stressed", "elevated", "watch") for r in out[t]}


def non_fb_payload():
    by = rows()
    return json.dumps({k: v for k, v in sorted(by.items()) if k not in FB_ISOS},
                      default=str, sort_keys=True, indent=1) + "\n"


class Constants(unittest.TestCase):
    def test_codes_and_freshness_limits(self):
        self.assertEqual(cs.FB_DIM4_CODES, {"DEU": "FB_DE_10Y", "GBR": "FB_GB_10Y",
                                            "JPN": "FB_JP_10Y", "FRA": "FB_FR_10Y"})
        self.assertEqual(cs.FB_MAX_AGE_DAYS, {"DEU": 4, "GBR": 5, "JPN": 7, "FRA": 4})
        watchdog = {c["key"][-2:].upper(): c["max_age_days"]
                    for c in freshness_watchdog.CHECKS if c["key"].startswith("foreign_bonds_")}
        self.assertEqual({cs.FB_DIM4_CODES[i][3:5]: d for i, d in cs.FB_MAX_AGE_DAYS.items()}, watchdog)

    def test_sovereign_yield_codes_unchanged(self):
        self.assertEqual(len(cs.SOVEREIGN_YIELD_CODES), 14)
        self.assertEqual(cs.SOVEREIGN_YIELD_CODES["FRA"], "IRLTLT01FRM156N")

    def test_euro_area_is_explicit_and_benchmark_is_germany(self):
        self.assertIsInstance(cs.EURO_AREA, frozenset)
        self.assertIn("FRA", cs.EURO_AREA)
        self.assertNotIn("GBR", cs.EURO_AREA)
        self.assertEqual(cs.SPREAD_BENCHMARK, "DEU")


class Helpers(unittest.TestCase):
    def test_percentile_on_fixtures(self):
        self.assertEqual(cs.spread_percentile(50, [40, 50, 60, 70]), 50.0)
        self.assertEqual(cs.spread_percentile(85, [40, 60, 80, 85]), 100.0)
        self.assertEqual(cs.spread_percentile(30, [40, 60, 30, 80]), 25.0)
        self.assertIsNone(cs.spread_percentile(30, []))

    def test_same_date_only_no_forward_fill(self):
        a = [(datetime(2026, 10, 19), 3.3), (datetime(2026, 10, 20), 3.4), (datetime(2026, 10, 21), 3.5)]
        b = [(datetime(2026, 10, 19), 2.6), (datetime(2026, 10, 21), 2.7)]
        got = cs.same_date_spread_bp(a, b)
        self.assertEqual([d for d, _ in got], [datetime(2026, 10, 19), datetime(2026, 10, 21)])
        self.assertAlmostEqual(got[0][1], 70.0)
        self.assertAlmostEqual(got[1][1], 80.0)

    def test_max_behaviour(self):
        self.assertEqual(cs.combine_dim4(10, 4.0), 10)
        self.assertEqual(cs.combine_dim4(0, 17.5), 17.5)
        self.assertEqual(cs.combine_dim4(5, None), 5)


class Scoring(unittest.TestCase):
    def test_fra_spread_term_at_the_top_of_its_history(self):
        fra = rows()["FRA"]
        self.assertEqual(fra["dim4_source"], "FB_FR_10Y")
        # Level: 3.35% is under the US 10Y, but the FR-US gap widened >30bp
        # inside 120 days, so the unchanged D-0066 ladder gives its +5 kicker.
        self.assertEqual(fra["dim4_level_score"], 5)
        self.assertAlmostEqual(fra["dim4_spread_bp"], 85.0, places=1)
        self.assertEqual(fra["dim4_spread_pctile"], 100.0)
        self.assertEqual(fra["dim4_spread_score"], 20.0)
        self.assertEqual(fra["dim4_score"], 20.0)
        self.assertEqual(fra["dim4_flags"], [])

    def test_gbr_level_from_the_daily_10y(self):
        gbr = rows()["GBR"]
        self.assertEqual(gbr["dim4_source"], "FB_GB_10Y")
        self.assertAlmostEqual(gbr["spread_bps"], 128.0, places=1)
        self.assertEqual(gbr["dim4_level_score"], 10)
        self.assertIsNone(gbr["dim4_spread_score"])
        self.assertEqual(gbr["dim4_score"], 10)

    def test_stale_daily_falls_back_to_irltlt(self):
        jpn = rows()["JPN"]
        self.assertEqual(jpn["dim4_source"], "IRLTLT01JPM156N")
        self.assertIn("daily_stale", jpn["dim4_flags"])
        fra = rows(fr_last=datetime(2026, 10, 14))["FRA"]
        self.assertEqual(fra["dim4_source"], "IRLTLT01FRM156N")
        self.assertIsNone(fra["dim4_spread_score"])
        self.assertIn("spread_leg_stale", fra["dim4_flags"])

    def test_no_spread_term_for_germany_or_non_ez(self):
        # Germany scores 0 on the fixture and drops off the board, so its
        # dimension 4 is read directly.
        db = fx.build()
        with mock.patch.object(cs, "datetime", _Frozen):
            for iso in ("DEU", "GBR", "JPN"):
                with self.subTest(iso=iso):
                    d4 = cs.get_dim4_fb(db, iso, fx.US_10Y)
                    self.assertIsNone(d4["dim4_spread_score"])
                    self.assertIsNone(d4["dim4_spread_pctile"])
                    self.assertNotIn("spread_leg_missing", d4["dim4_flags"])

    def test_missing_leg_gives_level_only(self):
        fra = rows(drop=("FB_DE_10Y",))["FRA"]
        self.assertEqual(fra["dim4_source"], "FB_FR_10Y")
        self.assertIsNone(fra["dim4_spread_score"])
        self.assertEqual(fra["dim4_score"], fra["dim4_level_score"])
        self.assertIn("spread_leg_missing", fra["dim4_flags"])

    def test_dim4_is_in_the_raw_sum_for_fb_countries(self):
        fra = rows()["FRA"]
        parts = (fra["tic_score"] + fra["gold_score"] + fra["monetary_score"]
                 + fra["petro_score"] + fra["cds_score"] + fra["dim4_score"])
        self.assertAlmostEqual(fra["raw_score"], round(parts, 1))

    def test_non_fb_countries_byte_identical_to_master(self):
        self.assertEqual(non_fb_payload(), BASELINE.read_text(encoding="utf-8"))
        self.assertNotIn("dim4_score", rows()["ITA"])


if __name__ == "__main__" and "--write-baseline" in sys.argv:
    BASELINE.write_text(non_fb_payload(), encoding="utf-8")
