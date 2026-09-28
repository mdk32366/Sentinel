"""ORDER-01 B2 — encode the Treasury CSV parser cases.

These were exercised by hand while `treasury_direct.py` was written. A case
that lives in a chat transcript is not a test, so they run here.

Every case takes CSV **text**, never a URL, so the whole file runs with the
internet off.
"""
import logging
import unittest
from decimal import Decimal

from pipelines.treasury_direct import PLAUSIBLE_RANGE, parse_curve_csv

HEADER = "Date,1 Mo,2 Yr,5 Yr,7 Yr,10 Yr,30 Yr"


def csv_of(*rows):
    return "\n".join([HEADER, *rows]) + "\n"


class TestDateForms(unittest.TestCase):
    def test_us_slash_format_parses(self):
        out = parse_curve_csv(csv_of("09/25/2026,4.10,4.86,5.02,5.06,5.17,5.49"))
        self.assertEqual(out[0]["date"].date().isoformat(), "2026-09-25")

    def test_iso_format_parses(self):
        out = parse_curve_csv(csv_of("2026-09-25,4.10,4.86,5.02,5.06,5.17,5.49"))
        self.assertEqual(out[0]["date"].date().isoformat(), "2026-09-25")

    def test_both_forms_yield_identical_rates(self):
        a = parse_curve_csv(csv_of("09/25/2026,4.10,4.86,5.02,5.06,5.17,5.49"))
        b = parse_curve_csv(csv_of("2026-09-25,4.10,4.86,5.02,5.06,5.17,5.49"))
        self.assertEqual(a[0]["rates"], b[0]["rates"])

    def test_unparseable_date_drops_the_row_rather_than_the_file(self):
        out = parse_curve_csv(csv_of(
            "not-a-date,4.10,4.86,5.02,5.06,5.17,5.49",
            "09/25/2026,4.10,4.86,5.02,5.06,5.17,5.49",
        ))
        self.assertEqual(len(out), 1)


class TestMissingValues(unittest.TestCase):
    """Blank / N/A / '.' must be ABSENT, never zero.

    A zero yield is a plausible number. Stored silently it is exactly the
    Principle 11 failure: right shape, right date, wrong value, nothing red.
    """

    def test_blank_cell_is_skipped_not_zeroed(self):
        out = parse_curve_csv(csv_of("09/25/2026,4.10,,5.02,5.06,5.17,5.49"))
        self.assertNotIn("DGS2", out[0]["rates"])

    def test_na_is_skipped_not_zeroed(self):
        out = parse_curve_csv(csv_of("09/25/2026,4.10,N/A,5.02,5.06,5.17,5.49"))
        self.assertNotIn("DGS2", out[0]["rates"])

    def test_dot_is_skipped_not_zeroed(self):
        """FRED's missing marker, which Treasury has also shipped."""
        out = parse_curve_csv(csv_of("09/25/2026,4.10,.,5.02,5.06,5.17,5.49"))
        self.assertNotIn("DGS2", out[0]["rates"])

    def test_no_missing_value_is_ever_stored_as_zero(self):
        out = parse_curve_csv(csv_of("09/25/2026,,,,,,"))
        self.assertEqual(out, [], "a row with no usable values must not be emitted")

    def test_surrounding_values_survive_a_missing_one(self):
        out = parse_curve_csv(csv_of("09/25/2026,4.10,N/A,5.02,5.06,5.17,5.49"))
        self.assertEqual(out[0]["rates"]["DGS7"], Decimal("5.06"))
        self.assertEqual(out[0]["rates"]["DGS30"], Decimal("5.49"))


class TestPlausibleRange(unittest.TestCase):
    def test_value_above_range_is_rejected_and_logged(self):
        too_high = PLAUSIBLE_RANGE[1] + 1
        with self.assertLogs("pipelines.treasury_direct", level=logging.WARNING) as caught:
            out = parse_curve_csv(csv_of(f"09/25/2026,4.10,{too_high},5.02,5.06,5.17,5.49"))
        self.assertNotIn("DGS2", out[0]["rates"])
        self.assertIn("plausible range", " ".join(caught.output))

    def test_value_below_range_is_rejected(self):
        too_low = PLAUSIBLE_RANGE[0] - 1
        with self.assertLogs("pipelines.treasury_direct", level=logging.WARNING):
            out = parse_curve_csv(csv_of(f"09/25/2026,4.10,{too_low},5.02,5.06,5.17,5.49"))
        self.assertNotIn("DGS2", out[0]["rates"])

    def test_negative_yields_inside_the_range_are_kept(self):
        """Negative sovereign yields are real. The guard must not eat them."""
        out = parse_curve_csv(csv_of("09/25/2026,4.10,-0.45,5.02,5.06,5.17,5.49"))
        self.assertEqual(out[0]["rates"]["DGS2"], Decimal("-0.45"))


class TestHeaderRobustness(unittest.TestCase):
    def test_unrecognised_tenor_column_is_ignored_without_breaking_the_row(self):
        """Treasury ADDING a tenor must be survivable (A-0002)."""
        text = ("Date,1 Mo,2 Yr,1.5 Mo,5 Yr,7 Yr,10 Yr,30 Yr\n"
                "09/25/2026,4.10,4.86,4.05,5.02,5.06,5.17,5.49\n")
        out = parse_curve_csv(text)
        self.assertEqual(out[0]["rates"]["DGS7"], Decimal("5.06"))
        self.assertEqual(out[0]["rates"]["DGS2"], Decimal("4.86"))

    def test_bom_on_the_header_still_matches(self):
        out = parse_curve_csv("﻿" + csv_of("09/25/2026,4.10,4.86,5.02,5.06,5.17,5.49"))
        self.assertEqual(out[0]["rates"]["DGS7"], Decimal("5.06"))

    def test_irregular_header_whitespace_still_matches(self):
        text = ("Date ,  1   Mo ,2 Yr  ,  5 Yr,7   Yr ,10 Yr, 30 Yr \n"
                "09/25/2026,4.10,4.86,5.02,5.06,5.17,5.49\n")
        out = parse_curve_csv(text)
        self.assertEqual(out[0]["rates"]["DGS7"], Decimal("5.06"))

    def test_mixed_case_header_still_matches(self):
        text = ("DATE,1 MO,2 YR,5 YR,7 YR,10 YR,30 YR\n"
                "09/25/2026,4.10,4.86,5.02,5.06,5.17,5.49\n")
        out = parse_curve_csv(text)
        self.assertEqual(out[0]["rates"]["DGS7"], Decimal("5.06"))

    def test_renaming_a_tenor_is_a_loud_failure_not_a_silent_one(self):
        """A-0002's falsification condition. Treasury RENAMING a column is not
        survivable, and must say so rather than returning empty rows."""
        text = ("Date,1 Month,2 Year,5 Year,7 Year,10 Year,30 Year\n"
                "09/25/2026,4.10,4.86,5.02,5.06,5.17,5.49\n")
        with self.assertRaises(ValueError) as caught:
            parse_curve_csv(text)
        self.assertIn("No recognised tenor columns", str(caught.exception))

    def test_empty_input_raises(self):
        with self.assertRaises(ValueError):
            parse_curve_csv("")


class TestOrdering(unittest.TestCase):
    def test_parser_preserves_source_order_which_is_newest_first(self):
        """F-0042. Recorded as a test so the next caller does not assume that
        out[-1] is the latest row - the live CSV arrives descending."""
        out = parse_curve_csv(csv_of(
            "09/25/2026,4.10,4.86,5.02,5.06,5.17,5.49",
            "09/24/2026,4.11,4.87,5.03,5.10,5.18,5.47",
        ))
        self.assertEqual(out[0]["date"].date().isoformat(), "2026-09-25")
        self.assertEqual(out[-1]["date"].date().isoformat(), "2026-09-24")
        self.assertGreater(out[0]["date"], out[-1]["date"])


if __name__ == "__main__":
    unittest.main()
