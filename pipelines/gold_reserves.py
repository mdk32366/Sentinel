"""
Gold Reserves Data Pipeline
----------------------------
Imports World Gold Council historical gold reserves CSV.

CSV format: Country × Quarter (Q4 00 → present), values in tonnes
Source: https://www.gold.org/goldhub/data/gold-reserves-by-country
Local path: data/gold_reserves.csv  (re-download monthly to keep current)

This wrapper delegates to the proven experimental/gold_fetcher.py implementation.
"""

import logging
from datetime import datetime
from pathlib import Path
from sqlalchemy.orm import Session
from database.models import UpdateLog

logger = logging.getLogger(__name__)

CSV_PATH = Path(__file__).parent.parent / "data" / "gold_reserves.csv"


def run_gold_reserves_fetch(db: Session) -> dict:
    """
    Main gold reserves pipeline.
    Reads WGC CSV from data/gold_reserves.csv and upserts into TimeSeries.
    Returns status dict compatible with scheduler and manual trigger endpoints.
    """
    start_time = datetime.utcnow()

    # Check CSV exists before attempting import
    if not CSV_PATH.exists():
        msg = (
            f"Gold reserves CSV not found at {CSV_PATH}. "
            "Download from https://www.gold.org/goldhub/data/gold-reserves-by-country "
            "and save as data/gold_reserves.csv"
        )
        logger.warning(msg)
        db.add(UpdateLog(
            pipeline_name="Gold_Reserves",
            status="partial",
            records_inserted=0,
            records_updated=0,
            error_message=msg,
            started_at=start_time,
            completed_at=datetime.utcnow(),
        ))
        db.commit()
        return {"status": "partial", "countries": 0, "inserted": 0, "updated": 0, "errors": [msg]}

    try:
        # Delegate to the proven gold_fetcher implementation
        from pipelines.experimental.gold_fetcher import import_wgc_csv
        result = import_wgc_csv(db, csv_path=CSV_PATH)

        db.add(UpdateLog(
            pipeline_name="Gold_Reserves",
            status="success",
            records_inserted=result["inserted"],
            records_updated=result["updated"],
            error_message=None,
            started_at=start_time,
            completed_at=datetime.utcnow(),
        ))
        db.commit()

        logger.info(
            f"Gold reserves import: {result['inserted']} inserted, "
            f"{result['updated']} updated, {result['skipped']} skipped"
        )

        return {
            "status": "success",
            "inserted": result["inserted"],
            "updated": result["updated"],
            "errors": [],
        }

    except Exception as e:
        logger.error(f"Gold reserves import failed: {e}")
        db.add(UpdateLog(
            pipeline_name="Gold_Reserves",
            status="failed",
            records_inserted=0,
            records_updated=0,
            error_message=str(e),
            started_at=start_time,
            completed_at=datetime.utcnow(),
        ))
        db.commit()
        return {"status": "failed", "inserted": 0, "updated": 0, "errors": [str(e)]}
