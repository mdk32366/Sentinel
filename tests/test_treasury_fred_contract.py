"""ORDER-01 B1 — contract test for the two producers of the `DGS*` namespace.

`treasury_direct` and `fred_fetcher` both write the same metric codes. Under
`D-0022` that is deliberate, and it is valid ONLY while the two sources agree.
`A-0001` is the assumption; this is its test.

Runs offline against fixtures captured from both live sources on 2026-09-28
(`tests/fixtures/treasury/`). Principle 5: a test that needs the real world is a
different kind of check. The live equivalent is `tools/check_curve_contract.py`,
which is a script, not part of the gate.

Fixtures go stale, and a stale fixture proving a live property is its own trap.
`test_fixtures_are_not_silently_ancient` fails when they age past a year so the
question is re-asked rather than assumed answered.
"""
import datetime
import json
import unittest
from decimal import Decimal
from pathlib import Path

from pipelines.treasury_direct import parse_curve_csv

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "treasury"
TREASURY_CSV = FIXTURES / "daily_treasury_rates_2026.csv"
FRED_JSON = FIXTURES / "fred_dgs_2026.json"

# D-0022's reversal condition. If the sources disagree by more than this, the
# same-namespace write is invalid and must become a separate UST_* namespace.
TOLERANCE = Decimal("0.01")

# Below this the comparison is not evidence, whatever it reports.
MINIMUM_OVERLAPPING_DAYS = 20


def _load():
    treasury = {
        row["date"].date(): row["rates"]
        for row in parse_curve_csv(TREASURY_CSV.read_text(encoding="utf-8"))
    }
    raw = json.loads(FRED_JSON.read_text(encoding="utf-8"))
    fred = {}
    for code, observations in raw.items():
        for day, value in observations.items():
            fred.setdefault(
                datetime.date.fromisoformat(day), {}
            )[code] = Decimal(value)
    return treasury, fred


class TestTreasuryFredContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.treasury, cls.fred = _load()
        cls.overlap = sorted(set(cls.treasury) & set(cls.fred))

    def test_sample_is_large_enough_to_be_evidence(self):
        """Carry the sample size with the claim (Principle 8)."""
        self.assertGreaterEqual(
            len(self.overlap),
            MINIMUM_OVERLAPPING_DAYS,
            f"only {len(self.overlap)} overlapping business days; "
            f"{MINIMUM_OVERLAPPING_DAYS} required before agreement means anything",
        )

    def test_sources_agree_on_every_shared_date_and_tenor(self):
        """A-0001. Failure invalidates D-0022 and forces the UST_* namespace."""
        compared = 0
        disagreements = []
        for day in self.overlap:
            for code, treasury_value in self.treasury[day].items():
                fred_value = self.fred[day].get(code)
                if fred_value is None:
                    continue
                compared += 1
                if abs(treasury_value - fred_value) > TOLERANCE:
                    disagreements.append(
                        f"{day} {code}: treasury={treasury_value} "
                        f"fred={fred_value} diff={abs(treasury_value - fred_value)}"
                    )

        self.assertGreater(compared, 0, "no comparable pairs - fixtures broken")
        self.assertEqual(
            disagreements,
            [],
            f"{len(disagreements)} of {compared} pairs disagree by more than "
            f"{TOLERANCE}. D-0022's same-namespace write is invalid; reverse to "
            f"UST_* before any further write.",
        )

    def test_the_comparison_can_actually_fail(self):
        """Clause (c): the fixture must distinguish correct from incorrect.

        Without this, a comparison that silently comes up empty would pass and
        prove nothing - which is how a test ends up asserting that two sources
        agree about no values at all.
        """
        corrupted = {
            day: dict(rates) for day, rates in self.treasury.items()
        }
        day = self.overlap[0]
        # Must be a tenor BOTH sources carry. Treasury publishes DGS1MO, DGS3MO,
        # DGS1, DGS3, DGS20 and others that the FRED side does not, and
        # corrupting one of those is skipped by the comparison - which is how
        # this test failed on its first run and why it is worth having.
        code = next(c for c in corrupted[day] if c in self.fred[day])
        corrupted[day][code] = corrupted[day][code] + Decimal("5.00")

        diffs = [
            abs(corrupted[d][c] - self.fred[d][c])
            for d in self.overlap
            for c in corrupted[d]
            if c in self.fred[d]
        ]
        self.assertTrue(
            any(diff > TOLERANCE for diff in diffs),
            "a 5pp corruption went undetected - the comparison is not wired up",
        )

    def test_seven_year_is_covered_by_the_contract(self):
        """DGS7 is the tenor this whole order exists to add."""
        with_seven = [d for d in self.overlap if "DGS7" in self.treasury[d]]
        self.assertGreaterEqual(len(with_seven), MINIMUM_OVERLAPPING_DAYS)
        self.assertTrue(
            any("DGS7" in self.fred[d] for d in with_seven),
            "FRED side carries no DGS7 - the contract does not cover it",
        )

    def test_fixtures_are_not_silently_ancient(self):
        """A fixture proving a live property must not quietly rot."""
        newest = max(self.overlap)
        age_days = (datetime.date.today() - newest).days
        self.assertLess(
            age_days,
            365,
            f"contract fixtures end {newest} ({age_days} days old). Recapture "
            f"them and re-run, rather than trusting a year-old agreement.",
        )


if __name__ == "__main__":
    unittest.main()
