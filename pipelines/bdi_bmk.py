"""Italy - Banca d'Italia benchmark BTP yields, monthly (Sentinel D-0116).

Source (keyless Banca d'Italia Infostat A2A export, cube BMK0100):

    https://a2a.bancaditalia.it/infostat/dataservices/export/EN/CSV/DATA/CUBE/BANKITALIA/DIFF/BMK0100

The answer is a ZIP holding one ``;``-separated CSV. First header cell
``DATA_OSS`` (observation date, ``YYYY/MM/DD``); the four columns read are

    MFN_BMK.M.020.922.0.EUR.203  -> FB_IT_03Y
    MFN_BMK.M.020.922.0.EUR.205  -> FB_IT_05Y
    MFN_BMK.M.020.922.0.EUR.210  -> FB_IT_10Y
    MFN_BMK.M.020.922.0.EUR.230  -> FB_IT_30Y

Every other column is ignored. A blank cell ("") is missing, never zero. The
series is monthly (A-0036: most likely a monthly average, so nothing calls it
a month-end yield). Display only, never scored.

The same parser serves the manual backup, POST /api/ingest/bdi-mfn-bmk
(``ingest`` below), so an upload and the scheduled fetch can never disagree
about what a file means.
"""
from __future__ import annotations

import csv
import hashlib
import io
import logging
import zipfile
from datetime import datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy.orm import Session

from pipelines.foreign_bond_common import (
    EmptyResponse,
    SchemaDrift,
    fetch_bytes,
    make_metrics,
    reject_html,
    write_run,
)

logger = logging.getLogger(__name__)

PIPELINE_NAME = "BdI_BMK"
INGEST_SOURCE = "bdi-mfn-bmk"
HOST = "a2a.bancaditalia.it"
URL = f"https://{HOST}/infostat/dataservices/export/EN/CSV/DATA/CUBE/BANKITALIA/DIFF/BMK0100"
DATE_COLUMN = "DATA_OSS"
COLUMNS = {
    "MFN_BMK.M.020.922.0.EUR.203": 3,
    "MFN_BMK.M.020.922.0.EUR.205": 5,
    "MFN_BMK.M.020.922.0.EUR.210": 10,
    "MFN_BMK.M.020.922.0.EUR.230": 30,
}
TENORS = (3, 5, 10, 30)
VALUE_RANGE = (Decimal("-5"), Decimal("30"))
MAX_BODY_BYTES = 2 * 1024 * 1024
MAX_UNZIPPED_BYTES = 16 * 1024 * 1024
QUANT = Decimal("0.00000001")

METRICS = make_metrics(
    "IT", TENORS,
    "Italy {t}Y benchmark BTP yield, monthly (Banca d'Italia)",
    "Banca d'Italia",
    "Banca d'Italia BMK0100 MFN_BMK.M.020.922.0.EUR.2{t:02d}: yield of the "
    "{t}Y benchmark BTP, monthly (likely a monthly average, A-0036). "
    "Display only, not scored (Sentinel D-0116).",
)


class IngestRejected(ValueError):
    """The upload is not a BMK0100 export this parser accepts (-> HTTP 422)."""


def unwrap(body: bytes, where: str = PIPELINE_NAME) -> bytes:
    """ZIP with exactly one CSV -> its bytes; anything else is taken as CSV."""
    if body[:4] != b"PK\x03\x04":
        return body
    try:
        zf = zipfile.ZipFile(io.BytesIO(body))
    except zipfile.BadZipFile as exc:
        raise SchemaDrift(f"{where}: not a readable ZIP") from exc
    members = [i for i in zf.infolist() if not i.is_dir()]
    csvs = [i for i in members if i.filename.lower().endswith(".csv")]
    if len(members) != 1 or len(csvs) != 1:
        raise SchemaDrift(f"{where}: ZIP must hold exactly one CSV, holds {[i.filename for i in members]}")
    if csvs[0].file_size > MAX_UNZIPPED_BYTES:
        raise SchemaDrift(f"{where}: CSV inside the ZIP is {csvs[0].file_size} B, over the cap")
    return zf.read(csvs[0])


def _value(raw: str, where: str):
    text = raw.strip()
    if text == "":
        return None
    try:
        value = Decimal(text.replace(",", "."))
    except InvalidOperation as exc:
        raise SchemaDrift(f"{where}: value {text!r} is not a number") from exc
    if not value.is_finite() or not (VALUE_RANGE[0] <= value <= VALUE_RANGE[1]):
        raise SchemaDrift(f"{where}: value {text!r} outside [{VALUE_RANGE[0]}, {VALUE_RANGE[1]}] %")
    return value.quantize(QUANT)


def parse_bmk(body: bytes) -> list:
    """BMK0100 CSV (or the ZIP around it) -> [(code, datetime, Decimal)]."""
    reject_html(body, PIPELINE_NAME)
    raw = unwrap(body)
    reject_html(raw, PIPELINE_NAME)
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise SchemaDrift(f"{PIPELINE_NAME}: CSV is not UTF-8") from exc
    reader = csv.reader(io.StringIO(text), delimiter=";")
    header = next(reader, None)
    if not header:
        raise EmptyResponse(f"{PIPELINE_NAME}: empty body")
    header = [h.strip() for h in header]
    if header[0] != DATE_COLUMN:
        raise SchemaDrift(f"{PIPELINE_NAME}: first header cell is {header[0]!r}, not {DATE_COLUMN}")
    daily = [h for h in header if h.startswith("MFN_BMK.D.") or ".D." in h]
    if daily:
        raise SchemaDrift(f"{PIPELINE_NAME}: daily keys are not accepted: {daily}")
    missing = [c for c in COLUMNS if c not in header]
    if missing:
        raise SchemaDrift(f"{PIPELINE_NAME}: header lacks {missing}")
    idx = {header.index(c): f"FB_IT_{t:02d}Y" for c, t in COLUMNS.items()}
    out = []
    n_rows = 0
    for n, r in enumerate(reader, start=2):
        if not any(c.strip() for c in r):
            continue
        n_rows += 1
        if len(r) < len(header):
            raise SchemaDrift(f"{PIPELINE_NAME}: row {n} has {len(r)} fields, header has {len(header)}")
        try:
            when = datetime.strptime(r[0].strip(), "%Y/%m/%d")
        except ValueError as exc:
            raise SchemaDrift(f"{PIPELINE_NAME}: row {n} date {r[0]!r} is not YYYY/MM/DD") from exc
        for i, code in idx.items():
            value = _value(r[i], f"{code} {r[0]}")
            if value is not None:
                out.append((code, when, value))
    if not n_rows:
        raise EmptyResponse(f"{PIPELINE_NAME}: header only, 0 observations")
    out.sort(key=lambda x: (x[1], x[0]))
    return out


def run_bdi_bmk(db: Session, backfill: bool = False, **fetch_kw) -> dict:
    """The whole cube is one small file, so a run always reads all of it."""

    def produce():
        body = fetch_bytes(URL, headers={"Accept": "application/zip, text/csv"}, **fetch_kw)
        if len(body) > MAX_BODY_BYTES:
            raise SchemaDrift(f"{PIPELINE_NAME}: body is {len(body)} B, over the {MAX_BODY_BYTES} B cap")
        return parse_bmk(body)

    return write_run(db, PIPELINE_NAME, METRICS, produce, URL)


def ingest(db: Session, body: bytes, uploader: str) -> dict:
    """Manual backup (POST /api/ingest/bdi-mfn-bmk). All or nothing.

    Raises IngestRejected (HTTP 422, 0 rows written) on any violation.
    Idempotent: a second identical upload changes nothing and reports every
    row unchanged. One ingest_provenance row per accepted upload.
    """
    from database.models import IngestProvenance, Metric, TimeSeries
    from pipelines.fred_fetcher import ensure_metric, upsert_observations

    if len(body) > MAX_BODY_BYTES:
        raise IngestRejected(f"upload is {len(body)} B, over the {MAX_BODY_BYTES} B cap")
    try:
        rows = parse_bmk(body)
    except (SchemaDrift, EmptyResponse) as exc:
        raise IngestRejected(str(exc)) from exc
    if not rows:
        raise IngestRejected("no observations")
    try:
        ids = {m["code"]: ensure_metric(db, m).id for m in METRICS}
        inserted = updated = unchanged = 0
        for code, metric_id in ids.items():
            points = [(w, v) for c, w, v in rows if c == code]
            if not points:
                continue
            have = {
                (d.date() if hasattr(d, "date") else d): Decimal(str(v))
                for d, v in db.query(TimeSeries.date, TimeSeries.value)
                .filter(TimeSeries.metric_id == metric_id, TimeSeries.country_id.is_(None))
                .all()
            }
            changed = []
            for when, value in points:
                old = have.get(when.date())
                if old is not None and old.quantize(QUANT) == value:
                    unchanged += 1
                else:
                    changed.append((when, value))
            if changed:
                i, u = upsert_observations(db, metric_id, changed)
                inserted += i
                updated += u
        dates = [w for _, w, _ in rows]
        db.add(IngestProvenance(
            source=INGEST_SOURCE,
            uploaded_at=datetime.utcnow(),
            uploader=(uploader or "unknown")[:100],
            sha256=hashlib.sha256(body).hexdigest(),
            rows_inserted=inserted,
            rows_updated=updated,
            rows_unchanged=unchanged,
            min_date=min(dates),
            max_date=max(dates),
        ))
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {
        "status": "success",
        "inserted": inserted,
        "updated": updated,
        "unchanged": unchanged,
        "min_date": min(dates).date().isoformat(),
        "max_date": max(dates).date().isoformat(),
    }
