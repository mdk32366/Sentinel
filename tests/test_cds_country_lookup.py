"""F-0078: /cds?country= must resolve the code it is actually sent.

CDS metrics encode the country by NAME — `TURKEY_CDS_5Y`. The endpoint built
`f"{country.upper()}_CDS_5Y"` and its own docstring said the parameter is a
"Country ISO code (e.g. TUR, MEX, BRA)". Those two facts cannot both hold:
`TUR_CDS_5Y` does not exist.

The country panel is the only caller, and it passes an ISO code. So the 5Y
CDS tile read **"No coverage" for every country, always** — a tile that was
never once correct, on the surface the owner asked to have CDS shown on.

The failure was silent because "no coverage" is a legitimate answer for most
countries: 21 of 105 are on the board at all. A wrong answer that is also a
plausible answer does not get reported.
"""
import unittest

from pipelines.composite_stress import CDS_NAME_BY_ISO
from pipelines.cds_fetcher import CDS_INSTRUMENTS


def metric_prefixes():
    """The country token every CDS metric code actually begins with."""
    return {
        tenors["5Y"]["code"].replace("_CDS_5Y", "")
        for tenors in CDS_INSTRUMENTS.values()
    }


class TheIsoMapCoversTheBoard(unittest.TestCase):
    def test_every_mapped_token_is_a_real_metric_prefix(self):
        # A mapping to a token nothing is stored under resolves to a metric
        # that does not exist, which is the original defect wearing a map.
        unknown = set(CDS_NAME_BY_ISO.values()) - metric_prefixes()
        self.assertEqual(unknown, set(), f"mapped to tokens no metric uses: {sorted(unknown)}")

    def test_every_instrument_is_reachable_by_some_iso(self):
        # The other direction: a country on the board that no ISO maps to can
        # never be opened from the country panel.
        unreachable = metric_prefixes() - set(CDS_NAME_BY_ISO.values())
        self.assertEqual(unreachable, set(), f"on the board but unreachable by ISO: {sorted(unreachable)}")

    def test_the_iso_keys_are_iso_shaped(self):
        for iso in CDS_NAME_BY_ISO:
            with self.subTest(iso=iso):
                self.assertEqual(len(iso), 3)
                self.assertTrue(iso.isupper())

    def test_the_specific_codes_the_country_panel_sends(self):
        # These are the ISO codes on the COMPOSITE tab's CDS-scoring rows.
        self.assertEqual(CDS_NAME_BY_ISO["TUR"], "TURKEY")
        self.assertEqual(CDS_NAME_BY_ISO["BRA"], "BRAZIL")
        self.assertEqual(CDS_NAME_BY_ISO["EGY"], "EGYPT")
        self.assertEqual(CDS_NAME_BY_ISO["ZAF"], "SOUTH_AFRICA")

    def test_an_iso_code_never_doubles_as_a_namespace_token(self):
        # The lookup falls back to the raw input when the ISO is unmapped, so
        # a three-letter token that is ALSO a metric prefix would resolve by
        # accident and mask a missing mapping.
        collisions = set(CDS_NAME_BY_ISO) & metric_prefixes()
        self.assertEqual(collisions, set())


class TheLookupResolvesBothForms(unittest.TestCase):
    """The endpoint's resolution rule, stated without a database."""

    @staticmethod
    def resolve(country):
        upper = country.upper()
        return CDS_NAME_BY_ISO.get(upper, upper)

    def test_an_iso_code_resolves_to_the_metric_prefix(self):
        self.assertEqual(self.resolve("TUR"), "TURKEY")
        self.assertEqual(self.resolve("tur"), "TURKEY")

    def test_a_namespace_token_still_resolves_to_itself(self):
        # Anyone reading the metric names would reach for this form, and the
        # endpoint answered it correctly before the fix. It must keep working.
        self.assertEqual(self.resolve("TURKEY"), "TURKEY")
        self.assertEqual(self.resolve("SAUDI_ARABIA"), "SAUDI_ARABIA")

    def test_an_unknown_country_resolves_to_itself_and_simply_misses(self):
        # Falling through is correct: the caller gets "no coverage", which for
        # an unlisted sovereign is the true answer.
        self.assertEqual(self.resolve("XXX"), "XXX")


class TheConfiguredSetCoversTheBoard(unittest.TestCase):
    """D-0064.

    The World Government Bonds board carried 30 sovereigns and
    CDS_INSTRUMENTS configured 21. A-0014 cited CDS coverage at 33% of scored
    countries as an argument against the dimension; ten of those absences were
    simply never configured.

    This records what the board was observed to carry on 2026-09-29. It is a
    recorded expectation, not a live check - a test that fetched the board
    would fail on the source's outage rather than on our regression.
    """

    OBSERVED_ON_BOARD = {
        "Austria", "Belgium", "Denmark", "Finland", "Ireland", "Israel",
        "Netherlands", "Portugal", "Sweden", "United Kingdom",
        "France", "Germany", "Greece", "Italy", "Spain", "Switzerland",
        "Russia", "Turkey", "Egypt", "China", "Japan", "South Korea",
        "India", "Indonesia", "United States", "Canada", "Mexico",
        "Brazil", "Australia", "South Africa",
    }

    def test_every_observed_sovereign_is_configured(self):
        missing = self.OBSERVED_ON_BOARD - set(CDS_INSTRUMENTS)
        self.assertEqual(
            missing, set(),
            f"on the board on 2026-09-29 but not configured: {sorted(missing)}",
        )

    def test_the_ten_added_by_d0064_are_present(self):
        # Named individually so a bulk edit that drops them fails loudly.
        for name in ("Austria", "Belgium", "Denmark", "Finland", "Ireland",
                     "Israel", "Netherlands", "Portugal", "Sweden",
                     "United Kingdom"):
            with self.subTest(country=name):
                self.assertIn(name, CDS_INSTRUMENTS)

    def test_the_only_configured_absentee_is_the_recorded_one(self):
        # Saudi Arabia is configured and has never been on the board, which is
        # why F-0075 made it an explicit exclusion. Anything ELSE configured
        # but absent would be a silent gap.
        from pipelines.cds_fetcher import KNOWN_ABSENT_FROM_5Y_BOARD
        configured_absentees = set(CDS_INSTRUMENTS) - self.OBSERVED_ON_BOARD
        self.assertEqual(configured_absentees, set(KNOWN_ABSENT_FROM_5Y_BOARD))


if __name__ == "__main__":
    unittest.main()
