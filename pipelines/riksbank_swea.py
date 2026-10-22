"""Sweden - Riksbank SWEA government bond yields (Sentinel D-0115).

Source (keyless, https://developer.api.riksbank.se, SWEA API v1):

    https://api.riksbank.se/swea/v1/Observations/{seriesId}/{from}/{to}

One call per series, four series (<= 5 calls a run): SEGVB2YC, SEGVB5YC,
SEGVB7YC, SEGVB10YC -> FB_SE_{02,05,07,10}Y. The answer is a JSON list of
``{"date": "YYYY-MM-DD", "value": 3.183}``.

The keyless tier is rate limited. A 429 stops the run at once: no retry, no
further series, status ``failed`` (no retry storm). Display only.
"""
from __future__ import annotations

import json
import logging
import urllib.error
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from pipelines.fetch_failure import ClassifiedFetchError, classify_fetch_error
from pipelines.foreign_bond_common import (
    EmptyResponse,
    SchemaDrift,
    _urlopen,
    code_for,
    fetch_bytes,
    make_metrics,
    reject_html,
    to_value,
    write_run,
)

logger = logging.getLogger(__name__)

PIPELINE_NAME = "Riksbank_SWEA"
COUNTRY = "SE"
HOST = "api.riksbank.se"
BASE_URL = f"https://{HOST}/swea/v1/Observations"
TENORS = (2, 5, 7, 10)
SERIES = {2: "SEGVB2YC", 5: "SEGVB5YC", 7: "SEGVB7YC", 10: "SEGVB10YC"}
DAILY_DAYS = 14
BACKFILL_DAYS = 1825

METRICS = make_metrics(
    COUNTRY, TENORS,
    "Sweden {t}Y government bond yield (Riksbank)",
    "Riksbank",
    "Riksbank SWEA series SEGVB{t}YC, Swedish government bond {t}Y yield, "
    "daily. Display only, not scored (Sentinel D-0115).",
)


def series_url(tenor: int, start: str, end: str) -> str:
    return f"{BASE_URL}/{SERIES[tenor]}/{start}/{end}"


def parse_riksbank(body: bytes, tenor: int) -> list:
    code = code_for(COUNTRY, tenor)
    reject_html(body, code)
    try:
        doc = json.loads(body.decode("utf-8-sig"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise SchemaDrift(f"{code}: body is not JSON") from exc
    if not isinstance(doc, list):
        raise SchemaDrift(f"{code}: expected a JSON list")
    if not doc:
        raise EmptyResponse(f"{code}: 0 observations")
    out = []
    for o in doc:
        if not isinstance(o, dict) or "date" not in o or "value" not in o:
            raise SchemaDrift(f"{code}: observation lacks date/value")
        try:
            when = datetime.strptime(str(o["date"]).strip()[:10], "%Y-%m-%d")
        except ValueError as exc:
            raise SchemaDrift(f"{code}: date {o['date']!r}") from exc
        value = to_value(o["value"], f"{code} {o['date']}")
        if value is not None:
            out.append((code, when, value))
    out.sort(key=lambda r: r[1])
    return out


def _no_retry_on_429(opener):
    """Wrap the opener: a 429 is raised already classified, which
    ``fetch_bytes`` re-raises at once instead of retrying."""
    inner = opener or _urlopen

    def call(url, headers=None):
        try:
            return inner(url, headers)
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                raise ClassifiedFetchError(classify_fetch_error(exc, url=url), exc) from exc
            raise

    return call


def run_riksbank_swea(db: Session, backfill: bool = False, opener=None, **fetch_kw) -> dict:
    today = datetime.utcnow()
    days = BACKFILL_DAYS if backfill else DAILY_DAYS
    start = (today - timedelta(days=days)).strftime("%Y-%m-%d")
    end = today.strftime("%Y-%m-%d")
    guarded = _no_retry_on_429(opener)

    def produce():
        rows = []
        for tenor in TENORS:
            body = fetch_bytes(series_url(tenor, start, end),
                               headers={"Accept": "application/json"},
                               opener=guarded, **fetch_kw)
            rows.extend(parse_riksbank(body, tenor))
        return rows

    return write_run(db, PIPELINE_NAME, METRICS, produce, BASE_URL)
