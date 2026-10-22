"""Euro area - ECB yield curves, AAA and all-issuer Svensson spot rates (Sentinel D-0115).

Source (keyless ECB Data Portal SDMX REST, https://data.ecb.europa.eu/help/api):

    https://data-api.ecb.europa.eu/service/data/YC/B.U2.EUR.4F.G_N_A+G_N_C.SV_C_YM.SR_2Y+SR_5Y+SR_7Y+SR_10Y+SR_30Y?format=csvdata&startPeriod=YYYY-MM-DD

One request, ten series: G_N_A (AAA-rated issuers) and G_N_C (all euro-area
central government issuers) at 2, 5, 7, 10 and 30Y ->
FB_EA_AAA_{02,05,07,10,30}Y and FB_EA_ALL_{02,05,07,10,30}Y.

The ECB fits these with a Svensson model; the reuse licence was not verified
(A-entry, D-0115), so the panel cites "Source: ECB" and nothing is scored.
EA is a benchmark panel on the Foreign Bonds tab only: never a country, never
in the 41-country list, never in the composite (T-0131).
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

PIPELINE_NAME = "ECB_YC"
HOST = "data-api.ecb.europa.eu"
BASE_URL = (
    f"https://{HOST}/service/data/YC/"
    "B.U2.EUR.4F.G_N_A+G_N_C.SV_C_YM.SR_2Y+SR_5Y+SR_7Y+SR_10Y+SR_30Y"
)
TENORS = (2, 5, 7, 10, 30)
CURVES = {"G_N_A": "EA_AAA", "G_N_C": "EA_ALL"}
REQUIRED_COLUMNS = ("KEY", "TIME_PERIOD", "OBS_VALUE")
DAILY_DAYS = 14
BACKFILL_DAYS = 1825

METRICS = (
    make_metrics(
        "EA_AAA", TENORS,
        "Euro area AAA {t}Y spot rate (ECB yield curve)",
        "ECB",
        "ECB yield curve YC B.U2.EUR.4F.G_N_A.SV_C_YM.SR_{t}Y: Svensson spot "
        "rate, AAA-rated euro-area central government bonds, {t}Y, daily. "
        "Benchmark panel only, not a country, not scored (Sentinel D-0115).",
    )
    + make_metrics(
        "EA_ALL", TENORS,
        "Euro area all-issuer {t}Y spot rate (ECB yield curve)",
        "ECB",
        "ECB yield curve YC B.U2.EUR.4F.G_N_C.SV_C_YM.SR_{t}Y: Svensson spot "
        "rate, all euro-area central government bonds, {t}Y, daily. "
        "Benchmark panel only, not a country, not scored (Sentinel D-0115).",
    )
)


def series_url(start: str) -> str:
    return f"{BASE_URL}?format=csvdata&startPeriod={start}"


def key_to_code(key: str):
    # YC.B.U2.EUR.4F.G_N_A.SV_C_YM.SR_10Y
    parts = key.strip().split(".")
    if len(parts) != 8 or parts[0] != "YC":
        return None
    curve = CURVES.get(parts[5])
    mat = parts[7]
    if curve is None or not mat.startswith("SR_") or not mat.endswith("Y"):
        return None
    try:
        tenor = int(mat[3:-1])
    except ValueError:
        return None
    if tenor not in TENORS:
        return None
    return code_for(curve, tenor)


def parse_ecb(body: bytes) -> list:
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
        try:
            when = datetime.strptime(r[i_d].strip(), "%Y-%m-%d")
        except ValueError as exc:
            raise SchemaDrift(f"{PIPELINE_NAME}: row {n} date {r[i_d]!r}") from exc
        value = to_value(r[i_v], f"{code} {r[i_d]}")
        if value is not None:
            out.append((code, when, value))
    out.sort(key=lambda x: (x[1], x[0]))
    return out


def run_ecb_yc(db: Session, backfill: bool = False, **fetch_kw) -> dict:
    days = BACKFILL_DAYS if backfill else DAILY_DAYS
    start = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")

    def produce():
        body = fetch_bytes(series_url(start), headers={"Accept": "text/csv"}, **fetch_kw)
        return parse_ecb(body)

    return write_run(db, PIPELINE_NAME, METRICS, produce, BASE_URL)
