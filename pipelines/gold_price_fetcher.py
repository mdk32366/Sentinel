"""Gold spot price from the LBMA daily fix.

Ruled on 2026-09-28 (ORDER-02 Part B / D-0041). The decision path, briefly,
because the obvious source is the wrong one:

  * FRED deleted every ICE Benchmark Administration series on 2022-01-31.
    `GOLDPMGBD228NLBM` returns "The series does not exist" (F-0043). Sources
    still citing it in 2026 are stale, and that was checked rather than
    assumed.
  * The World Bank Pink Sheet gold price is not exposed as a WDI indicator.
  * LBMA serves the fix directly, unauthenticated, daily.

The join is not a splice. The monthly mean of these fixes reproduces the
existing WGC CSV history to 0.00% across every month compared (F-0044) - they
are the same series, because WGC sources from ICE Benchmark Administration,
which administers this fix.

Modelled on treasury_direct.py: retries with backoff, a plausibility range, a
write window, and a truncated error field.
"""
import json
import logging
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation

from sqlalchemy.orm import Session

from database.models import Metric, TimeSeries, UpdateLog

logger = logging.getLogger(__name__)

PIPELINE_NAME = "Gold_Spot_Price"

SOURCE_URL = "https://prices.lbma.org.uk/json/gold_pm.json"

METRIC = {
    "code": "GOLD_SPOT_USD",
    "name": "Gold Spot Price (LBMA PM fix)",
    "category": "gold",
    "unit": "USD/oz",
    "source": "LBMA",
    "description": "LBMA Gold Price PM, USD per troy ounce",
}

# USD per troy ounce. Wide on purpose: this rejects a decimal-point error or a
# currency mix-up, not a market move. Gold has never been near either bound.
PLAUSIBLE_RANGE = (100.0, 20000.0)

# Do not rewrite history. The series carries years of WGC-sourced values and a
# backfill that silently replaced them would be unreviewable.
DEFAULT_WRITE_WINDOW_DAYS = 400

ERROR_FIELD_LIMIT = 480


def _truncate(text):
    if text and len(text) > ERROR_FIELD_LIMIT:
        return text[: ERROR_FIELD_LIMIT - 3] + "..."
    return text


def fetch_lbma_json(url: str = SOURCE_URL, attempts: int = 3,
                    backoff: float = 4.0) -> list:
    """Fetch the LBMA gold fix series, retrying transient failures.

    A 4xx other than 429 is not transient - the endpoint moved or is refusing
    us - and retrying it only delays the report.
    """
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            request = urllib.request.Request(
                url, headers={"User-Agent": "Sentinel/2.0 (sovereign stress monitor)"}
            )
            with urllib.request.urlopen(request, timeout=45) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if 400 <= exc.code < 500 and exc.code != 429:
                raise
            last_error = exc
        except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as exc:
            last_error = exc

        if attempt < attempts:
            wait = backoff * (2 ** (attempt - 1))
            logger.warning("LBMA attempt %d/%d failed (%s); retrying in %.0fs",
                           attempt, attempts, last_error, wait)
            time.sleep(wait)

    raise last_error


def parse_lbma_json(payload: list) -> list:
    """[{'date': datetime, 'usd': Decimal}, ...], oldest first.

    Entries look like {"d": "2026-09-25", "v": [usd, gbp, eur]}. Only USD is
    taken. A missing or implausible value is SKIPPED, never coerced to zero: a
    zero gold price is a plausible-looking number that would silently invert
    every divergence comparison downstream.
    """
    if not isinstance(payload, list):
        raise ValueError(f"LBMA payload was {type(payload).__name__}, expected list")

    out = []
    skipped = 0
    for entry in payload:
        if not isinstance(entry, dict):
            skipped += 1
            continue
        raw_date = entry.get("d")
        values = entry.get("v") or []
        if not raw_date or not values:
            skipped += 1
            continue
        try:
            when = datetime.strptime(str(raw_date)[:10], "%Y-%m-%d")
        except ValueError:
            skipped += 1
            continue
        if values[0] is None:
            skipped += 1
            continue
        try:
            usd = Decimal(str(values[0]))
        except (InvalidOperation, ValueError):
            skipped += 1
            continue
        if not (PLAUSIBLE_RANGE[0] <= float(usd) <= PLAUSIBLE_RANGE[1]):
            logger.warning("LBMA %s out of plausible range: %s", when.date(), usd)
            skipped += 1
            continue
        out.append({"date": when, "usd": usd})

    if not out:
        raise ValueError(
            f"LBMA payload yielded no usable rows ({skipped} skipped). "
            f"Refusing to report success."
        )

    out.sort(key=lambda row: row["date"])
    logger.info("LBMA: parsed %d rows, skipped %d", len(out), skipped)
    return out


def ensure_metric(db: Session) -> Metric:
    metric = db.query(Metric).filter_by(code=METRIC["code"]).first()
    if metric is None:
        metric = Metric(**METRIC)
        db.add(metric)
        db.commit()
        db.refresh(metric)
        logger.info("Created metric %s", METRIC["code"])
    return metric


def run_gold_price_fetch(db: Session,
                         write_window_days: int = DEFAULT_WRITE_WINDOW_DAYS) -> dict:
    """Fetch the LBMA fix and upsert recent observations."""
    started = datetime.utcnow()
    errors = []
    inserted = updated = 0
    latest_date = None

    try:
        rows = parse_lbma_json(fetch_lbma_json())
        cutoff = started - timedelta(days=write_window_days)
        metric = ensure_metric(db)

        for row in rows:
            if row["date"] < cutoff:
                continue
            existing = db.query(TimeSeries).filter(
                TimeSeries.metric_id == metric.id,
                TimeSeries.country_id == None,  # noqa: E711
                TimeSeries.date == row["date"],
            ).first()
            if existing:
                if Decimal(str(existing.value)) != row["usd"]:
                    existing.value = row["usd"]
                    existing.updated_at = datetime.utcnow()
                    updated += 1
            else:
                db.add(TimeSeries(
                    metric_id=metric.id,
                    country_id=None,
                    date=row["date"],
                    value=row["usd"],
                ))
                inserted += 1
            latest_date = row["date"] if latest_date is None else max(latest_date, row["date"])

        db.commit()
        status = "success"
    except Exception as exc:
        db.rollback()
        logger.error("Gold price fetch failed: %s", exc)
        errors.append(f"{METRIC['code']}: {exc}")
        status = "failed"

    db.add(UpdateLog(
        pipeline_name=PIPELINE_NAME,
        status=status,
        records_inserted=inserted,
        records_updated=updated,
        error_message=_truncate("; ".join(errors)) if errors else None,
        started_at=started,
        completed_at=datetime.utcnow(),
    ))
    db.commit()

    result = {
        "status": status,
        "inserted": inserted,
        "updated": updated,
        "errors": errors,
        "latest_date": latest_date.date().isoformat() if latest_date else None,
        "series": METRIC["code"],
    }
    if status == "failed":
        raise RuntimeError(f"Gold price fetch failed: {errors}")
    return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    from database.connection import get_session

    session = get_session()
    try:
        print(run_gold_price_fetch(session))
    finally:
        session.close()
