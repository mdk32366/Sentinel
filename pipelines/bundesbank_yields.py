"""Germany - Bundesbank Svensson fitted Bund yields (Sentinel D-0111, vault:D-0057).

Source: Deutsche Bundesbank SDMX web service, official and free.

    https://api.statistiken.bundesbank.de/rest/data/BBSIS/
        D.I.ZST.ZI.EUR.S1311.B.A604.R{TT}XX.R.A.A._Z._Z.A
    ?lastNObservations=N   (daily run)   |   ?startPeriod=YYYY-MM-DD (backfill)
    Accept: text/csv  ->  semicolon-separated; one observation per row, the
    TIME_PERIOD;OBS_VALUE pair. {TT} in 02, 05, 07, 10, 30.

"Zinsstrukturkurve (Svensson-Methode) / Boersennotierte Bundeswertpapiere /
N Jahr(e) RLZ / Tageswerte": zero-coupon yields at exact maturity from the
Svensson curve fitted to listed Federal securities. Type FIT.

Observed quirk (findings, 2026-10-21): a 200 whose body is the header line
and nothing else. That is retried like a 5xx and, after the last attempt,
the run is ``failed``. It is never recorded as a 0-row success.
"""
from __future__ import annotations

import csv
import io
import logging
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from pipelines.foreign_bond_common import (
    CATEGORY,
    TENORS,
    EmptyResponse,
    SchemaDrift,
    code_for,
    fetch_bytes,
    to_value,
    write_run,
)

logger = logging.getLogger(__name__)

PIPELINE_NAME = "Bundesbank_Yields"
HOST = "api.statistiken.bundesbank.de"
SERIES_KEY = "BBSIS/D.I.ZST.ZI.EUR.S1311.B.A604.R{tt}XX.R.A.A._Z._Z.A"
BASE_URL = f"https://{HOST}/rest/data/"
DAILY_LAST_N = 10
BACKFILL_DAYS = 1825  # five years, like FRED's days_back

REQUIRED_COLUMNS = ("TIME_PERIOD", "OBS_VALUE")


def series_url(tenor: int, start: str = None, last_n: int = DAILY_LAST_N) -> str:
    key = SERIES_KEY.format(tt=f"{tenor:02d}")
    query = f"startPeriod={start}" if start else f"lastNObservations={last_n}"
    return f"{BASE_URL}{key}?{query}"


METRICS = [
    {
        "code": code_for("DE", t),
        "name": f"Germany {t}Y Bund yield (Bundesbank fitted)",
        "category": CATEGORY,
        "unit": "%",
        "source": "Bundesbank",
        "description": (
            f"FIT. Svensson zero-coupon yield at {t}Y on listed Federal "
            f"securities, daily. Bundesbank SDMX "
            f"{SERIES_KEY.format(tt=f'{t:02d}')}. Display only, not scored "
            f"(Sentinel D-0111)."
        ),
    }
    for t in TENORS
]


def _rows(body: bytes):
    text = body.decode("utf-8-sig", errors="strict")
    reader = csv.reader(io.StringIO(text), delimiter=";")
    header = next(reader, None)
    return header, [r for r in reader if any(cell.strip() for cell in r)]


def is_header_only(body: bytes) -> bool:
    """True for a 200 that carries the header line and no observation."""
    try:
        header, rows = _rows(body)
    except UnicodeDecodeError:
        return False
    return header is not None and not rows


def parse_bundesbank(body: bytes, tenor: int) -> list:
    """CSV bytes for one tenor -> [(code, datetime, Decimal)], oldest first."""
    code = code_for("DE", tenor)
    try:
        header, rows = _rows(body)
    except UnicodeDecodeError as exc:
        raise SchemaDrift(f"{code}: body is not UTF-8") from exc
    if header is None:
        raise SchemaDrift(f"{code}: empty body")
    missing = [c for c in REQUIRED_COLUMNS if c not in header]
    if missing:
        raise SchemaDrift(f"{code}: header lacks {missing}")
    if not rows:
        raise EmptyResponse(f"{code}: header only, 0 observations")
    i_date = header.index("TIME_PERIOD")
    i_val = header.index("OBS_VALUE")
    i_mat = header.index("BBK_SEIS_MATURITY") if "BBK_SEIS_MATURITY" in header else None

    out = []
    for n, row in enumerate(rows, start=2):
        if len(row) <= max(i_date, i_val):
            raise SchemaDrift(f"{code}: row {n} has {len(row)} fields")
        if i_mat is not None and row[i_mat] != f"R{tenor:02d}XX":
            raise SchemaDrift(f"{code}: row {n} is maturity {row[i_mat]!r}")
        try:
            when = datetime.strptime(row[i_date].strip(), "%Y-%m-%d")
        except ValueError as exc:
            raise SchemaDrift(f"{code}: row {n} date {row[i_date]!r}") from exc
        value = to_value(row[i_val], f"{code} {row[i_date]}")
        if value is None:
            continue
        out.append((code, when, value))
    out.sort(key=lambda r: r[1])
    return out


def fetch_bundesbank(tenor: int, start: str = None, **kw) -> bytes:
    return fetch_bytes(
        series_url(tenor, start=start),
        headers={"Accept": "text/csv"},
        is_empty=is_header_only,
        **kw,
    )


def run_bundesbank_yields(db: Session, backfill: bool = False, **fetch_kw) -> dict:
    """All five tenors, or nothing. ``backfill`` reads five years."""
    start = None
    if backfill:
        start = (datetime.utcnow() - timedelta(days=BACKFILL_DAYS)).strftime("%Y-%m-%d")

    def produce():
        rows = []
        for tenor in TENORS:
            body = fetch_bundesbank(tenor, start=start, **fetch_kw)
            rows.extend(parse_bundesbank(body, tenor))
        return rows

    return write_run(db, PIPELINE_NAME, METRICS, produce, BASE_URL)


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO)
    from database.connection import get_session

    session = get_session()
    try:
        print(run_bundesbank_yields(session, backfill="--backfill" in sys.argv))
    finally:
        session.close()
