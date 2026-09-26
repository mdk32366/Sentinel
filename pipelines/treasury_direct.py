"""
US Treasury Direct — Daily Par Yield Curve Rates
=================================================
Same-day source for the full Treasury constant-maturity curve.

WHY THIS EXISTS
    FRED's H.15 DGS* series publish with a one-business-day lag. Treasury
    publishes the same constant-maturity rates itself around 15:30 ET on the
    day they apply. This pipeline closes that gap and adds the tenors FRED
    coverage in Sentinel is missing (7Y, 20Y, 3Y, and the bill tenors).

RELATIONSHIP TO fred_fetcher
    Both write the SAME metric codes (DGS10, DGS7, ...). This is deliberate:
    FRED's DGS* series ARE the Treasury CMT rates, so the values are identical.
    Treasury gets there first; FRED overwrites with the authoritative revised
    value on its next nightly run. Last write wins and both agree, so the
    two pipelines are idempotent with respect to each other.

    Run this AFTER the FRED job in the daily order so that on any given day
    FRED owns history and Treasury owns only the leading edge.

SOURCE
    https://home.treasury.gov/resource-center/data-chart-center/interest-rates/
        TextView?type=daily_treasury_yield_curve

    CSV columns (as of 2026):
        Date,1 Mo,1.5 Mo,2 Mo,3 Mo,4 Mo,6 Mo,1 Yr,2 Yr,3 Yr,5 Yr,7 Yr,
        10 Yr,20 Yr,30 Yr

SAFETY RAILS
    - Only writes dates within TREASURY_MAX_BACKDATE_DAYS (default 10). A bad
      parse cannot rewrite history.
    - Rejects values outside PLAUSIBLE_RANGE.
    - Warns (does not block) when a value jumps more than MAX_JUMP_PP from the
      previously stored point — blocking would suppress a real crisis.
    - Retries transient 5xx/429 with exponential backoff.
    - Redacts nothing here (no API key in the URL), but truncates the log field
      so a wide failure cannot overflow update_logs.error_message varchar(500).

NO API KEY REQUIRED.
"""

import csv
import io
import logging
import os
import time
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation

import requests
from requests.exceptions import RequestException
from sqlalchemy.orm import Session

from database.models import Metric, TimeSeries, UpdateLog

logger = logging.getLogger(__name__)

PIPELINE_NAME = "TreasuryDirect"

BASE_URL = (
    "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
    "daily-treasury-rates.csv/{year}/all"
    "?type=daily_treasury_yield_curve&field_tdr_date_value={year}&page&_format=csv"
)

# Normalised CSV header -> (metric code, human name)
# Normalisation: lowercase, collapse whitespace.
# 1.5 Mo and 4 Mo are intentionally omitted: no standard FRED equivalent, and
# inventing a code would create a series only this pipeline maintains.
TENOR_MAP = {
    "1 mo":  ("DGS1MO", "1-Month Treasury Yield"),
    "3 mo":  ("DGS3MO", "3-Month Treasury Yield"),
    "6 mo":  ("DGS6MO", "6-Month Treasury Yield"),
    "1 yr":  ("DGS1",   "1-Year Treasury Yield"),
    "2 yr":  ("DGS2",   "2-Year Treasury Yield"),
    "3 yr":  ("DGS3",   "3-Year Treasury Yield"),
    "5 yr":  ("DGS5",   "5-Year Treasury Yield"),
    "7 yr":  ("DGS7",   "7-Year Treasury Yield"),
    "10 yr": ("DGS10",  "10-Year Treasury Yield"),
    "20 yr": ("DGS20",  "20-Year Treasury Yield"),
    "30 yr": ("DGS30",  "30-Year Treasury Yield"),
}

PLAUSIBLE_RANGE = (-2.0, 25.0)   # percent
MAX_JUMP_PP = 1.5                # percentage points vs previous stored point
ERROR_FIELD_LIMIT = 480          # update_logs.error_message is varchar(500)

USER_AGENT = os.getenv(
    "TREASURY_USER_AGENT",
    "Sentinel/2.0 (sovereign stress monitor; contact: admin)",
)


# ─────────────────────────────────────────────────────────────────────────────
# Fetch
# ─────────────────────────────────────────────────────────────────────────────

def fetch_curve_csv(year: int = None, retries: int = 3, backoff: float = 4.0) -> str:
    """Download the par yield curve CSV for a calendar year. Returns raw text."""
    year = year or datetime.utcnow().year
    url = BASE_URL.format(year=year)
    last_err = None

    for attempt in range(retries):
        try:
            r = requests.get(
                url,
                timeout=45,
                headers={"User-Agent": USER_AGENT, "Accept": "text/csv,*/*"},
            )
            r.raise_for_status()
            text = r.text
            if "Date" not in text[:200]:
                raise ValueError(
                    f"Response does not look like the expected CSV "
                    f"(first 120 chars: {text[:120]!r})"
                )
            return text
        except (RequestException, ValueError) as e:
            last_err = e
            code = getattr(getattr(e, "response", None), "status_code", None)
            if code is not None and code < 500 and code != 429:
                break
            if attempt < retries - 1:
                time.sleep(backoff * (2 ** attempt))

    raise RuntimeError(f"Treasury CSV fetch failed for {year}: {last_err}")


def _parse_date(raw: str):
    """Treasury has shipped both MM/DD/YYYY and YYYY-MM-DD. Accept either."""
    raw = (raw or "").strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None


def parse_curve_csv(text: str) -> list:
    """
    Parse the CSV into [{'date': datetime, 'rates': {code: Decimal}}, ...].
    Unknown columns are ignored, so Treasury adding a tenor will not break this.
    """
    reader = csv.reader(io.StringIO(text))
    rows = [r for r in reader if r and any(c.strip() for c in r)]
    if not rows:
        raise ValueError("Treasury CSV was empty")

    header = [c.strip().lower().replace("\ufeff", "") for c in rows[0]]
    header = [" ".join(c.split()) for c in header]

    col_index = {}
    for i, col in enumerate(header):
        if col in TENOR_MAP:
            col_index[i] = TENOR_MAP[col][0]

    if not col_index:
        raise ValueError(f"No recognised tenor columns in header: {header}")

    logger.info(
        "Treasury CSV: matched %d tenor columns (%s)",
        len(col_index), ", ".join(sorted(col_index.values())),
    )

    out = []
    for row in rows[1:]:
        if not row:
            continue
        dt = _parse_date(row[0])
        if dt is None:
            continue

        rates = {}
        for i, code in col_index.items():
            if i >= len(row):
                continue
            raw = row[i].strip().replace(",", "")
            if not raw or raw in {"N/A", "NA", "."}:
                continue
            try:
                val = Decimal(raw)
            except (InvalidOperation, ValueError):
                continue
            if not (PLAUSIBLE_RANGE[0] <= float(val) <= PLAUSIBLE_RANGE[1]):
                logger.warning(
                    "Treasury %s on %s out of plausible range: %s",
                    code, dt.date(), val,
                )
                continue
            rates[code] = val

        if rates:
            out.append({"date": dt, "rates": rates})

    return out


# ─────────────────────────────────────────────────────────────────────────────
# Persist
# ─────────────────────────────────────────────────────────────────────────────

def ensure_metric(db: Session, code: str, name: str) -> Metric:
    metric = db.query(Metric).filter_by(code=code).first()
    if not metric:
        metric = Metric(
            code=code,
            name=name,
            category="treasury",
            unit="%",
            source="US_TREASURY",
            description=(
                "Daily Treasury par yield curve rate (constant maturity), "
                "published same day by the US Department of the Treasury."
            ),
        )
        db.add(metric)
        db.commit()
        logger.info("Created metric: %s", code)
    return metric


def _previous_value(db: Session, metric_id: int, before_date: datetime):
    row = (
        db.query(TimeSeries.value)
        .filter(
            TimeSeries.metric_id == metric_id,
            TimeSeries.country_id.is_(None),
            TimeSeries.date < before_date,
        )
        .order_by(TimeSeries.date.desc())
        .first()
    )
    return row[0] if row else None


def run_treasury_direct_fetch(db: Session, year: int = None,
                              max_backdate_days: int = None) -> dict:
    """
    Main entry point. Signature matches the other pipelines: run_*_fetch(db).

    max_backdate_days: only write observations this recent. Defaults to
    TREASURY_MAX_BACKDATE_DAYS env var, else 10. Pass a large number (or
    set the env var) for a one-off backfill of the current year.
    """
    start_time = datetime.utcnow()
    if max_backdate_days is None:
        max_backdate_days = int(os.getenv("TREASURY_MAX_BACKDATE_DAYS", "10"))

    cutoff = datetime.utcnow() - timedelta(days=max_backdate_days)

    inserted = updated = skipped = 0
    anomalies = []
    errors = []
    latest_date = None

    try:
        text = fetch_curve_csv(year)
        records = parse_curve_csv(text)
    except Exception as e:
        msg = str(e)[:ERROR_FIELD_LIMIT]
        logger.error("Treasury Direct fetch failed: %s", msg)
        db.add(UpdateLog(
            pipeline_name=PIPELINE_NAME, status="failed",
            records_inserted=0, records_updated=0, error_message=msg,
            started_at=start_time, completed_at=datetime.utcnow(),
        ))
        db.commit()
        return {"status": "failed", "inserted": 0, "updated": 0,
                "skipped": 0, "errors": [msg], "latest_date": None}

    metric_cache = {}

    for rec in records:
        dt = rec["date"]
        if dt < cutoff:
            skipped += 1
            continue
        if latest_date is None or dt > latest_date:
            latest_date = dt

        for code, value in rec["rates"].items():
            try:
                if code not in metric_cache:
                    name = next(
                        (n for c, n in TENOR_MAP.values() if c == code), code
                    )
                    metric_cache[code] = ensure_metric(db, code, name)
                metric = metric_cache[code]

                existing = (
                    db.query(TimeSeries)
                    .filter(
                        TimeSeries.metric_id == metric.id,
                        TimeSeries.date == dt,
                        TimeSeries.country_id.is_(None),
                    )
                    .first()
                )

                if existing is None:
                    prev = _previous_value(db, metric.id, dt)
                    if prev is not None and abs(float(value) - float(prev)) > MAX_JUMP_PP:
                        anomalies.append(
                            f"{code} {dt.date()}: {prev} -> {value}"
                        )
                        logger.warning(
                            "Treasury %s on %s jumped %.2fpp (%s -> %s) — writing anyway",
                            code, dt.date(), abs(float(value) - float(prev)), prev, value,
                        )
                    db.add(TimeSeries(
                        metric_id=metric.id, country_id=None,
                        date=dt, value=value,
                    ))
                    inserted += 1
                elif existing.value != value:
                    existing.value = value
                    existing.updated_at = datetime.utcnow()
                    updated += 1

            except Exception as e:
                errors.append(f"{code} {dt.date()}: {e}")

        db.commit()

    status = "success" if not errors else "partial"
    parts = []
    if errors:
        parts.append("; ".join(errors))
    if anomalies:
        parts.append("ANOMALIES: " + "; ".join(anomalies))
    err_text = ("; ".join(parts))[:ERROR_FIELD_LIMIT] if parts else None

    db.add(UpdateLog(
        pipeline_name=PIPELINE_NAME, status=status,
        records_inserted=inserted, records_updated=updated,
        error_message=err_text,
        started_at=start_time, completed_at=datetime.utcnow(),
    ))
    db.commit()

    logger.info(
        "Treasury Direct: %d inserted, %d updated, %d out of window, latest=%s",
        inserted, updated, skipped,
        latest_date.date() if latest_date else "none",
    )

    return {
        "status": status,
        "inserted": inserted,
        "updated": updated,
        "skipped": skipped,
        "anomalies": anomalies,
        "errors": errors,
        "latest_date": latest_date.date().isoformat() if latest_date else None,
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    from database.connection import get_session

    db = get_session()
    try:
        # One-off: backfill the whole current year.
        print(run_treasury_direct_fetch(db, max_backdate_days=400))
    finally:
        db.close()
