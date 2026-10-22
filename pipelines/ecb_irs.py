"""ECB long-term interest rates for convergence purposes, monthly (Sentinel D-0116).

Source (keyless ECB Data Portal SDMX REST):

    https://data-api.ecb.europa.eu/service/data/IRS/M.IT+ES+GR+PT+PL.L.L40.CI.0000..N.Z?format=csvdata&startPeriod=YYYY-MM

One request, five monthly series: the Maastricht-criterion 10-year
government bond yield of Italy, Spain, Greece, Portugal and Poland. The
currency slot is left open: four keys resolve to EUR, Poland's to PLN.

Stored as FB_{CC}_10Y_ECB_M at the LAST calendar day of the month (a monthly
average, not a month-end print). Display only: the country cards' second
10Y fallback (daily -> ECB_M -> IRLTLT), and the only 10Y Greece and Portugal
have. Never scored; FB_DIM4_CODES does not change.
"""
from __future__ import annotations

import calendar
import csv
import io
import logging
from datetime import datetime

from sqlalchemy.orm import Session

from pipelines.foreign_bond_common import (
    CATEGORY,
    EmptyResponse,
    SchemaDrift,
    fetch_bytes,
    reject_html,
    to_value,
    write_run,
)

logger = logging.getLogger(__name__)

PIPELINE_NAME = "ECB_IRS"
HOST = "data-api.ecb.europa.eu"
COUNTRIES = ("IT", "ES", "GR", "PT", "PL")
BASE_URL = f"https://{HOST}/service/data/IRS/M.{'+'.join(COUNTRIES)}.L.L40.CI.0000..N.Z"
REQUIRED_COLUMNS = ("KEY", "TIME_PERIOD", "OBS_VALUE")
DAILY_MONTHS = 13
BACKFILL_MONTHS = 60
NAMES = {"IT": "Italy", "ES": "Spain", "GR": "Greece", "PT": "Portugal", "PL": "Poland"}


def irs_code(cc: str) -> str:
    return f"FB_{cc}_10Y_ECB_M"


METRICS = [
    {
        "code": irs_code(cc),
        "name": f"{NAMES[cc]} 10Y long-term interest rate, monthly (ECB IRS)",
        "category": CATEGORY,
        "unit": "%",
        "source": "ECB",
        "description": (
            f"ECB IRS M.{cc}.L.L40.CI.0000.*.N.Z: long-term interest rate for "
            "convergence purposes, 10-year government bond, monthly average, "
            "stored at month end. Card fallback only, not scored (Sentinel D-0116)."
        ),
    }
    for cc in COUNTRIES
]


def series_url(start: str) -> str:
    return f"{BASE_URL}?format=csvdata&startPeriod={start}"


def key_to_code(key: str):
    # IRS.M.PL.L.L40.CI.0000.PLN.N.Z
    parts = key.strip().split(".")
    if len(parts) != 10 or parts[0] != "IRS" or parts[1] != "M":
        return None
    if parts[2] not in COUNTRIES or parts[3:7] != ["L", "L40", "CI", "0000"]:
        return None
    if parts[8:] != ["N", "Z"]:
        return None
    return irs_code(parts[2])


def month_end(period: str) -> datetime:
    try:
        first = datetime.strptime(period.strip(), "%Y-%m")
    except ValueError as exc:
        raise SchemaDrift(f"{PIPELINE_NAME}: period {period!r} is not YYYY-MM") from exc
    last = calendar.monthrange(first.year, first.month)[1]
    return first.replace(day=last)


def parse_irs(body: bytes) -> list:
    reject_html(body, PIPELINE_NAME)
    try:
        text = body.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise SchemaDrift(f"{PIPELINE_NAME}: body is not UTF-8") from exc
    reader = csv.reader(io.StringIO(text))
    header = next(reader, None)
    if header is None:
        raise EmptyResponse(f"{PIPELINE_NAME}: empty body")
    header = [h.strip() for h in header]
    missing = [c for c in REQUIRED_COLUMNS if c not in header]
    if missing:
        raise SchemaDrift(f"{PIPELINE_NAME}: header lacks {missing}")
    rows = [r for r in reader if any(c.strip() for c in r)]
    if not rows:
        raise EmptyResponse(f"{PIPELINE_NAME}: header only, 0 observations")
    i_k, i_d, i_v = (header.index(c) for c in REQUIRED_COLUMNS)
    out = []
    for n, r in enumerate(rows, start=2):
        if len(r) <= max(i_k, i_d, i_v):
            raise SchemaDrift(f"{PIPELINE_NAME}: row {n} has {len(r)} fields")
        code = key_to_code(r[i_k])
        if code is None:
            raise SchemaDrift(f"{PIPELINE_NAME}: row {n} key {r[i_k]!r} not asked for")
        when = month_end(r[i_d])
        value = to_value(r[i_v], f"{code} {r[i_d]}")
        if value is not None:
            out.append((code, when, value))
    out.sort(key=lambda x: (x[1], x[0]))
    return out


def start_period(now: datetime, months: int) -> str:
    y, m = now.year, now.month - months
    while m <= 0:
        y, m = y - 1, m + 12
    return f"{y:04d}-{m:02d}"


def run_ecb_irs(db: Session, backfill: bool = False, **fetch_kw) -> dict:
    start = start_period(datetime.utcnow(), BACKFILL_MONTHS if backfill else DAILY_MONTHS)

    def produce():
        body = fetch_bytes(series_url(start), headers={"Accept": "text/csv"}, **fetch_kw)
        return parse_irs(body)

    return write_run(db, PIPELINE_NAME, METRICS, produce, BASE_URL)
