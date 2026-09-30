"""
Gold Reserves Data Pipeline
----------------------------
Imports World Gold Council historical gold reserves CSV.

CSV format: Country × Quarter (Q4 00 → present), values in tonnes
Source: https://www.gold.org/goldhub/data/gold-reserves-by-country
Local path: data/gold_reserves.csv  (re-download monthly to keep current)

This wrapper delegates to the proven gold_fetcher.py implementation.
"""

import logging
from datetime import datetime
from pathlib import Path
from sqlalchemy.orm import Session
from database.models import UpdateLog
from pipelines.paths import DATA_DIR

logger = logging.getLogger(__name__)

CSV_PATH = DATA_DIR / "gold_reserves.csv"


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
        # D-0027: a missing source file is a failure, not a quiet "partial".
        # A guard that stands aside is how a dangerous thing comes to look harmless.
        logger.error(msg)
        db.add(UpdateLog(
            pipeline_name="Gold_Reserves",
            status="failed",
            records_inserted=0,
            records_updated=0,
            error_message=msg,
            started_at=start_time,
            completed_at=datetime.utcnow(),
        ))
        db.commit()
        raise FileNotFoundError(msg)

    try:
        # F-0103. This called `import_wgc_csv` without importing it, so every
        # run raised NameError - 35 of 35 in the log, and the job has never
        # once succeeded. Imported here rather than at module scope because
        # gold_fetcher imports composite_stress, and a top-level import would
        # add a third module to that chain for one function.
        from pipelines.gold_fetcher import import_wgc_csv

        # Delegate to the proven gold_fetcher implementation
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
            # D-0090. The importer refuses a frozen file; these let a reader
            # watch it age before that happens.
            "source_latest": result.get("source_latest"),
            "source_age_days": result.get("source_age_days"),
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
