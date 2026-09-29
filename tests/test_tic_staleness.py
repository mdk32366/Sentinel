"""F-0050 — the TIC pipeline must not call a frozen source a success.

For nine months `TIC_Holdings` reported `success` on every run: 10,009 rows
updated, 0 inserted, newest observation never moving past 2025-12-01. The fetch
worked, the parse worked, the write worked. Only the data was frozen, and
nothing in the pipeline could tell the difference between "imported the current
release" and "re-imported a year that will never change".

Offline: the network fetch is stubbed with TIC-shaped text this file builds, and
the database is in-memory SQLite.
"""
import datetime
import re
import unittest
from unittest import mock

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.models import Base
from pipelines import treasury_holdings
from pipelines.treasury_holdings import (
    MAX_SOURCE_AGE_DAYS,
    StaleSourceError,
    run_treasury_holdings_fetch,
)


def tic_text(months):
    """A minimal MFH file. Tab-delimited, newest month first, as Treasury ships."""
    header_months = "\t".join(m.strftime("%b") for m in months)
    header_years = "\t".join(m.strftime("%Y") for m in months)
    rule = "\t".join("------" for _ in months)
    values = "\t".join(f"{1000 + i}" for i in range(len(months)))
    return (
        "\t\t\tMAJOR FOREIGN HOLDERS OF TREASURY SECURITIES\n"
        "\t\t\t(in billions of dollars)\n"
        "\t\t\tHOLDINGS 1/ AT END OF PERIOD\n"
        "\n\n"
        f"\t{header_months}\n"
        f"Country\t{header_years}\n"
        f"\t{rule}\n"
        "\n"
        f"Japan\t{values}\n"
        f"United Kingdom\t{values}\n"
    )


def months_ending(days_ago, count=3):
    newest = datetime.datetime.utcnow() - datetime.timedelta(days=days_ago)
    newest = newest.replace(day=1)
    out = []
    for i in range(count):
        month = newest.month - i
        year = newest.year
        while month <= 0:
            month += 12
            year -= 1
        out.append(datetime.datetime(year, month, 1))
    return out


class TestTicStaleness(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.addCleanup(self.db.close)

    def _run(self, days_ago):
        text = tic_text(months_ending(days_ago))
        with mock.patch.object(treasury_holdings, "fetch_tic_mfh_data",
                               return_value=text):
            return run_treasury_holdings_fetch(self.db)

    def test_a_current_source_succeeds(self):
        """Clause (c): correct and incorrect must differ. A guard that failed
        unconditionally would pass the staleness test and be worthless."""
        self.assertEqual(self._run(days_ago=40)["status"], "success")

    def test_a_frozen_source_fails(self):
        """The case that actually happened: 301 days, reported as success."""
        self.assertEqual(self._run(days_ago=301)["status"], "failed")

    def test_failure_is_failed_not_partial(self):
        """D-0027. `partial` reads as 'mostly fine' and is what let this sit
        for nine months."""
        self.assertNotEqual(self._run(days_ago=301)["status"], "partial")

    def test_the_error_names_the_url_and_the_age(self):
        """A log line that does not say WHICH source and HOW stale sends the
        next person back to the database to work it out."""
        errors = " ".join(self._run(days_ago=301).get("errors") or [])
        self.assertIn("ticdata.treasury.gov", errors)
        self.assertIn(str(MAX_SOURCE_AGE_DAYS), errors)

        # Assert the SHAPE, not a literal count. The fixture's newest row is
        # computed relative to now and snapped to the 1st of the month, so the
        # exact age changes every day - an earlier version of this test
        # hardcoded "301 days old" and failed the following morning.
        match = re.search(r"is (\d+) days old", errors)
        self.assertIsNotNone(match, f"age not reported in: {errors}")
        self.assertGreater(int(match.group(1)), MAX_SOURCE_AGE_DAYS)

    def test_boundary_sits_where_the_constant_says(self):
        self.assertEqual(self._run(days_ago=MAX_SOURCE_AGE_DAYS - 25)["status"],
                         "success")
        self.assertEqual(self._run(days_ago=MAX_SOURCE_AGE_DAYS + 40)["status"],
                         "failed")

    def test_the_limit_accommodates_a_real_publication_cycle(self):
        """TIC is monthly at ~45 days in arrears, so a healthy newest row is
        around 60 days old and 75 at the end of a cycle. A limit that fired on
        those would be the decoration D-0024 exists to prevent."""
        self.assertGreater(MAX_SOURCE_AGE_DAYS, 75)

    def test_stale_source_error_is_distinguishable(self):
        """It must not be swallowed by the per-country error path, which
        legitimately produces `partial`."""
        self.assertTrue(issubclass(StaleSourceError, RuntimeError))


if __name__ == "__main__":
    unittest.main()
