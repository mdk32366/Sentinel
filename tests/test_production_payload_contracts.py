"""F-0049 — the response models match what production actually returns.

`tests/test_response_contracts.py` proves the models *enforce* a contract.
This proves the contract is the *right* one, by validating every model against
payloads captured from the live application on 2026-09-28.

That distinction is the whole reason `F-0049` existed: the four endpoints here
were left unmodelled for a week because their nullable fields were null in
every local row, and a guessed `Optional[...]` that is wrong in production
turns a working endpoint into a 500. These fixtures are the populated sample
that made modelling them safe rather than speculative.

Fixtures go stale. `test_fixtures_carry_the_fields_the_models_call_optional`
checks that the captured data still exercises the nullable paths, so an
all-populated recapture cannot quietly turn this into a test of nothing.
"""
import json
import unittest
from pathlib import Path

from api.schemas import (
    CdsAllItem,
    CdsCountryResponse,
    CompositeStressResponse,
    CrossAssetStressResponse,
    GoldReservesResponse,
    HoldingsResponse,
)

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "api" / "production_payloads.json"
PAYLOADS = json.loads(FIXTURE.read_text(encoding="utf-8"))


class TestProductionPayloadsValidate(unittest.TestCase):
    def test_holdings(self):
        HoldingsResponse(**PAYLOADS["holdings"])

    def test_gold_reserves(self):
        GoldReservesResponse(**PAYLOADS["gold_reserves"])

    def test_cds_all_every_row(self):
        rows = PAYLOADS["cds_all"]
        self.assertGreater(len(rows), 0, "fixture has no CDS rows to validate")
        for row in rows:
            CdsAllItem(**row)

    def test_cds_country_with_data(self):
        """The populated shape: tenor objects rather than nulls."""
        parsed = CdsCountryResponse(**PAYLOADS["cds_country_with_data"])
        self.assertIsNotNone(parsed.five_year)
        self.assertGreater(parsed.five_year.value, 0)

    def test_cds_country_without_data(self):
        """The empty shape. A model that rejected this would turn 'no CDS for
        this country' into a 500."""
        parsed = CdsCountryResponse(**PAYLOADS["cds_country_no_data"])
        self.assertIsNone(parsed.five_year)
        self.assertIsNotNone(parsed.message)

    def test_cross_asset_stress(self):
        CrossAssetStressResponse(**PAYLOADS["cross_asset_stress"])

    def test_composite(self):
        parsed = CompositeStressResponse(**PAYLOADS["composite"])
        scored = len(parsed.crisis) + len(parsed.stressed) + len(parsed.elevated) + len(parsed.watch)
        self.assertGreater(scored, 0)


class TestFixturesStillExerciseTheHardCases(unittest.TestCase):
    """Clause (c) applied to fixtures rather than to code.

    Every `Optional` in these models exists because production had a null
    there. If a recapture happens to be fully populated, these models would
    still validate while proving nothing about the nullable paths - so the
    fixture is checked for the nulls it is supposed to carry.
    """

    def _composite_rows(self):
        p = PAYLOADS["composite"]
        return [c for t in ("crisis", "stressed", "elevated", "watch") for c in p.get(t, [])]

    def test_fixtures_carry_the_fields_the_models_call_optional(self):
        rows = self._composite_rows()
        for field in ("region", "oil_signal", "tic_mom_pct", "spread_bps",
                      "treseg_trend_pct", "m2_growth_pct"):
            self.assertTrue(
                any(row.get(field) is None for row in rows),
                f"no production row has {field} null - either the data changed "
                f"or this fixture no longer exercises the optional path",
            )

    def test_cds_fixture_carries_a_null_tenor(self):
        """cds_10y was null in 20 of 21 production rows."""
        self.assertTrue(
            any(row.get("cds_10y") is None for row in PAYLOADS["cds_all"]),
            "no CDS row has a null 10Y - the Optional is no longer exercised",
        )

    def test_int_where_float_is_declared_is_still_accepted(self):
        """score fields arrive as int on some rows and float on others."""
        rows = self._composite_rows()
        self.assertTrue(
            any(isinstance(row.get("tic_score"), int) for row in rows)
            or any(isinstance(row.get("gold_score"), int) for row in rows),
            "fixture no longer contains an integer score - the int/float "
            "widening this relies on is untested",
        )
        CompositeStressResponse(**PAYLOADS["composite"])


if __name__ == "__main__":
    unittest.main()
