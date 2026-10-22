"""Japan - Ministry of Finance JGB constant-maturity yields (Sentinel D-0111, vault:D-0057).

Source: MOF "Interest Rate" (国債金利情報), official and free.

    Daily:    https://www.mof.go.jp/jgbs/reference/interest_rate/jgbcm.csv
              (current month)
    Backfill: https://www.mof.go.jp/jgbs/reference/interest_rate/data/jgbcm_all.csv
              (1974-09-24 to the end of the previous month; verified
              2026-10-21, see findings.md)

Shift-JIS (decode cp932). Header ``基準日,1年,2年,...,30年,40年``; dates in
Japanese era form, e.g. ``R8.10.20`` (Reiwa 8 = 2026), ``H30.4.2``,
``S49.9.24``. ``-`` is a missing value. A blank first cell or a ``※`` note
line is the file's trailer and is skipped.

These are MOF constant-maturity par yields interpolated from benchmark JGBs,
labelled CMT, not FIT.
"""
from __future__ import annotations

import csv
import io
import logging
import re
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from pipelines.foreign_bond_common import (
    CATEGORY,
    TENORS,
    SchemaDrift,
    code_for,
    fetch_bytes,
    to_value,
    write_run,
)

logger = logging.getLogger(__name__)

PIPELINE_NAME = "MOF_JGB"
HOST = "www.mof.go.jp"
CURRENT_URL = f"https://{HOST}/jgbs/reference/interest_rate/jgbcm.csv"
HISTORY_URL = f"https://{HOST}/jgbs/reference/interest_rate/data/jgbcm_all.csv"
DATE_HEADER = "基準日"
BACKFILL_DAYS = 1825

# First year of each era, minus one: era year y -> base + y.
ERA_BASE = {"M": 1867, "T": 1911, "S": 1925, "H": 1988, "R": 2018}
_ERA_RE = re.compile(r"^([MTSHR])(\d{1,2})\.(\d{1,2})\.(\d{1,2})$")

METRICS = [
    {
        "code": code_for("JP", t),
        "name": f"Japan {t}Y JGB yield (MOF CMT)",
        "category": CATEGORY,
        "unit": "%",
        "source": "MOF",
        "description": (
            f"CMT. Ministry of Finance constant-maturity JGB yield, column "
            f"{t}年, daily. jgbcm.csv. Display only, not scored "
            f"(Sentinel D-0111)."
        ),
    }
    for t in TENORS
]


def era_to_date(text: str) -> datetime:
    """``R8.10.20`` -> 2026-10-20. SchemaDrift on anything else."""
    m = _ERA_RE.match(text.strip())
    if not m:
        raise SchemaDrift(f"MOF date {text!r} is not an era date")
    era, y, mo, d = m.group(1), int(m.group(2)), int(m.group(3)), int(m.group(4))
    try:
        return datetime(ERA_BASE[era] + y, mo, d)
    except ValueError as exc:
        raise SchemaDrift(f"MOF date {text!r}: {exc}") from exc


def parse_mof_csv(body: bytes) -> list:
    """jgbcm(_all).csv bytes -> [(code, datetime, Decimal)], oldest first."""
    try:
        text = body.decode("cp932")
    except UnicodeDecodeError as exc:
        raise SchemaDrift(f"MOF body is not Shift-JIS: {exc}") from exc
    reader = csv.reader(io.StringIO(text))
    header = None
    cols = {}
    out = []
    for n, row in enumerate(reader, start=1):
        if not row:
            continue
        first = row[0].strip()
        if header is None:
            if first == DATE_HEADER:
                header = [c.strip() for c in row]
                for t in TENORS:
                    label = f"{t}年"
                    if label not in header:
                        raise SchemaDrift(f"MOF header lacks {label}")
                    cols[t] = header.index(label)
            continue
        if first == "" or first.startswith("※"):
            continue
        when = era_to_date(first)
        for t, idx in cols.items():
            code = code_for("JP", t)
            raw = row[idx] if idx < len(row) else None
            value = to_value(raw, f"{code} {first}")
            if value is not None:
                out.append((code, when, value))
    if header is None:
        raise SchemaDrift(f"MOF csv has no {DATE_HEADER} header row")
    out.sort(key=lambda r: (r[1], r[0]))
    return out


def run_mof_jgb(db: Session, backfill: bool = False, **fetch_kw) -> dict:
    def produce():
        rows = parse_mof_csv(fetch_bytes(CURRENT_URL, **fetch_kw))
        if backfill:
            since = datetime.utcnow() - timedelta(days=BACKFILL_DAYS)
            rows.extend(r for r in parse_mof_csv(fetch_bytes(HISTORY_URL, **fetch_kw)) if r[1] >= since)
        return rows

    return write_run(db, PIPELINE_NAME, METRICS, produce, CURRENT_URL)


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO)
    from database.connection import get_session

    session = get_session()
    try:
        print(run_mof_jgb(session, backfill="--backfill" in sys.argv))
    finally:
        session.close()
