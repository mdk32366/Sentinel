"""Canada - Bank of Canada Valet benchmark bond yields (Sentinel D-0115).

Source (keyless, documented at https://www.bankofcanada.ca/valet/docs):

    https://www.bankofcanada.ca/valet/observations/group/bond_yields_benchmark/json

``recent=10`` for the daily run, ``start_date=YYYY-MM-DD`` for the five-year
backfill. Values arrive as strings (``{"v": "3.90"}``); a blank or absent cell
is skipped. The real-return bond (``BD.CDN.RRB.DQ.YLD``) is ignored.

Tenors 2, 3, 5, 7, 10 and LONG. LONG is the Bank's long benchmark (a bond of
roughly 30 years); it is stored as FB_CA_30Y and labelled "10s-long" in the
card tooltip (A-entry, D-0115). Display only, never scored.
"""
from __future__ import annotations

import json
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

PIPELINE_NAME = "BoC_Valet"
COUNTRY = "CA"
HOST = "www.bankofcanada.ca"
BASE_URL = f"https://{HOST}/valet/observations/group/bond_yields_benchmark/json"
TENORS = (2, 3, 5, 7, 10, 30)
SERIES = {
    "BD.CDN.2YR.DQ.YLD": 2,
    "BD.CDN.3YR.DQ.YLD": 3,
    "BD.CDN.5YR.DQ.YLD": 5,
    "BD.CDN.7YR.DQ.YLD": 7,
    "BD.CDN.10YR.DQ.YLD": 10,
    "BD.CDN.LONG.DQ.YLD": 30,  # LONG -> 30Y (A-entry, D-0115)
}
RECENT = 10
BACKFILL_DAYS = 1825

METRICS = make_metrics(
    COUNTRY, TENORS,
    "Canada {t}Y GoC benchmark bond yield (Bank of Canada)",
    "Bank of Canada",
    "Bank of Canada Valet group bond_yields_benchmark, {t}Y benchmark yield, "
    "business daily (30Y = the Bank's LONG benchmark). Display only, not "
    "scored (Sentinel D-0115).",
)


def series_url(start: str = None) -> str:
    if start:
        return f"{BASE_URL}?start_date={start}"
    return f"{BASE_URL}?recent={RECENT}"


def parse_boc(body: bytes) -> list:
    reject_html(body, PIPELINE_NAME)
    try:
        doc = json.loads(body.decode("utf-8-sig"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise SchemaDrift(f"{PIPELINE_NAME}: body is not JSON") from exc
    if not isinstance(doc, dict) or "observations" not in doc:
        raise SchemaDrift(f"{PIPELINE_NAME}: no 'observations' key")
    detail = doc.get("seriesDetail") or {}
    missing = [s for s in SERIES if detail and s not in detail]
    if missing:
        raise SchemaDrift(f"{PIPELINE_NAME}: seriesDetail lacks {missing}")
    obs = doc["observations"]
    if not obs:
        raise EmptyResponse(f"{PIPELINE_NAME}: 0 observations")
    out = []
    for o in obs:
        try:
            when = datetime.strptime(str(o.get("d", "")).strip(), "%Y-%m-%d")
        except ValueError as exc:
            raise SchemaDrift(f"{PIPELINE_NAME}: date {o.get('d')!r}") from exc
        for sid, tenor in SERIES.items():
            cell = o.get(sid)
            if not isinstance(cell, dict):
                continue
            code = code_for(COUNTRY, tenor)
            value = to_value(cell.get("v"), f"{code} {o.get('d')}")
            if value is not None:
                out.append((code, when, value))
    out.sort(key=lambda r: (r[1], r[0]))
    return out


def run_boc_valet(db: Session, backfill: bool = False, **fetch_kw) -> dict:
    start = None
    if backfill:
        start = (datetime.utcnow() - timedelta(days=BACKFILL_DAYS)).strftime("%Y-%m-%d")

    def produce():
        body = fetch_bytes(series_url(start), headers={"Accept": "application/json"}, **fetch_kw)
        return parse_boc(body)

    return write_run(db, PIPELINE_NAME, METRICS, produce, BASE_URL)
