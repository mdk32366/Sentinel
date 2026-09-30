"""F-0082: a response model must declare everything the scorer produces.

FastAPI's `response_model` is a filter, not a validator of completeness. Any
key the model does not declare is **removed from the response**, silently and
with no error anywhere.

`CompositeCountry` declared 33 fields. `compute_composite_stress` produced 44.
The eleven it dropped included the entire Sovereign CDS dimension and
`active_signals` — so the COMPOSITE table's CDS column, the CDS tab's "CDS
Share" column and the country panel's stress breakdown all read a field the
API had already removed, and all three rendered a dash. The Activity column
was the widest on the table and almost always empty for the same reason.

**Why the frontend tests did not catch it.** They stub `fetch` and supply the
shape themselves. A stub written from the scorer's output proves the component
renders that shape; it proves nothing about whether the server sends it. The
stub was defining the contract instead of the server.

This check is static — it reads the scorer's `results.append({...})` keys and
compares them to the model's fields — so it needs no database and cannot be
satisfied by a stub.
"""
import re
import unittest
from pathlib import Path

from api.schemas import CompositeCountry

ROOT = Path(__file__).resolve().parents[1]
SCORER = ROOT / "pipelines" / "composite_stress.py"


def scorer_payload_keys():
    """The keys of the dict the scorer appends per country.

    Follows a `**helper(...)` spread into the helper's own return dict.
    `D-0083` added four fields that way, and this guard reported them as
    declared-but-never-produced — the guard being right about what it could see
    and wrong about the payload.

    Resolved by teaching it to follow the spread rather than by exempting the
    fields. An exemption list would let the next spread hide a field silently,
    and the point of this pair of tests is that the model and the scorer cannot
    drift apart.
    """
    source = SCORER.read_text(encoding="utf-8")
    start = source.index("        results.append({")
    end = source.index("\n        })", start)
    block = source[start:end]

    keys = {m.group(1) for m in re.finditer(r'^\s*"([a-z0-9_]+)":', block, re.M)}

    for helper in re.findall(r"\*\*([a-z_][a-z0-9_]*)\(", block):
        hstart = source.index(f"def {helper}(")
        # Bounded by the next top-level def.
        hend = source.find("\ndef ", hstart + 1)
        body = source[hstart: hend if hend != -1 else len(source)]
        keys |= {m.group(1) for m in re.finditer(r'^\s*"([a-z0-9_]+)":', body, re.M)}

    return keys


class TheModelDeclaresEverythingTheScorerProduces(unittest.TestCase):
    def test_no_field_is_silently_dropped(self):
        dropped = scorer_payload_keys() - set(CompositeCountry.model_fields)
        self.assertEqual(
            dropped, set(),
            "the response model drops these on the way out, with no error: "
            f"{sorted(dropped)}",
        )

    def test_the_cds_dimension_reaches_the_client(self):
        # Named explicitly because this is what the whole CDS surface depends
        # on, and because a bulk edit to the model would otherwise remove it
        # without anything in the test name saying what broke.
        for field in ("cds_5y", "cds_score", "cds_coverage", "cds_widening_pct"):
            with self.subTest(field=field):
                # assertTrue, not assertIn: assertIn dumps the entire
                # FieldInfo dict into the failure message, which buries the
                # one word that matters under two thousand characters.
                self.assertTrue(
                    field in CompositeCountry.model_fields,
                    f"CompositeCountry does not declare {field} - the API strips it",
                )

    def test_active_signals_reaches_the_client(self):
        # The Activity column's entire content.
        self.assertTrue(
            "active_signals" in CompositeCountry.model_fields,
            "CompositeCountry does not declare active_signals - the Activity "
            "column renders empty for every row",
        )

    def test_the_model_declares_nothing_the_scorer_never_sends(self):
        # The other direction. A declared field the scorer never produces is a
        # promise the API cannot keep - it renders as a default, which reads
        # as a real value rather than an absent one.
        produced = scorer_payload_keys()
        # Fields the scorer sets outside the append block, after tiering.
        SET_LATER = {"tier", "composite_score", "raw_score", "multiplier"}
        phantom = set(CompositeCountry.model_fields) - produced - SET_LATER
        self.assertEqual(
            phantom, set(),
            f"declared but never produced: {sorted(phantom)}",
        )


class TheScorerPayloadIsParseable(unittest.TestCase):
    """If this file stops finding the payload, the checks above go quiet."""

    def test_the_payload_block_was_found(self):
        keys = scorer_payload_keys()
        self.assertGreater(len(keys), 20, "the results.append block was not parsed")

    def test_it_contains_the_fields_we_know_are_there(self):
        keys = scorer_payload_keys()
        for known in ("country_iso", "tic_score", "gold_score", "cds_score"):
            with self.subTest(field=known):
                self.assertTrue(known in keys, f"{known} not parsed from the scorer payload")


if __name__ == "__main__":
    unittest.main()
