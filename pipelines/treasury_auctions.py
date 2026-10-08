"""Treasury auction results from Fiscal Data (D-0098). STUB — tests first."""
import datetime
from decimal import Decimal

PIPELINE_NAME = "Treasury_Auctions"
BACKFILL_START = datetime.date(2008, 1, 1)


class _Blank(dict):
    def __missing__(self, key):
        return Decimal(0)


def parse_record(rec: dict):
    return _Blank(null_reasons={})


def ingest_records(db, records) -> dict:
    return {"inserted": 0, "updated": 0, "unchanged": 0, "pending": 0,
            "mismatches": [], "unverifiable": 0, "share_gaps": [],
            "identity_failures": []}


def fetch_records(start, cusip=None) -> list:
    return []


def run_treasury_auctions_fetch(db, start=None, fetch=None) -> dict:
    return {"status": "stub", "mismatches": []}
