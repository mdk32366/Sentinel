"""Sentinel D-0113: the country cards' FB freshness limits are the watchdog's.

The card judges a leg stale with FB_MAX_AGE_DAYS in ui/src/lib/constants.js;
that table must equal max_age_days of foreign_bonds_{de,gb,jp,fr} in
pipelines/freshness_watchdog.py, so the card and the Foreign Bonds tab agree.
"""
import re
import unittest
from pathlib import Path

from pipelines import freshness_watchdog

CONSTANTS = Path(__file__).resolve().parents[1] / "ui" / "src" / "lib" / "constants.js"


class CardFreshnessMirrorsTheWatchdog(unittest.TestCase):
    def test_limits_match(self):
        m = re.search(r"export const FB_MAX_AGE_DAYS = \{([^}]*)\}", CONSTANTS.read_text(encoding="utf-8"))
        self.assertIsNotNone(m, "FB_MAX_AGE_DAYS not found in constants.js")
        ui = {k: int(v) for k, v in re.findall(r"([A-Z]{2}):\s*(\d+)", m.group(1))}
        watchdog = {c["key"][-2:].upper(): c["max_age_days"]
                    for c in freshness_watchdog.CHECKS if c["key"].startswith("foreign_bonds_")}
        self.assertEqual(ui, watchdog)
        # Sentinel D-0115 (T-0118): batch 2a countries and the EA benchmark.
        self.assertEqual(set(ui), {"DE", "GB", "JP", "FR", "CA", "SE", "AU", "NO", "ES", "EA"})
