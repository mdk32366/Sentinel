"""ORDER-03 E — the response models actually enforce a contract.

Declaring `response_model` is only useful if a mismatch is a loud server-side
failure. Eighteen of twenty-seven endpoints assemble raw dicts, which means
`App.jsx` is the only specification of their shape and a renamed field empties
a tile in silence.

These cases run offline against a throwaway FastAPI app, so nothing depends on
the database having data.
"""
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from api.schemas import (
    GoldReserveItem,
    GoldReservesResponse,
    HoldingItem,
    HoldingsResponse,
)

GOOD_HOLDING = {
    "country_code": "JPN",
    "country_name": "Japan",
    "holdings_billions_usd": 1130.5,
    "percent_of_total": 14.2,
}
GOOD_ENVELOPE = {
    "date": "2025-12-01",
    "total_billions_usd": 7960.1,
    "holdings": [GOOD_HOLDING],
}


def app_returning(payload, model):
    app = FastAPI()

    @app.get("/probe", response_model=model)
    def probe():
        return payload

    return TestClient(app, raise_server_exceptions=False)


class TestContractIsEnforced(unittest.TestCase):
    def test_a_correct_payload_passes(self):
        """Clause (c): correct and incorrect must differ."""
        r = app_returning(GOOD_ENVELOPE, HoldingsResponse).get("/probe")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["holdings"][0]["country_code"], "JPN")

    def test_a_renamed_field_is_a_server_error_not_an_empty_tile(self):
        """E's PROOF. The UI reads holdings_billions_usd; renaming it must
        fail here rather than render a blank number."""
        renamed = dict(GOOD_HOLDING)
        renamed["holdings_bn"] = renamed.pop("holdings_billions_usd")
        payload = dict(GOOD_ENVELOPE, holdings=[renamed])
        r = app_returning(payload, HoldingsResponse).get("/probe")
        self.assertGreaterEqual(r.status_code, 500)

    def test_a_missing_envelope_field_is_a_server_error(self):
        payload = {k: v for k, v in GOOD_ENVELOPE.items() if k != "total_billions_usd"}
        r = app_returning(payload, HoldingsResponse).get("/probe")
        self.assertGreaterEqual(r.status_code, 500)

    def test_a_wrong_type_is_rejected(self):
        """A string where a float belongs is exactly what a silent upstream
        format change looks like."""
        bad = dict(GOOD_HOLDING, holdings_billions_usd="not a number")
        with self.assertRaises(ValidationError):
            HoldingItem(**bad)

    def test_gold_reserves_envelope_validates(self):
        item = {
            "country_code": "DEU",
            "country_name": "Germany",
            "as_of_date": "2026-01-01",
            "metric_tonnes": 3352.6,
            "percent_of_total": 9.1,
        }
        envelope = {
            "as_of": "2026-01-01",
            "total_metric_tonnes": 36700.0,
            "country_count": 39,
            "reserves": [item],
        }
        self.assertEqual(GoldReservesResponse(**envelope).country_count, 39)
        self.assertEqual(GoldReserveItem(**item).metric_tonnes, 3352.6)

    def test_extra_fields_do_not_break_the_contract(self):
        """Adding a field upstream must not take the endpoint down - only a
        REMOVED or renamed field should. Otherwise the contract is a tripwire
        on ordinary additive change."""
        extended = dict(GOOD_HOLDING, new_field_added_later=1)
        payload = dict(GOOD_ENVELOPE, holdings=[extended])
        r = app_returning(payload, HoldingsResponse).get("/probe")
        self.assertEqual(r.status_code, 200)


if __name__ == "__main__":
    unittest.main()
