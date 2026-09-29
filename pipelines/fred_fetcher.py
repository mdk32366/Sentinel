"""
FRED Data Pipeline
------------------
Fetches economic time series from the Federal Reserve Economic Data API.
Runs daily at 2am via scheduler.
"""

import re
import time

import requests
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from sqlalchemy import and_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session
from database.models import Metric, TimeSeries, UpdateLog
from config import settings

logger = logging.getLogger(__name__)

FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"

FRED_METRICS = [
    {"code": "DGS30",             "name": "30-Year Treasury Yield",         "category": "treasury",   "unit": "%", "source": "FRED",          "description": "Market yield on US Treasury securities at 30-year constant maturity"},
    {"code": "DGS10",             "name": "10-Year Treasury Yield",         "category": "treasury",   "unit": "%", "source": "FRED",          "description": "Market yield on US Treasury securities at 10-year constant maturity"},
    {"code": "DGS7",              "name": "7-Year Treasury Yield",          "category": "treasury",   "unit": "%", "source": "FRED",          "description": "Market yield on US Treasury securities at 7-year constant maturity"},
    {"code": "DGS5",              "name": "5-Year Treasury Yield",          "category": "treasury",   "unit": "%", "source": "FRED",          "description": "Market yield on US Treasury securities at 5-year constant maturity"},
    {"code": "DGS2",              "name": "2-Year Treasury Yield",          "category": "treasury",   "unit": "%", "source": "FRED",          "description": "Market yield on US Treasury securities at 2-year constant maturity"},
    # D-0057: DFF is the DAILY effective rate and is what the UI shows.
    # FEDFUNDS is the MONTHLY AVERAGE of the same quantity - kept because it
    # is what most published analysis quotes, and because five years of
    # history should not be discarded to fix a display choice.
    {"code": "DFF",               "name": "Federal Funds Rate (Daily)",     "category": "monetary",   "unit": "%", "source": "FRED",          "description": "Effective federal funds rate, daily"},
    {"code": "FEDFUNDS",          "name": "Federal Funds Rate (Monthly Avg)", "category": "monetary", "unit": "%", "source": "FRED",          "description": "Effective federal funds rate, monthly average"},
    {"code": "DFII10",            "name": "10-Year Real Yield (TIPS)",      "category": "treasury",   "unit": "%", "source": "FRED",          "description": "Market yield on US Treasury inflation-indexed securities at 10-year constant maturity"},
    {"code": "DCOILWTICO",        "name": "WTI Crude Oil Price",            "category": "commodity",  "unit": "$/bbl", "source": "FRED",      "description": "Crude oil prices: West Texas Intermediate (WTI)"},
    {"code": "DTWEXBGS",          "name": "US Dollar Index",                "category": "fx",         "unit": "index", "source": "FRED",      "description": "Nominal broad US dollar index"},
    {"code": "CPIAUCSL",          "name": "Consumer Price Index (CPI)",     "category": "inflation",  "unit": "index", "source": "FRED",      "description": "Consumer price index for all urban consumers: all items"},
    # D-0058: WM2NS is the WEEKLY M2 series and is what the UI shows. Both
    # come from the same H.6 release and FRED stamps them with the same
    # last_updated, so this buys granularity and a newer data point - not a
    # newer release. M2SL is kept: it is seasonally adjusted and it is the
    # series published analysis quotes.
    {"code": "WM2NS",             "name": "M2 Money Supply (Weekly)",       "category": "monetary",   "unit": "billions", "source": "FRED",   "description": "M2 money stock, weekly, not seasonally adjusted"},
    {"code": "M2SL",              "name": "M2 Money Supply (Monthly, SA)",  "category": "monetary",   "unit": "billions", "source": "FRED",   "description": "M2 money stock, monthly, seasonally adjusted"},
    {"code": "IRLTLT01JPM156N", "name": "Japan 10Y Gov Bond Yield",    "category": "sovereign_yield", "unit": "%", "source": "FRED", "description": "Japan 10-year government bond yield, monthly (OECD)"},
    {"code": "IRLTLT01DEM156N", "name": "Germany 10Y Gov Bond Yield",  "category": "sovereign_yield", "unit": "%", "source": "FRED", "description": "Germany 10-year government bond yield, monthly (OECD)"},
    {"code": "IRLTLT01ITM156N", "name": "Italy 10Y Gov Bond Yield",    "category": "sovereign_yield", "unit": "%", "source": "FRED", "description": "Italy 10-year government bond yield, monthly (OECD)"},
    {"code": "IRLTLT01FRM156N", "name": "France 10Y Gov Bond Yield",   "category": "sovereign_yield", "unit": "%", "source": "FRED", "description": "France 10-year government bond yield, monthly (OECD)"},
    {"code": "IRLTLT01ESM156N", "name": "Spain 10Y Gov Bond Yield",    "category": "sovereign_yield", "unit": "%", "source": "FRED", "description": "Spain 10-year government bond yield, monthly (OECD)"},
    {"code": "IRLTLT01GBM156N", "name": "UK 10Y Gov Bond Yield",       "category": "sovereign_yield", "unit": "%", "source": "FRED", "description": "UK 10-year government bond yield, monthly (OECD)"},
    {"code": "IRLTLT01AUM156N", "name": "Australia 10Y Gov Bond Yield","category": "sovereign_yield", "unit": "%", "source": "FRED", "description": "Australia 10-year government bond yield, monthly (OECD)"},
    {"code": "IRLTLT01CAM156N", "name": "Canada 10Y Gov Bond Yield",   "category": "sovereign_yield", "unit": "%", "source": "FRED", "description": "Canada 10-year government bond yield, monthly (OECD)"},
    {"code": "IRLTLT01NLM156N", "name": "Netherlands 10Y Gov Bond Yield", "category": "sovereign_yield", "unit": "%", "source": "FRED", "description": "Netherlands 10-year government bond yield, monthly (OECD)"},
    {"code": "IRLTLT01NOM156N", "name": "Norway 10Y Gov Bond Yield",      "category": "sovereign_yield", "unit": "%", "source": "FRED", "description": "Norway 10-year government bond yield, monthly (OECD)"},
    {"code": "IRLTLT01SEM156N", "name": "Sweden 10Y Gov Bond Yield",      "category": "sovereign_yield", "unit": "%", "source": "FRED", "description": "Sweden 10-year government bond yield, monthly (OECD)"},
    {"code": "IRLTLT01CHM156N", "name": "Switzerland 10Y Gov Bond Yield", "category": "sovereign_yield", "unit": "%", "source": "FRED", "description": "Switzerland 10-year government bond yield, monthly (OECD)"},
    {"code": "IRLTLT01BEM156N", "name": "Belgium 10Y Gov Bond Yield",     "category": "sovereign_yield", "unit": "%", "source": "FRED", "description": "Belgium 10-year government bond yield, monthly (OECD)"},
    {"code": "IRLTLT01KRM156N", "name": "South Korea 10Y Gov Bond Yield", "category": "sovereign_yield", "unit": "%", "source": "FRED", "description": "South Korea 10-year government bond yield, monthly (OECD)"},
    {"code": "DCOILBRENTEU", "name": "Brent Crude Oil Price", "category": "commodity", "unit": "$/bbl", "source": "FRED", "description": "Crude Oil Prices: Brent - Europe, dollars per barrel, daily"},
    # ── Total Reserves Excluding Gold (IMF IFS via FRED) ──────────────────────
    # Units: Millions of USD, Monthly. Tracks de-dollarization / reserve accumulation.
    {"code": "TRESEGCNM052N", "name": "China Total Reserves ex-Gold",        "category": "reserves", "unit": "millions_usd", "source": "IMF_IFS", "description": "China total reserves excluding gold (millions USD, IMF IFS)"},
    {"code": "TRESEGJPM052N", "name": "Japan Total Reserves ex-Gold",         "category": "reserves", "unit": "millions_usd", "source": "IMF_IFS", "description": "Japan total reserves excluding gold (millions USD, IMF IFS)"},
    {"code": "TRESEGRUM052N", "name": "Russia Total Reserves ex-Gold",        "category": "reserves", "unit": "millions_usd", "source": "IMF_IFS", "description": "Russia total reserves excluding gold (millions USD, IMF IFS)"},
    {"code": "TRESEGINM052N", "name": "India Total Reserves ex-Gold",         "category": "reserves", "unit": "millions_usd", "source": "IMF_IFS", "description": "India total reserves excluding gold (millions USD, IMF IFS)"},
    {"code": "TRESEGTRM052N", "name": "Turkey Total Reserves ex-Gold",        "category": "reserves", "unit": "millions_usd", "source": "IMF_IFS", "description": "Turkey total reserves excluding gold (millions USD, IMF IFS)"},
    {"code": "TRESEGDEM052N", "name": "Germany Total Reserves ex-Gold",       "category": "reserves", "unit": "millions_usd", "source": "IMF_IFS", "description": "Germany total reserves excluding gold (millions USD, IMF IFS)"},
    {"code": "TRESEGFRM052N", "name": "France Total Reserves ex-Gold",        "category": "reserves", "unit": "millions_usd", "source": "IMF_IFS", "description": "France total reserves excluding gold (millions USD, IMF IFS)"},
    {"code": "TRESEGGBM052N", "name": "UK Total Reserves ex-Gold",            "category": "reserves", "unit": "millions_usd", "source": "IMF_IFS", "description": "UK total reserves excluding gold (millions USD, IMF IFS)"},
    {"code": "TRESEGSAM052N", "name": "Saudi Arabia Total Reserves ex-Gold",  "category": "reserves", "unit": "millions_usd", "source": "IMF_IFS", "description": "Saudi Arabia total reserves excluding gold (millions USD, IMF IFS)"},
    {"code": "TRESEGBRM052N", "name": "Brazil Total Reserves ex-Gold",        "category": "reserves", "unit": "millions_usd", "source": "IMF_IFS", "description": "Brazil total reserves excluding gold (millions USD, IMF IFS)"},
    {"code": "TRESEGUSM052N", "name": "US Total Reserves ex-Gold",            "category": "reserves", "unit": "millions_usd", "source": "IMF_IFS", "description": "US total reserves excluding gold (millions USD, IMF IFS)"},
    {"code": "TRESEGIDM052N", "name": "Indonesia Total Reserves ex-Gold",     "category": "reserves", "unit": "millions_usd", "source": "IMF_IFS", "description": "Indonesia total reserves excluding gold (millions USD, IMF IFS)"},
]


# F-0010: the key travels as a query parameter, so raise_for_status() embeds
# the full URL in the exception text, that text is written to
# update_logs.error_message, and /api/pipeline-logs serves the field over HTTP.
# Nothing here is hypothetical - five of ten sampled rows carried the live key.
_API_KEY_RE = re.compile(r"api_key=[0-9A-Za-z]+")

# A-0003: error_message is varchar(500). A multi-series failure overflows it,
# the UpdateLog insert itself throws, and the log row is lost entirely -
# destroying the diagnostic that produced every finding about this pipeline.
ERROR_FIELD_LIMIT = 480


def _redact(text: str) -> str:
    """Strip any API key from text bound for a log, a database or an HTTP body."""
    return _API_KEY_RE.sub("api_key=***", str(text))


def ensure_metric(db: Session, metric_data: dict) -> Metric:
    metric = db.query(Metric).filter_by(code=metric_data["code"]).first()
    if not metric:
        metric = Metric(**metric_data)
        db.add(metric)
        db.commit()
        logger.info(f"Created metric: {metric_data['code']}")
    return metric


def fetch_fred_series(series_id: str, start_date: str, end_date: str,
                      attempts: int = 3, backoff: float = 4.0) -> list:
    """Fetch observations from FRED, retrying transient failures.

    F-0003: FRED returns intermittent 502s that lose exactly one random series
    per run. Five of ten sampled runs were `partial` for that reason. The
    failures recovered on the next night, so they are transient and worth
    retrying rather than surfacing.

    A 4xx other than 429 is not transient - it is a bad request or a bad key,
    and retrying it three times only delays the report.
    """
    params = {
        "series_id": series_id,
        "api_key": settings.fred_api_key,
        "file_type": "json",
        "observation_start": start_date,
        "observation_end": end_date,
    }

    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            r = requests.get(FRED_BASE, params=params, timeout=30)
            if 400 <= r.status_code < 500 and r.status_code != 429:
                r.raise_for_status()
            r.raise_for_status()
            return r.json().get("observations", [])
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else None
            if status is not None and 400 <= status < 500 and status != 429:
                raise
            last_error = exc
        except requests.RequestException as exc:
            last_error = exc

        if attempt < attempts:
            wait = backoff * (2 ** (attempt - 1))
            logger.warning(
                "FRED %s attempt %d/%d failed (%s); retrying in %.0fs",
                series_id, attempt, attempts, _redact(last_error), wait,
            )
            time.sleep(wait)

    raise last_error


# Postgres caps a statement at 65535 bind parameters. Five columns per row
# leaves enormous headroom at this size; the chunking exists so a future daily
# series with a longer history cannot quietly cross it.
UPSERT_CHUNK = 1000


def upsert_observations(db: Session, metric_id: int, rows: list) -> tuple:
    """Write `rows` for one metric, replacing any that already exist.

    `rows` is a list of `(date, Decimal)`. Returns `(inserted, updated)`.

    F-0073. This used to be check-then-insert: SELECT for each observation,
    then INSERT or mutate. Two overlapping FRED runs - and every deploy starts
    one, on top of the nightly schedule - could both see "absent" and both
    insert. That produced 1,190 duplicate rows before anyone noticed, because
    the unique index was not enforcing anything for `country_id IS NULL`.

    On Postgres the write is now a single `ON CONFLICT DO UPDATE`, so the
    database decides, not a check that was true a moment ago. **This depends
    on the index created by F-0073**: `ON CONFLICT (metric_id, country_id,
    date)` can only arbitrate on a NULL `country_id` because that index is
    `NULLS NOT DISTINCT`. Without it Postgres would not match the conflict and
    would insert a duplicate exactly as before.

    Every other dialect keeps the old path. SQLite - which is what this
    suite's in-memory databases are - shares Postgres' NULL-distinct
    semantics, so an `ON CONFLICT` there would not arbitrate either and would
    silently be the thing it is meant to replace. Better one explicit branch
    than a fix that only appears to apply everywhere.
    """
    if not rows:
        return 0, 0

    # A revision can report the same date twice in one payload. Postgres
    # refuses to let ON CONFLICT DO UPDATE touch a row twice in a single
    # statement -- "cannot affect row a second time" -- so the batch has to be
    # unique before it is sent. Last value for a date wins, which is what the
    # per-observation loop did implicitly.
    #
    # This belongs here rather than in the caller: a helper that raises on
    # input its only caller happens never to send is a trap for the second
    # caller.
    deduped = {}
    for date, value in rows:
        deduped[date] = value
    rows = sorted(deduped.items())

    # Counted from what is already stored rather than from what the write
    # returned, so the two dialects report the same numbers.
    dates = [date for date, _ in rows]
    existing = set()
    for start in range(0, len(dates), UPSERT_CHUNK):
        chunk = dates[start:start + UPSERT_CHUNK]
        existing.update(
            row[0] for row in db.execute(
                select(TimeSeries.date).where(and_(
                    TimeSeries.metric_id == metric_id,
                    TimeSeries.country_id.is_(None),
                    TimeSeries.date.in_(chunk),
                ))
            ).all()
        )

    inserted = sum(1 for date, _ in rows if date not in existing)
    updated = len(rows) - inserted
    now = datetime.utcnow()

    if db.get_bind().dialect.name == "postgresql":
        payload = [
            {"metric_id": metric_id, "country_id": None, "date": date,
             "value": value, "created_at": now, "updated_at": now}
            for date, value in rows
        ]
        for start in range(0, len(payload), UPSERT_CHUNK):
            chunk = payload[start:start + UPSERT_CHUNK]
            stmt = pg_insert(TimeSeries.__table__).values(chunk)
            db.execute(stmt.on_conflict_do_update(
                index_elements=["metric_id", "country_id", "date"],
                set_={"value": stmt.excluded.value,
                      "updated_at": stmt.excluded.updated_at},
            ))
        return inserted, updated

    for date, value in rows:
        existing_row = db.query(TimeSeries).filter(
            TimeSeries.metric_id == metric_id,
            TimeSeries.date == date,
            TimeSeries.country_id.is_(None),
        ).first()
        if existing_row:
            existing_row.value = value
            existing_row.updated_at = now
        else:
            db.add(TimeSeries(metric_id=metric_id, country_id=None,
                              date=date, value=value))
    return inserted, updated


def run_fred_fetch(db: Session, days_back: int = 1825) -> dict:
    """Main FRED fetch pipeline. Fetches last 5 years by default."""
    start_time = datetime.utcnow()
    total_inserted = 0
    total_updated = 0
    errors = []

    end_date = datetime.utcnow().strftime("%Y-%m-%d")
    start_date = (datetime.utcnow() - timedelta(days=days_back)).strftime("%Y-%m-%d")

    for metric_data in FRED_METRICS:
        try:
            metric = ensure_metric(db, metric_data)
            observations = fetch_fred_series(metric_data["code"], start_date, end_date)

            rows = []
            for obs in observations:
                value_str = obs.get("value", ".")
                if value_str == ".":
                    continue
                try:
                    value = Decimal(value_str)
                    date = datetime.strptime(obs["date"], "%Y-%m-%d")
                except Exception:
                    continue
                rows.append((date, value))

            inserted, updated = upsert_observations(db, metric.id, rows)
            total_inserted += inserted
            total_updated += updated

            db.commit()
            logger.info(f"FRED {metric_data['code']}: fetched {len(observations)} observations")

        except Exception as e:
            logger.error("FRED fetch failed for %s: %s",
                         metric_data["code"], _redact(e))
            errors.append(_redact(f"{metric_data['code']}: {e}"))

        # Be a good citizen against a shared public API, and keep a run that
        # hits 37 series from looking like a burst.
        time.sleep(0.5)

    status = "success" if not errors else "partial"
    # Truncate BEFORE the insert. An over-long error_message makes the insert
    # itself throw, which loses the whole log row - the row that would have
    # told you what went wrong (A-0003).
    joined = "; ".join(errors) if errors else None
    if joined and len(joined) > ERROR_FIELD_LIMIT:
        joined = joined[:ERROR_FIELD_LIMIT - 3] + "..."
    db.add(UpdateLog(
        pipeline_name="FRED",
        status=status,
        records_inserted=total_inserted,
        records_updated=total_updated,
        error_message=joined,
        started_at=start_time,
        completed_at=datetime.utcnow(),
    ))
    db.commit()

    logger.info(f"FRED fetch complete: {total_inserted} inserted, {total_updated} updated")
    return {
        "status": status,
        "inserted": total_inserted,
        "updated": total_updated,
        "errors": errors,
    }

