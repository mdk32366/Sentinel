"""Spain - Banco de España table TI_1_3, secondary-market bond yields (Sentinel D-0115).

Source (keyless): https://www.bde.es/webbe/es/estadisticas/compartido/datos/csv/ti_1_3.csv

Choices recorded as A-entries in D-0115:
  - the file is Latin-1 (``CÓDIGO DE LA SERIE``) and is decoded as Latin-1
    explicitly, never sniffed;
  - ``_`` and empty cells are missing (weekends carry a full row of ``_``);
  - the 10Y is the secondary-market ("mercado secundario") 10Y bond yield,
    series D_G0B1F0ZP, not a primary-auction rate.

Layout: six metadata rows (CÓDIGO DE LA SERIE, NÚMERO SECUENCIAL, ALIAS,
DESCRIPCIÓN, UNIDADES, FRECUENCIA), then data rows ``"20 OCT 2026",...``
until a ``FUENTE`` / ``NOTAS`` footer. Columns are selected by series code
from the first row, never by position:

    D_G0B1F0ZN 3Y   D_G0B1F0ZO 5Y   D_G0B1F0ZP 10Y   D_G0B1F0ZQ 15Y

Month names are Spanish abbreviations, with English variants accepted. A row
whose month is unknown is a parse error for that row only: it is skipped and
logged, and the rest of the file is read. The whole history is one file, so
rows older than the window are dropped before their values are read (1990s
Spanish yields exceed the plausible range). Display only.
"""
from __future__ import annotations

import csv
import io
import logging
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from pipelines.foreign_bond_common import (
    EmptyResponse,
    SchemaDrift,
    code_for,
    fetch_bytes,
    make_metrics,
    reject_html,
    to_value,
    write_run,
)

logger = logging.getLogger(__name__)

PIPELINE_NAME = "BdE_TI13"
COUNTRY = "ES"
HOST = "www.bde.es"
BASE_URL = f"https://{HOST}/webbe/es/estadisticas/compartido/datos/csv/ti_1_3.csv"
TENORS = (3, 5, 10, 15)
SERIES = {"D_G0B1F0ZN": 3, "D_G0B1F0ZO": 5, "D_G0B1F0ZP": 10, "D_G0B1F0ZQ": 15}
META_ROWS = 6
FOOTER = ("FUENTE", "NOTAS")
MISSING = ("", "_")
MONTHS = {
    "ENE": 1, "FEB": 2, "MAR": 3, "ABR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AGO": 8, "SEP": 9, "SET": 9, "OCT": 10, "NOV": 11, "DIC": 12,
    # English variants
    "JAN": 1, "APR": 4, "AUG": 8, "DEC": 12,
}
DAILY_DAYS = 14
BACKFILL_DAYS = 1825

METRICS = make_metrics(
    COUNTRY, TENORS,
    "Spain {t}Y government bond yield (Banco de España TI_1_3)",
    "Banco de España",
    "Banco de España table TI_1_3, secondary-market Spanish government bond "
    "{t}Y yield, daily. Display only, not scored (Sentinel D-0115).",
)


class RowDateError(ValueError):
    """One data row's date could not be read (that row only)."""


def parse_date(raw: str) -> datetime:
    parts = raw.strip().split()
    if len(parts) != 3:
        raise RowDateError(f"date {raw!r}")
    day, mon, year = parts
    month = MONTHS.get(mon.upper().rstrip("."))
    if month is None:
        raise RowDateError(f"unknown month in {raw!r}")
    try:
        return datetime(int(year), month, int(day))
    except ValueError as exc:
        raise RowDateError(f"date {raw!r}") from exc


def decode(body: bytes) -> str:
    """The file is Latin-1 (A-entry, D-0115): a UTF-8 decode garbles its
    accented headers or raises."""
    return body.decode("latin-1")


def parse_bde(body: bytes, since: datetime = None) -> list:
    reject_html(body, PIPELINE_NAME)
    text = decode(body)
    rows = list(csv.reader(io.StringIO(text)))
    if len(rows) <= META_ROWS:
        raise EmptyResponse(f"{PIPELINE_NAME}: no data rows after the metadata")
    header = [c.strip() for c in rows[0]]
    if not header or "DIGO DE LA SERIE" not in header[0].upper():
        raise SchemaDrift(f"{PIPELINE_NAME}: first row is not CÓDIGO DE LA SERIE")
    missing = [s for s in SERIES if s not in header]
    if missing:
        raise SchemaDrift(f"{PIPELINE_NAME}: header lacks {missing}")
    cols = {header.index(s): t for s, t in SERIES.items()}
    out = []
    data = 0
    for r in rows[META_ROWS:]:
        if not r or not any(c.strip() for c in r):
            continue
        if r[0].strip().upper() in FOOTER:
            break
        data += 1
        try:
            when = parse_date(r[0])
        except RowDateError as exc:
            logger.warning("%s: row skipped, %s", PIPELINE_NAME, exc)
            continue
        if since is not None and when < since:
            continue
        for i, tenor in cols.items():
            if i >= len(r) or r[i].strip() in MISSING:
                continue
            code = code_for(COUNTRY, tenor)
            value = to_value(r[i], f"{code} {r[0]}")
            if value is not None:
                out.append((code, when, value))
    if not data:
        raise EmptyResponse(f"{PIPELINE_NAME}: 0 data rows")
    out.sort(key=lambda x: (x[1], x[0]))
    return out


def run_bde_ti13(db: Session, backfill: bool = False, **fetch_kw) -> dict:
    days = BACKFILL_DAYS if backfill else DAILY_DAYS
    since = datetime.utcnow() - timedelta(days=days)

    def produce():
        body = fetch_bytes(BASE_URL, headers={"Accept": "text/csv"}, **fetch_kw)
        return parse_bde(body, since=since)

    return write_run(db, PIPELINE_NAME, METRICS, produce, BASE_URL)
