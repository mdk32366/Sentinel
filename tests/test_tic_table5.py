"""F-0088 / F-0089 — the current MFH table, and thresholds that a healthy
source can actually satisfy.

The pipeline read `Publish/mfhhis01.txt` for nine months. That file is served,
returns 200, and is rewritten by every release — it is the *history* file, and
it stopped being extended past December 2025 when Treasury retired the
standalone MFH release in March 2023 and folded the table into SLT as Table 5.
Every layer reported success on a frozen year.

Then, having found the live file, the thresholds turned out to be set below
what a healthy TIC can be. Both findings are pinned here.

Every case takes file **text**, never a URL, so the whole file runs offline.
"""
import re
import unittest
from datetime import datetime

from pipelines.freshness_watchdog import CHECKS
from pipelines.treasury_holdings import (
    MAX_SOURCE_AGE_DAYS,
    TIC_MFH_HISTORY_URL,
    TIC_MFH_URL,
    parse_tic_mfh,
)

# A trimmed copy of the real file, keeping the shapes that matter: the prose
# header, the `Link:` line that names the file, the single-row ISO header, real
# country rows, and the "Of Which:" aggregates that are not countries.
TABLE5 = "\r\n".join([
    "Table 5: Major Foreign Holders of Treasury Securities\t\t\t",
    "Holdings at end of time period\t\t\t",
    "Billions of dollars\t\t\t",
    "Link: https://ticdata.treasury.gov/resource-center/data-chart-center/tic/Documents/slt_table5.txt\t\t\t",
    "\t\t\t",
    "Country\t2026-07\t2026-06\t2026-05",
    "Japan\t1103.9\t1116.7\t1143.1",
    "United Kingdom\t998.3\t939.9\t948.6",
    "China, Mainland\t618.0\t633.4\t659.3",
    "Grand Total\t9158.1\t9130.0\t9045.2",
    "Of Which: Foreign Official\t3773.1\t3766.0\t3750.9",
    "Of Which: Foreign Official Treasury Bills\t354.4\t350.1\t349.0",
    "",
])

# The legacy layout, which splits the header over two rows and stacks a fresh
# pair per year. Still served, and still the only source of deep history.
HISTORY = "\r\n".join([
    "",
    "                    MAJOR FOREIGN HOLDERS OF TREASURY SECURITIES",
    "                              (in billions of dollars)",
    "                            HOLDINGS 1/ AT END OF PERIOD",
    "",
    "\tDec\tNov\tOct",
    "Country\t2025\t2025\t2025",
    "\t------\t------\t------",
    "Japan\t1185.5\t1202.7\t1200.0",
    "China, Mainland\t684.4\t683.9\t687.7",
    "",
])


class TestTable5Layout(unittest.TestCase):
    def test_iso_month_header_is_read(self):
        out = parse_tic_mfh(TABLE5)
        self.assertEqual(
            sorted(out["Japan"]), sorted(["Jul 2026", "Jun 2026", "May 2026"])
        )

    def test_values_land_on_the_right_months(self):
        # Column order is newest-first, which is the reverse of how a reader
        # would write it. An off-by-one here would silently date July's
        # holdings to May.
        japan = parse_tic_mfh(TABLE5)["Japan"]
        self.assertEqual(japan["Jul 2026"], 1103.9)
        self.assertEqual(japan["Jun 2026"], 1116.7)
        self.assertEqual(japan["May 2026"], 1143.1)

    def test_iso_months_normalise_to_the_callers_date_format(self):
        # run_treasury_holdings_fetch does strptime("01 %s", "%d %b %Y") on
        # these keys. A key of "2026-07" parses in neither layout and would
        # make every row a per-country error rather than an import.
        for key in parse_tic_mfh(TABLE5)["Japan"]:
            datetime.strptime(f"01 {key}", "%d %b %Y")

    def test_aggregate_rows_are_not_countries(self):
        out = parse_tic_mfh(TABLE5)
        for name in out:
            self.assertFalse(
                name.startswith("Of Which"),
                f"{name!r} parsed as a country. At 3773.1 it outranks Japan "
                f"and looks exactly like the largest holder.",
            )
        self.assertNotIn("Grand Total", out)

    def test_the_link_line_is_not_a_country(self):
        self.assertNotIn(
            "Link:", " ".join(parse_tic_mfh(TABLE5)),
        )

    def test_real_countries_survive(self):
        out = parse_tic_mfh(TABLE5)
        self.assertEqual(
            sorted(out), ["China, Mainland", "Japan", "United Kingdom"]
        )


class TestLegacyLayoutStillParses(unittest.TestCase):
    """The history file is the only source of pre-2025 monthly data, so the
    two-row header path is a live format and not sentiment."""

    def test_stacked_month_and_year_rows_are_read(self):
        out = parse_tic_mfh(HISTORY)
        self.assertEqual(out["Japan"]["Dec 2025"], 1185.5)
        self.assertEqual(out["China, Mainland"]["Oct 2025"], 687.7)

    def test_both_layouts_produce_the_same_key_format(self):
        a = set(parse_tic_mfh(TABLE5)["Japan"])
        b = set(parse_tic_mfh(HISTORY)["Japan"])
        for key in a | b:
            self.assertRegex(key, r"^[A-Z][a-z]{2} \d{4}$")

    def test_a_year_row_alone_does_not_set_dates(self):
        # The Table 5 branch fires on any row starting with "Country", so it
        # must not swallow the legacy year row - which starts the same way and
        # carries bare years, not ISO months.
        out = parse_tic_mfh("\r\n".join([
            "Country\t2025\t2025",
            "Japan\t1.0\t2.0",
        ]))
        self.assertEqual(out, {}, "bare years were mistaken for ISO months")


class TestTheUrlIsTheCurrentRelease(unittest.TestCase):
    def test_the_scheduled_url_is_table_5(self):
        self.assertIn("slt_table5", TIC_MFH_URL)

    def test_the_history_file_is_not_what_gets_fetched(self):
        # F-0088 in one assertion. mfhhis01.txt is still served and still
        # touched by every release; it is simply not the current table.
        self.assertNotEqual(TIC_MFH_URL, TIC_MFH_HISTORY_URL)
        self.assertNotIn("mfhhis", TIC_MFH_URL)


class TestThresholdsAHealthySourceCanSatisfy(unittest.TestCase):
    """F-0089.

    A row is dated to the FIRST of its data month, and the release covers the
    month ending two months earlier. The 2026-09-16 release published July
    2026, so a row dated 2026-07-01 was 77 days old on arrival and reaches
    ~106 days before the next release lands.

    Both thresholds were set from "~45 days in arrears" — counted from the
    wrong end of the month, and about a month too low. Nothing noticed,
    because the source was frozen at 303 days for the entire life of both
    numbers: every threshold agrees about a year-old file.
    """

    # D-0077 retargeted these. They were measured from the row's LABEL - the
    # first of the data month - which is what the stored date is. The watchdog
    # now measures from the end of the period the row describes, so the same
    # publication cycle is a month shorter: the 2026-09-16 release published
    # data covering to 2026-07-31, 47 days earlier, not 2026-07-01, 77 days
    # earlier. Both describe one observation; only one of them is the age of the
    # data.
    #
    # Not a weakening. The bound still pins the cycle, against the same release
    # calendar, measured from the end of the period instead of its name.
    BEST_CASE_AGE = 47    # the day a release lands
    WORST_CASE_AGE = 76   # the day before the next one

    def _tic(self):
        tic = next((s for s in CHECKS if s["key"] == "tic"), None)
        self.assertIsNotNone(tic, "the watchdog no longer configures tic")
        return tic

    def test_the_watchdog_can_actually_report_tic_as_current(self):
        # At 55 this was unreachable: TIC was never current at any point in
        # any cycle, however promptly Treasury published. Harmless while the
        # data really was a year old - then D-0074 put the verdict on every
        # tab, where a permanently red strip is what teaches a reader to stop
        # reading it.
        self.assertGreaterEqual(self._tic()["max_age_days"], self.WORST_CASE_AGE)

    def test_the_watchdog_still_catches_a_missed_release(self):
        # One skipped month puts the newest observation at ~106 days from its
        # coverage end. A tolerance loose enough to pass that would be
        # decoration (D-0024).
        self.assertLess(self._tic()["max_age_days"], self.WORST_CASE_AGE + 31)

    def test_the_pipeline_does_not_refuse_a_current_file(self):
        # At 100 this sat inside the healthy range: the last fortnight of
        # every cycle would have been refused as frozen.
        #
        # This one keeps the LABEL basis on purpose. MAX_SOURCE_AGE_DAYS is
        # applied in treasury_holdings.py against the parsed row date, which is
        # the first of the data month - it never sees a coverage end. Two
        # thresholds measured against two different things is exactly what
        # F-0087 was about, so the difference is stated rather than silently
        # carried: 106 is the label-based worst case and remains the right bound
        # for this constant.
        self.assertGreater(MAX_SOURCE_AGE_DAYS, 106)

    def test_the_pipeline_still_refuses_a_frozen_one(self):
        # Two missed releases is ~166 days. The December-2025 freeze that
        # started all of this reached 303.
        self.assertLess(MAX_SOURCE_AGE_DAYS, 166)

    def test_the_two_thresholds_are_ordered_and_distinct(self):
        # F-0087: these answer different questions — "the source has missed
        # its release" and "this file is too old to import". The warning must
        # come first, or the pipeline refuses data the screen still calls
        # current.
        self.assertLess(self._tic()["max_age_days"], MAX_SOURCE_AGE_DAYS)

    def test_no_comment_still_claims_45_days_in_arrears(self):
        # The wrong number was justified by a wrong sentence, repeated in two
        # files. Leaving the sentence is how the number comes back.
        for path in ("pipelines/treasury_holdings.py",
                     "pipelines/freshness_watchdog.py"):
            with open(path, encoding="utf-8") as fh:
                body = fh.read()
            for line in body.splitlines():
                if re.search(r"45 days in arrears", line):
                    self.assertIn(
                        "F-0089", body,
                        f"{path}: '45 days in arrears' survives without the "
                        f"correction that explains it",
                    )


if __name__ == "__main__":
    unittest.main()
