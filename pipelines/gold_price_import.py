"""
Spot Gold Price CSV Importer
-----------------------------
Historical monthly gold price (USD/troy oz), World Gold Council file at
data/gold_prices.csv. Month-end dates are normalised to day 1 (D-0027).

This is not the GOLD_SPOT_USD update. D-0041 kept the file for seeding and
said spot no longer arrives this way. D-0094 writes that series from
gold-api.com (daily, dated by updatedAt) with the World Bank Pink Sheet as
the monthly fallback. F-0133: once the series has a non-day-1 observation,
or an incoming average disagrees with a stored value, this importer refuses
to write. That refusal is a write-guard, not a copyright ruling.
"""

import csv
import logging
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from sqlalchemy.orm import Session
from database.models import Metric, TimeSeries, UpdateLog
from pipelines.paths import DATA_DIR

logger = logging.getLogger(__name__)

CSV_PATH = DATA_DIR / "gold_prices.csv"

# D-0027: the WGC series is month-end, normalised to day=1 on write.
# On 2026-09-26 a fully current file is already 56 days old by that measure,
# and reaches ~65 just before the next publication. 70 is the first value that
# does not fire on healthy data. A present-but-frozen file is the failure that
# actually occurred; a missing-file check would never have caught it.
MAX_SOURCE_AGE_DAYS = 70

SPOT_GOLD_METRIC = {
    "code": "GOLD_SPOT_USD",
    "name": "Gold Spot Price (USD/troy oz)",
    "category": "commodity",
    "unit": "$/troy oz",
    "source": "WGC_ICE",
    "description": "Monthly gold price per troy ounce in USD (WGC/ICE Benchmark Administration)"
}


def ensure_spot_metric(db: Session) -> Metric:
    metric = db.query(Metric).filter_by(code=SPOT_GOLD_METRIC["code"]).first()
    if not metric:
        metric = Metric(**SPOT_GOLD_METRIC)
        db.add(metric)
        db.commit()
        logger.info("Created metric: GOLD_SPOT_USD")
    return metric


def _parse_wgc_price_rows(csv_path: Path):
    """Return (parsed, skipped, newest_day1) using the historical column rules.

    parsed is a list of (day-1 datetime, Decimal). No database access.
    """
    parsed = []
    skipped = 0
    newest_source_date = None
    source_line = (
        "Source: Bloomberg, Datastream, ICE Benchmark Administration, "
        "Multi Commodity Exchange of India, World Gold Council"
    )

    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))

    for row in rows:
        # Need at least 4 columns: blank, blank, date, USD
        if len(row) < 4:
            continue

        date_str = row[2].strip()
        usd_str = row[3].strip().replace(",", "")

        if not date_str or date_str == source_line:
            continue

        try:
            date = datetime.strptime(date_str, "%m/%d/%Y").replace(day=1)
        except ValueError:
            continue

        if not usd_str or usd_str in ("#N/A", "N/A", "", "USD"):
            skipped += 1
            continue

        try:
            value = Decimal(usd_str)
        except Exception:
            skipped += 1
            continue

        if newest_source_date is None or date > newest_source_date:
            newest_source_date = date
        parsed.append((date, value))

    return parsed, skipped, newest_source_date


def _monthly_write_refusal(db: Session, metric: Metric, parsed) -> str:
    """Empty string when a monthly seed is still safe; otherwise the reason.

    Safe: every stored GOLD_SPOT_USD row is on day 1, and no incoming value
    disagrees with a stored one. A mid-month row means the series is the
    daily spot series. A different number on an existing date is the
    overwrite this guard exists to stop — including a day-1 spot print.
    The message carries no prices. It has to fit UpdateLog.error_message
    String(500).
    """
    stored = db.query(TimeSeries).filter(
        TimeSeries.metric_id == metric.id,
        TimeSeries.country_id == None,  # noqa: E711
    ).all()
    by_date = {row.date: Decimal(str(row.value)) for row in stored}

    def _msg(why: str) -> str:
        text = (
            f"Refusing to write GOLD_SPOT_USD from the WGC monthly-average "
            f"CSV: {why} Dates normalise to day 1; this is not the update "
            f"(D-0041, D-0094). Use run_gold_price_fetch or POST "
            f"/api/fetch/gold-price. Write-guard only, not a copyright ruling."
        )
        if len(text) > 500:
            raise RuntimeError(f"refusal message is {len(text)} chars")
        return text

    if any(row.date.day != 1 for row in stored):
        return _msg("the series has an observation that is not on day 1.")
    for date, value in parsed:
        current = by_date.get(date)
        if current is not None and current != value:
            return _msg("an incoming average differs from a stored observation.")
    return ""


def import_gold_price_csv(db: Session, csv_path: Path = CSV_PATH) -> dict:
    """
    Parse a WGC gold-price CSV and seed USD history when that is still safe.

    CSV format:
      Row 1-5: headers/metadata (skip)
      Row 6+:  [blank, blank, date(M/D/YYYY), USD, EUR, JPY, ...]
      Date column: index 2
      USD column:  index 3

    Not the live update. See the module docstring and F-0133.
    """
    if not csv_path.exists():
        raise FileNotFoundError(
            f"Gold price CSV not found at {csv_path}\n"
            f"Download from: https://www.gold.org/goldhub/data/gold-prices\n"
            f"Save as: {csv_path}"
        )

    metric = ensure_spot_metric(db)
    parsed, skipped, newest_source_date = _parse_wgc_price_rows(csv_path)

    # D-0027: refuse a present-but-frozen file. This is the case that
    # actually occurred and ran undetected for three months. Checked
    # before any series write.
    if newest_source_date is None:
        db.rollback()
        raise ValueError(
            f"Gold price CSV at {csv_path} yielded no parseable rows "
            f"({skipped} rows skipped). Refusing to report success."
        )

    age_days = (datetime.utcnow() - newest_source_date).days
    if age_days > MAX_SOURCE_AGE_DAYS:
        db.rollback()
        raise ValueError(
            f"Gold price CSV at {csv_path} is stale: newest row "
            f"{newest_source_date.date()} is {age_days} days old, limit is "
            f"{MAX_SOURCE_AGE_DAYS}. The file is present but frozen - refresh it "
            f"from https://www.gold.org/goldhub/data/gold-prices"
        )

    refusal = _monthly_write_refusal(db, metric, parsed)
    if refusal:
        db.rollback()
        raise ValueError(refusal)

    inserted = updated = 0
    for date, value in parsed:
        existing = db.query(TimeSeries).filter(
            TimeSeries.metric_id == metric.id,
            TimeSeries.country_id == None,  # noqa: E711
            TimeSeries.date == date,
        ).first()

        if existing:
            existing.value = value
            existing.updated_at = datetime.utcnow()
            updated += 1
        else:
            db.add(TimeSeries(
                metric_id=metric.id,
                country_id=None,
                date=date,
                value=value,
            ))
            inserted += 1

    db.commit()
    logger.info(f"Gold price import: {inserted} inserted, {updated} updated, {skipped} skipped")
    return {
        "status": "success",
        "inserted": inserted,
        "updated": updated,
        "skipped": skipped,
        "series": "GOLD_SPOT_USD",
        "source_latest": newest_source_date.date().isoformat(),
        "source_age_days": age_days,
    }


def run_gold_price_import(db: Session) -> dict:
    """Manual CSV entry point. Not scheduled, and not POST /api/fetch/gold-price.

    That route calls run_gold_price_fetch (D-0094). This function remains for
    a monthly-only seed. F-0133 refuses it once the series is daily or a
    stored value would change.
    """
    start_time = datetime.utcnow()
    try:
        result = import_gold_price_csv(db, CSV_PATH)
        db.add(UpdateLog(
            pipeline_name="Gold_Spot_Price",
            status="success",
            records_inserted=result["inserted"],
            records_updated=result["updated"],
            error_message=None,
            started_at=start_time,
            completed_at=datetime.utcnow(),
        ))
        db.commit()
        return result
    except Exception as e:
        logger.error(f"Gold price import failed: {e}")
        db.add(UpdateLog(
            pipeline_name="Gold_Spot_Price",
            status="failed",
            records_inserted=0,
            records_updated=0,
            error_message=str(e),
            started_at=start_time,
            completed_at=datetime.utcnow(),
        ))
        db.commit()
        raise
