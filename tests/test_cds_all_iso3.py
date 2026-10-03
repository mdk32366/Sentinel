"""D-0091 / F-0106: `/cds/all` carries the ISO3 the country card is keyed by.

Every CDS row navigated to the country card with `country_iso`, which is the
CDS namespace token ("RUSSIA"), not ISO-3166. The card asked for
`/holdings/RUSSIA` and `/gold-reserves/RUSSIA`, got 404s, and titled itself
"RUSSIA" with no holdings or gold. `UNITED_STATES` never reached the USA
dashboard at all, because that branch is keyed on the literal "USA".

The fix is an ADDITIVE field, `country_iso3`, derived on the server from the
one map that already exists. `country_iso` is a documented contract and is
not renamed. These tests pin the four ways the fix could quietly undo itself:

1. the field is not declared, so `response_model` strips it (F-0079 / F-0082);
2. the inverse map stops being a 1:1 inverse of `CDS_NAME_BY_ISO`;
3. the captured production fixture drifts from the map;
4. the endpoint stops emitting it.

(4) follows the in-memory SQLite pattern of `tests/test_cds_coverage.py`
(`_session()` + `Metric` / `TimeSeries` rows), so it runs with no Postgres.
"""
import asyncio
import json
import unittest
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import List

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.routes import get_all_cds
from api.schemas import CdsAllItem
from database.models import Base, Metric, TimeSeries
from pipelines.cds_fetcher import CDS_SOURCE
from pipelines.composite_stress import CDS_NAME_BY_ISO, ISO_BY_CDS_NAME

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "api" / "production_payloads.json"
PAYLOADS = json.loads(FIXTURE.read_text(encoding="utf-8"))


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _seed_5y(db, token, name, value, day):
    metric = Metric(
        code=f"{token}_CDS_5Y",
        name=f"{name} 5Y CDS",
        category="sovereign_cds",
        unit="bps",
        source=CDS_SOURCE,
    )
    db.add(metric)
    db.flush()
    db.add(TimeSeries(metric_id=metric.id, country_id=None, date=day, value=Decimal(str(value))))


class TheFieldIsDeclared(unittest.TestCase):
    def test_country_iso3_is_a_declared_field(self):
        # An undeclared key is dropped by response_model without a word, which
        # is how F-0082 shipped. Declared or it does not exist.
        self.assertIn("country_iso3", CdsAllItem.model_fields)

    def test_the_token_field_is_not_renamed(self):
        # D-0091 is additive. country_iso stays the CDS token it documents.
        self.assertIn("country_iso", CdsAllItem.model_fields)
        self.assertTrue(CdsAllItem.model_fields["country_iso"].is_required())

    def test_it_is_optional(self):
        # A token the map does not know must not turn the endpoint into a 500.
        self.assertFalse(CdsAllItem.model_fields["country_iso3"].is_required())


class TheInverseIsExact(unittest.TestCase):
    def test_every_iso_round_trips(self):
        for iso, token in CDS_NAME_BY_ISO.items():
            with self.subTest(iso=iso):
                self.assertEqual(ISO_BY_CDS_NAME[token], iso)

    def test_no_token_repeats(self):
        # A repeated token would make the inverse lose an ISO silently: the
        # dict comprehension keeps the last one and nothing says so.
        tokens = list(CDS_NAME_BY_ISO.values())
        self.assertEqual(len(tokens), len(set(tokens)))
        self.assertEqual(len(ISO_BY_CDS_NAME), len(CDS_NAME_BY_ISO))

    def test_the_inverse_is_iso_shaped(self):
        for iso in ISO_BY_CDS_NAME.values():
            with self.subTest(iso=iso):
                self.assertRegex(iso, r"^[A-Z]{3}$")


class TheFixtureMatchesTheMap(unittest.TestCase):
    def test_every_cds_all_row_carries_the_mapped_iso3(self):
        rows = PAYLOADS["cds_all"]
        self.assertEqual(len(rows), 21, "fixture row count changed; re-check this guard")
        for row in rows:
            with self.subTest(token=row["country_iso"]):
                self.assertIn("country_iso3", row)
                self.assertEqual(row["country_iso3"], ISO_BY_CDS_NAME[row["country_iso"]])

    def test_the_two_cases_the_card_cares_about(self):
        by_token = {r["country_iso"]: r for r in PAYLOADS["cds_all"]}
        self.assertEqual(by_token["RUSSIA"]["country_iso3"], "RUS")
        # The USA dashboard branch is keyed on the literal "USA".
        self.assertEqual(by_token["UNITED_STATES"]["country_iso3"], "USA")


class TheEndpointEmitsIt(unittest.TestCase):
    def _rows(self):
        db = _session()
        try:
            day = datetime.utcnow() - timedelta(days=1)
            _seed_5y(db, "RUSSIA", "Russia", 210.0, day)
            _seed_5y(db, "UNITED_STATES", "United States", 45.0, day)
            # A token the map does not know: must come back null, not guessed.
            _seed_5y(db, "ATLANTIS", "Atlantis", 99.0, day)
            db.commit()
            return asyncio.run(get_all_cds(db=db))
        finally:
            db.close()

    def test_get_all_cds_emits_country_iso3(self):
        by_token = {r["country_iso"]: r for r in self._rows()}
        self.assertEqual(by_token["RUSSIA"]["country_iso3"], "RUS")
        self.assertEqual(by_token["UNITED_STATES"]["country_iso3"], "USA")
        self.assertIsNone(by_token["ATLANTIS"]["country_iso3"])

    def test_it_survives_the_response_model(self):
        # The F-0082 shape end to end: what the route returns, served through
        # the model it is declared with, still carries the field.
        rows = self._rows()
        app = FastAPI()

        @app.get("/probe", response_model=List[CdsAllItem])
        def probe():
            return rows

        body = TestClient(app).get("/probe").json()
        by_token = {r["country_iso"]: r for r in body}
        self.assertEqual(by_token["RUSSIA"]["country_iso3"], "RUS")
        self.assertEqual(by_token["UNITED_STATES"]["country_iso3"], "USA")


if __name__ == "__main__":
    unittest.main()
