"""Norway - Norges Bank generic government bond rates (Sentinel D-0115).

Source (keyless SDMX REST, https://app.norges-bank.no/query/):

    https://data.norges-bank.no/api/data/GOVT_GENERIC_RATES/B..GBON?format=csv&startPeriod=YYYY-MM-DD

One call. ``;``-separated CSV with TENOR, TIME_PERIOD and OBS_VALUE columns,
long format; it is pivoted on TENOR. Tenors 3Y, 5Y, 7Y, 10Y (Norway has no
2Y generic). Other tenors in the answer are ignored. Display only.
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

PIPELINE_NAME = "Norges_GOVT"
COUNTRY = "NO"
HOST = "data.norges-bank.no"
BASE_URL = f"https://{HOST}/api/data/GOVT_GENERIC_RATES/B..GBON"
TENORS = (3, 5, 7, 10)
TENOR_KEYS = {"3Y": 3, "5Y": 5, "7Y": 7, "10Y": 10}
REQUIRED_COLUMNS = ("TENOR", "TIME_PERIOD", "OBS_VALUE")
DAILY_DAYS = 14
BACKFILL_DAYS = 1825

METRICS = make_metrics(
    COUNTRY, TENORS,
    "Norway {t}Y government bond yield (Norges Bank)",
    "Norges Bank",
    "Norges Bank GOVT_GENERIC_RATES B.{t}Y.GBON, generic Norwegian "
    "government bond {t}Y yield, business daily. Display only, not scored "
    "(Sentinel D-0115).",
)


def series_url(start: str) -> str:
    return f"{BASE_URL}?format=csv&startPeriod={start}"


def parse_norges(body: bytes) -> list:
    reject_html(body, PIPELINE_NAME)
    try:
        text = body.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise SchemaDrift(f"{PIPELINE_NAME}: body is not UTF-8") from exc
    reader = csv.reader(io.StringIO(text), delimiter=";")
    header = next(reader, None)
    if header is None:
        raise SchemaDrift(f"{PIPELINE_NAME}: empty body")
    header = [h.strip() for h in header]
    missing = [c for c in REQUIRED_COLUMNS if c not in header]
    if missing:
        raise SchemaDrift(f"{PIPELINE_NAME}: header lacks {missing}")
    rows = [r for r in reader if any(c.strip() for c in r)]
    if not rows:
        raise EmptyResponse(f"{PIPELINE_NAME}: header only, 0 observations")
    i_t, i_d, i_v = (header.index(c) for c in REQUIRED_COLUMNS)
    out = []
    for n, r in enumerate(rows, start=2):
        if len(r) <= max(i_t, i_d, i_v):
            raise SchemaDrift(f"{PIPELINE_NAME}: row {n} has {len(r)} fields")
        tenor = TENOR_KEYS.get(r[i_t].strip())
        if tenor is None:
            continue
        try:
            when = datetime.strptime(r[i_d].strip(), "%Y-%m-%d")
        except ValueError as exc:
            raise SchemaDrift(f"{PIPELINE_NAME}: row {n} date {r[i_d]!r}") from exc
        code = code_for(COUNTRY, tenor)
        value = to_value(r[i_v], f"{code} {r[i_d]}")
        if value is not None:
            out.append((code, when, value))
    out.sort(key=lambda x: (x[1], x[0]))
    return out


def run_norges_govt(db: Session, backfill: bool = False, **fetch_kw) -> dict:
    days = BACKFILL_DAYS if backfill else DAILY_DAYS
    start = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")

    def produce():
        body = fetch_bytes(series_url(start), headers={"Accept": "text/csv"}, **fetch_kw)
        return parse_norges(body)

    return write_run(db, PIPELINE_NAME, METRICS, produce, BASE_URL)
