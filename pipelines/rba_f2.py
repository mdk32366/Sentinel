"""Australia - RBA statistical table F2, government bond yields (Sentinel D-0115).

Source (keyless): https://www.rba.gov.au/statistics/tables/csv/f2-data.csv

A full-history file (daily since 2013), so backfill and the daily run are the
same call; the daily run keeps the last ``DAILY_DAYS`` only. Layout: a title
line, metadata rows (Title, Description, Frequency, Type, Units, blank lines,
Source, Publication date), then ``Series ID,FCMYGBAG2D,...``; data rows after
it, dates ``%d-%b-%Y`` (``14-Oct-2026``). ``\\r`` and blank lines are
stripped. Columns are selected by series id; the indexed bond
(FCMYGBAGID) is ignored.

F2 is published weekly with the week's daily values, so its newest date lags
by up to ~8 days (F-entry, D-0115); the freshness limit is 12 days.
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

PIPELINE_NAME = "RBA_F2"
COUNTRY = "AU"
HOST = "www.rba.gov.au"
BASE_URL = f"https://{HOST}/statistics/tables/csv/f2-data.csv"
TENORS = (2, 3, 5, 10)
SERIES = {"FCMYGBAG2D": 2, "FCMYGBAG3D": 3, "FCMYGBAG5D": 5, "FCMYGBAG10D": 10}
DAILY_DAYS = 30
BACKFILL_DAYS = 1825

METRICS = make_metrics(
    COUNTRY, TENORS,
    "Australia {t}Y government bond yield (RBA F2)",
    "Reserve Bank of Australia",
    "RBA statistical table F2, Australian Government {t}Y bond yield "
    "(interpolated), daily, published weekly. Display only, not scored "
    "(Sentinel D-0115).",
)


def parse_rba(body: bytes, since: datetime = None) -> list:
    reject_html(body, PIPELINE_NAME)
    try:
        text = body.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = body.decode("cp1252")
    lines = [ln.replace("\r", "") for ln in text.split("\n")]
    lines = [ln for ln in lines if ln.strip()]
    rows = list(csv.reader(lines))
    idx = next((i for i, r in enumerate(rows) if r and r[0].strip() == "Series ID"), None)
    if idx is None:
        raise SchemaDrift(f"{PIPELINE_NAME}: no 'Series ID' row")
    header = [c.strip() for c in rows[idx]]
    missing = [s for s in SERIES if s not in header]
    if missing:
        raise SchemaDrift(f"{PIPELINE_NAME}: Series ID row lacks {missing}")
    cols = {header.index(s): t for s, t in SERIES.items()}
    data = rows[idx + 1:]
    if not data:
        raise EmptyResponse(f"{PIPELINE_NAME}: 0 data rows")
    out = []
    for r in data:
        if not r or not r[0].strip():
            continue
        try:
            when = datetime.strptime(r[0].strip(), "%d-%b-%Y")
        except ValueError as exc:
            raise SchemaDrift(f"{PIPELINE_NAME}: date {r[0]!r}") from exc
        if since is not None and when < since:
            continue
        for i, tenor in cols.items():
            if i >= len(r):
                continue
            code = code_for(COUNTRY, tenor)
            value = to_value(r[i], f"{code} {r[0]}")
            if value is not None:
                out.append((code, when, value))
    out.sort(key=lambda x: (x[1], x[0]))
    return out


def run_rba_f2(db: Session, backfill: bool = False, **fetch_kw) -> dict:
    days = BACKFILL_DAYS if backfill else DAILY_DAYS
    since = datetime.utcnow() - timedelta(days=days)

    def produce():
        body = fetch_bytes(BASE_URL, headers={"Accept": "text/csv"}, **fetch_kw)
        return parse_rba(body, since=since)

    return write_run(db, PIPELINE_NAME, METRICS, produce, BASE_URL)
