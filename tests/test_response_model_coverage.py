"""F-0101 — every response model must declare what its producer sends.

`F-0082` established the rule for `CompositeCountry`: FastAPI's `response_model`
is a **filter**, not a validator of completeness, so any key the model does not
declare is removed from the response silently and with no error anywhere.

A contract test was written for that one model. `F-0097` then added `tic_state`
and `tic_last_reported_bn` to **two** producers - `composite_stress.py` and
`gold_fetcher.py` - declared them on `CompositeCountry` only, and shipped. The
CROSS-ASSET tab's "n/r" rendering, written in the same change, **never once
appeared**: the field it reads was deleted between the scorer and the browser.

Nothing caught it. The frontend test supplied the field itself in a stub, the
backend test checked the other model, and the tab simply rendered a dash. It was
found by reading the live payload.

This file generalises the guard: for every producer/model pair, the model must
declare what the producer sends.
"""
import inspect
import re
import unittest
from pathlib import Path

from api import schemas

ROOT = Path(__file__).resolve().parents[1]


def dict_keys_in(source: str, anchor: str) -> set:
    """Keys of the dict literal appended at `anchor`."""
    keys = set()
    for m in re.finditer(re.escape(anchor), source):
        start = m.start()
        depth, i = 0, source.index("{", start)
        j = i
        while j < len(source):
            if source[j] == "{":
                depth += 1
            elif source[j] == "}":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        keys |= {k.group(1) for k in re.finditer(r'"([a-z0-9_]+)":', source[i:j])}
    return keys


class TestCrossAssetItem(unittest.TestCase):
    """The model F-0097 forgot."""

    def setUp(self):
        from pipelines import gold_fetcher
        self.produced = dict_keys_in(
            inspect.getsource(gold_fetcher.compute_cross_asset_stress),
            "results.append(",
        )
        self.declared = set(schemas.CrossAssetItem.model_fields)

    def test_it_declares_the_tic_state_fields(self):
        # The specific regression. Without these the CROSS-ASSET tab cannot
        # distinguish a completed liquidation from a country that merely fell
        # below the reporting threshold - which is the whole of F-0097.
        for field in ("tic_state", "tic_last_reported_bn"):
            self.assertIn(field, self.declared, f"{field} would be stripped")

    def test_it_declares_everything_the_producer_sends(self):
        missing = sorted(self.produced - self.declared)
        self.assertEqual(
            missing, [],
            f"gold_fetcher sends these and CrossAssetItem drops them: {missing}",
        )

    def test_the_producer_actually_sends_them(self):
        # The other direction: a declared field nothing produces renders as its
        # default, which reads as a real value rather than an absent one.
        for field in ("tic_state", "tic_last_reported_bn"):
            self.assertIn(field, self.produced, f"{field} is declared but unsent")


class TestHoldingsResponse(unittest.TestCase):
    """D-0085's fields, held shut the same way."""

    def setUp(self):
        from fastapi.routing import APIRoute

        from api.routes import router
        route = next(
            r for r in router.routes
            if isinstance(r, APIRoute) and r.path == "/api/holdings"
        )
        self.body = inspect.getsource(route.endpoint)

    def test_the_response_declares_what_the_endpoint_returns(self):
        returned = dict_keys_in(self.body, "return {")
        declared = set(schemas.HoldingsResponse.model_fields)
        missing = sorted(returned - declared)
        self.assertEqual(missing, [], f"stripped from /api/holdings: {missing}")

    def test_each_row_declares_what_the_endpoint_builds(self):
        # The row dicts are built in a comprehension, not a `return {`.
        row_keys = {
            m.group(1) for m in re.finditer(r'"([a-z0-9_]+)": ', self.body)
        }
        declared = set(schemas.HoldingItem.model_fields)
        for field in ("country_code", "holdings_billions_usd",
                      "percent_of_total", "long_term_only"):
            self.assertIn(field, row_keys, f"{field} is not built")
            self.assertIn(field, declared, f"{field} would be stripped")


class TestTheRuleIsStatedWhereItCanBeSeen(unittest.TestCase):
    def test_the_filter_behaviour_is_documented_on_the_schemas(self):
        # Three separate changes have now been bitten by this (F-0082, F-0097,
        # F-0101). The next person to add a field reads schemas.py, so the
        # warning belongs there rather than only in the register.
        text = (ROOT / "api" / "schemas.py").read_text(encoding="utf-8")
        self.assertIn("filter", text.lower())
        self.assertIn("F-0079", text)


if __name__ == "__main__":
    unittest.main()
