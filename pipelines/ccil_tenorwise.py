"""Sentinel D-0118: CCIL Tenorwise Indicative Yields, manual upload (red stub)."""
ATTRIBUTION = ""
MAX_BODY_BYTES = 2 * 1024 * 1024


class IngestRejected(ValueError):
    pass


def parse_ccil(body: bytes):
    return []


def ingest(db, body: bytes, uploader: str) -> dict:
    return {"inserted": 0, "updated": 0, "unchanged": 0, "rows_changed": 0, "as_of": None}
