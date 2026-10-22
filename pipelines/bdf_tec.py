"""France - Banque de France TEC constant-maturity OAT yields (Sentinel D-0112).

Replaces D-0111 option A's four NO SOURCE cells with a daily official source.

Source: Banque de France Webstat API (Opendatasoft "explore v2.1"), documented
in the Bank's own guide, read 2026-10-22:

    https://webstat.banque-france.fr/pages/guide-migration-api/?flg=fr-fr

What this module relies on, each from that guide:
  - endpoint  https://webstat.banque-france.fr/api/explore/v2.1/catalog/
              datasets/observations/exports/csv   ("Exports EXCEL": replace
              ``json`` with ``csv`` in the URL)
  - auth      HTTP header ``Authorization: Apikey <key>`` ("Authentification",
              the recommended form; the ``apikey=`` URL parameter is for
              testing only and is never used here)
  - filter    ``where=series_key in ("k1","k2",..)`` (Exemple 3 remarks) and
              ``time_period_start>=date'YYYY-MM-DD'`` (Exemple 1 remarks)
  - fields    ``series_key``, ``time_period_start`` (ISO YYYY-MM-DD) and
              ``obs_value`` (may be null) (Exemple 1, JSON schema)
  - bad key   an absent or unknown key answers 404 ``NotFoundResource`` /
              "The requested dataset observations does not exist."

Measured, not in the guide (F-0118, 2026-10-22 16:06 UTC): with no key the
endpoint does answer that 404, but a key it does not recognise, sent in the
documented header, answers 401 ``{"error": "API key is not valid"}``. Both
are treated as a rejected key.

Series: FM.D.FR.EUR.FR2.BB.FRMOYTEC{2,5,7,10,30}.HSTA - TEC N, "taux de
l'echeance constante": the yield of a notional OAT of exactly N years,
interpolated from the two benchmark OATs around it. Type CMT, like MOF Japan.

The key comes from WEBSTAT_API_KEY (``settings.webstat_api_key``). Missing, the
run logs a warning and is skipped: no request, nothing written. It never
raises, so the scheduler is never taken down by a missing secret.

Fail closed, all or nothing (as ``foreign_bond_common``): the 404 or 401
above fails at once with WEBSTAT_API_KEY named; a 200 with only the header is retried and
then ``failed``; a series missing from the answer, or one not asked for, or a
renamed column is ``SchemaDrift``. The key never reaches a log or UpdateLog:
it travels only in the header.
"""
from __future__ import annotations

import csv
import io
import logging
from datetime import datetime, timedelta
from urllib.parse import quote, urlencode

from sqlalchemy.orm import Session

from config import settings
from pipelines.fetch_failure import ClassifiedFetchError
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

PIPELINE_NAME = "BdF_TEC"
HOST = "webstat.banque-france.fr"
GUIDE_URL = "https://webstat.banque-france.fr/pages/guide-migration-api/?flg=fr-fr"
BASE_URL = f"https://{HOST}/api/explore/v2.1/catalog/datasets/observations/exports/csv"
SERIES_KEY = "FM.D.FR.EUR.FR2.BB.FRMOYTEC{n}.HSTA"
DAILY_DAYS = 14       # two weeks: covers the Bundesbank pattern's last-10 window
BACKFILL_DAYS = 1825  # five years, like the other Foreign Bonds sources

REQUIRED_COLUMNS = ("series_key", "time_period_start", "obs_value")
SERIES_BY_TENOR = {t: SERIES_KEY.format(n=t) for t in TENORS}
TENOR_BY_SERIES = {v: k for k, v in SERIES_BY_TENOR.items()}


class WebstatKeyRejected(ValueError):
    """Webstat refused the key: the guide's 404, or the measured 401."""


KEY_REJECTED = {
    404: "404 'dataset observations does not exist' - the guide's answer to an "
         "absent or unknown key; check WEBSTAT_API_KEY",
    401: "401 'API key is not valid' - check WEBSTAT_API_KEY",
}


METRICS = [
    {
        "code": code_for("FR", t),
        "name": f"France {t}Y OAT yield (Banque de France TEC)",
        "category": CATEGORY,
        "unit": "%",
        "source": "Banque de France",
        "description": (
            f"CMT. TEC {t}: constant-maturity OAT yield at {t}Y, business-daily. "
            f"Banque de France Webstat {SERIES_BY_TENOR[t]}. Display only, not "
            f"scored (Sentinel D-0112)."
        ),
    }
    for t in TENORS
]


def series_url(start: str) -> str:
    keys = ",".join(f'"{SERIES_BY_TENOR[t]}"' for t in TENORS)
    query = {
        "select": "series_key,time_period,time_period_start,obs_value",
        "where": f"series_key in ({keys}) and time_period_start>=date'{start}'",
        "order_by": "time_period_start",
    }
    return f"{BASE_URL}?{urlencode(query, quote_via=quote)}"


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


def parse_bdf_tec(body: bytes) -> list:
    """CSV bytes for the five series -> [(code, datetime, Decimal)], oldest first."""
    try:
        header, rows = _rows(body)
    except UnicodeDecodeError as exc:
        raise SchemaDrift(f"{PIPELINE_NAME}: body is not UTF-8") from exc
    if header is None:
        raise SchemaDrift(f"{PIPELINE_NAME}: empty body")
    header = [h.strip() for h in header]
    missing = [c for c in REQUIRED_COLUMNS if c not in header]
    if missing:
        raise SchemaDrift(f"{PIPELINE_NAME}: header lacks {missing}")
    if not rows:
        raise EmptyResponse(f"{PIPELINE_NAME}: header only, 0 observations")
    i_key = header.index("series_key")
    i_date = header.index("time_period_start")
    i_val = header.index("obs_value")

    out = []
    seen = set()
    for n, row in enumerate(rows, start=2):
        if len(row) <= max(i_key, i_date, i_val):
            raise SchemaDrift(f"{PIPELINE_NAME}: row {n} has {len(row)} fields")
        key = row[i_key].strip()
        tenor = TENOR_BY_SERIES.get(key)
        if tenor is None:
            raise SchemaDrift(f"{PIPELINE_NAME}: row {n} is series {key!r}, not asked for")
        seen.add(tenor)
        code = code_for("FR", tenor)
        try:
            when = datetime.strptime(row[i_date].strip(), "%Y-%m-%d")
        except ValueError as exc:
            raise SchemaDrift(f"{code}: row {n} date {row[i_date]!r}") from exc
        value = to_value(row[i_val], f"{code} {row[i_date]}")
        if value is None:
            continue
        out.append((code, when, value))
    absent = [SERIES_BY_TENOR[t] for t in TENORS if t not in seen]
    if absent:
        raise SchemaDrift(f"{PIPELINE_NAME}: no observation for {absent}")
    out.sort(key=lambda r: (r[1], r[0]))
    return out


def fetch_bdf_tec(api_key: str, start: str, **kw) -> bytes:
    url = series_url(start)
    try:
        return fetch_bytes(
            url,
            headers={"Authorization": f"Apikey {api_key}", "Accept": "text/csv"},
            is_empty=is_header_only,
            **kw,
        )
    except ClassifiedFetchError as exc:
        hint = KEY_REJECTED.get(exc.failure.http_status)
        if hint:
            raise ClassifiedFetchError(exc.failure, WebstatKeyRejected(hint)) from exc
        raise


def run_bdf_tec(db: Session, backfill: bool = False, api_key: str = None, **fetch_kw) -> dict:
    """All five tenors in one request, or nothing. ``backfill`` reads five years.

    No key: logged and skipped (status ``skipped``), no request, no write.
    """
    key = api_key if api_key is not None else settings.webstat_api_key
    key = (key or "").strip()
    if not key:
        logger.warning(
            "%s skipped: WEBSTAT_API_KEY is not set; French TEC yields not fetched "
            "(FR 10Y shows the monthly FRED/OECD fallback)", PIPELINE_NAME,
        )
        return {"status": "skipped", "inserted": 0, "updated": 0,
                "errors": [], "latest_date": None}

    days = BACKFILL_DAYS if backfill else DAILY_DAYS
    start = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")

    def produce():
        return parse_bdf_tec(fetch_bdf_tec(key, start, **fetch_kw))

    return write_run(db, PIPELINE_NAME, METRICS, produce, BASE_URL)


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO)
    from database.connection import get_session

    session = get_session()
    try:
        print(run_bdf_tec(session, backfill="--backfill" in sys.argv))
    finally:
        session.close()
