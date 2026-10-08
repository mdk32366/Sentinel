"""F-0113 - CROSS-ASSET could not show the countries it calls EXITED.

`compute_cross_asset_stress` returns every exited country holding 50t or more
of gold. GET /holdings/cross-asset-stress then split them into three lists -
cross-asset, Treasury-only and gold-only - and an exited country is never
`selling_treasuries`, so:

  exited, not selling gold           -> in no list at all: dropped
  exited, selling gold, spot flat    -> gold-only
  exited, selling gold, spot rising  -> cross-asset (divergence)

The "Exited Position" tile added up the cross-asset and Treasury-only lists,
so it counted only the third kind; the EXITED view showed the gold-only list,
which is neither exited countries nor all of them. The response now carries
the exited countries themselves, and a count of them.
"""
import unittest
from unittest import mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from database.connection import get_db


def row(iso, *, exited=False, selling_t=False, selling_g=False, divergence=False, cross=False):
    return {
        "country_iso": iso, "country_name": iso, "region": None,
        "tic_holdings_bn": 0.0 if exited else 50.0, "tic_mom_pct": None,
        "tic_consecutive_months": 0, "no_tic_holdings": exited,
        "tic_state": "exited" if exited else "reported", "tic_last_reported_bn": None,
        "gold_tonnes": 100.0, "gold_mom_pct": None, "gold_consecutive_months": 0,
        "treseg_signal": "NO_DATA", "treseg_trend_pct": None, "treseg_latest_bn": None,
        "spot_gold_price": 4000.0, "spot_gold_3m_pct": 1.0, "spot_gold_rising": divergence,
        "selling_treasuries": selling_t, "selling_gold": selling_g,
        "cross_asset_stress": cross, "divergence_signal": divergence,
        "signal_tier": "EXITED" if exited else "T_ONLY", "score_before_multiplier": 50.0,
        "multiplier": 1.0, "stress_score": 50.0, "alert": exited,
        "tic_as_of": "2026-07", "gold_as_of": "2026-07",
    }


ROWS = [
    row("AAA", exited=True),                                   # holds gold, not selling
    row("BBB", exited=True, selling_g=True),                   # selling gold, spot flat
    row("CCC", exited=True, selling_g=True, divergence=True),  # selling into a rising spot
    row("DDD", selling_t=True),                                # an ordinary T-only seller
]


class TheExitedCountriesReachTheResponse(unittest.TestCase):
    def setUp(self):
        from api.routes import router

        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_db] = lambda: None
        with mock.patch("api.routes.compute_cross_asset_stress", return_value=ROWS):
            self.body = TestClient(app).get("/api/holdings/cross-asset-stress").json()

    def test_every_exited_country_is_listed(self):
        exited = sorted(r["country_iso"] for r in self.body.get("exited", []))
        self.assertEqual(exited, ["AAA", "BBB", "CCC"])

    def test_the_count_is_of_exited_countries(self):
        self.assertEqual(self.body["summary"].get("exited"), 3)

    def test_a_non_exited_country_is_not_listed(self):
        self.assertNotIn("DDD", [r["country_iso"] for r in self.body.get("exited", [])])


if __name__ == "__main__":
    unittest.main()
