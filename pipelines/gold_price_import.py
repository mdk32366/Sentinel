"""
Spot Gold Price CSV Importer
-----------------------------
Imports historical monthly gold price (USD/troy oz) into the database.

Source: World Gold Council / ICE Benchmark Administration
File: C:\projects\sentinel\data\gold_prices.csv
Format: Monthly, USD per troy ounce, back to January 1978

Run once to seed history, then update monthly by re-downloading and re-running.
"""

import csv
import logging
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from sqlalchemy.orm import Session
from database.models import Metric, TimeSeries, UpdateLog

logger = logging.getLogger(__name__)

CSV_PATH = Path(__file__).parent.parent / "data" / "gold_prices.csv"

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


def import_gold_price_csv(db: Session, csv_path: Path = CSV_PATH) -> dict:
    """
    Parse WGC gold price CSV and load USD spot price history.

    CSV format:
      Row 1-5: headers/metadata (skip)
      Row 6+:  [blank, blank, date(M/D/YYYY), USD, EUR, JPY, ...]
      Date column: index 2
      USD column:  index 3
    """
    if not csv_path.exists():
        raise FileNotFoundError(
            f"Gold price CSV not found at {csv_path}\n"
            f"Download from: https://www.gold.org/goldhub/data/gold-prices\n"
            f"Save as: {csv_path}"
        )

    metric = ensure_spot_metric(db)
    inserted = updated = skipped = 0

    with open(csv_path, newline='', encoding='utf-8-sig') as f:
        reader = csv.reader(f)
        rows = list(reader)

    for row in rows:
        # Need at least 4 columns: blank, blank, date, USD
        if len(row) < 4:
            continue

        date_str = row[2].strip()
        usd_str = row[3].strip().replace(",", "")

        # Skip header/metadata rows
        if not date_str or date_str in ("", "Source: Bloomberg, Datastream, ICE Benchmark Administration, Multi Commodity Exchange of India, World Gold Council"):
            continue

        # Parse date - format is M/D/YYYY
        try:
            date = datetime.strptime(date_str, "%m/%d/%Y")
            # Normalize to first of month
            date = date.replace(day=1)
        except ValueError:
            continue

        # Parse USD value
        if not usd_str or usd_str in ("#N/A", "N/A", "", "USD"):
            skipped += 1
            continue

        try:
            value = Decimal(usd_str)
        except Exception:
            skipped += 1
            continue

        # Spot gold has no country
        existing = db.query(TimeSeries).filter(
            TimeSeries.metric_id == metric.id,
            TimeSeries.country_id == None,
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
    }


def run_gold_price_import(db: Session) -> dict:
    """Entry point called by API route."""
    start_time = datetime.utcnow()
    try:
        result = import_gold_price_csv(db)
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
