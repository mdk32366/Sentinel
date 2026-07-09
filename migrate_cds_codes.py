#!/usr/bin/env python3
"""
One-time migration: fix doubled CDS metric codes.
--------------------------------------------------
The CDS fetcher previously stored metric codes like "FRANCE_CDS_5Y_5Y"
(the tenor was appended twice). This renames each doubled code to its
clean form ("FRANCE_CDS_5Y").

Safe to run more than once — it only acts on codes that still contain a
doubled tenor suffix, and it merges rather than collides if a clean code
already exists.

Usage:
    python migrate_cds_codes.py            # dry run (shows what would change)
    python migrate_cds_codes.py --apply    # actually perform the migration
"""

import sys
import re
import logging

from database.connection import get_session
from database.models import Metric, TimeSeries

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

# Matches a trailing doubled tenor: "..._5Y_5Y" or "..._10Y_10Y"
DOUBLED = re.compile(r"^(?P<base>.+_CDS_(?P<tenor>\d+Y))_(?P=tenor)$")


def find_doubled(db):
    """Return list of (metric, clean_code) for every doubled CDS metric."""
    out = []
    for metric in db.query(Metric).filter(Metric.code.like("%_CDS_%")).all():
        m = DOUBLED.match(metric.code)
        if m:
            out.append((metric, m.group("base")))
    return out


def migrate(apply: bool):
    db = get_session()
    try:
        doubled = find_doubled(db)
        if not doubled:
            logger.info("No doubled CDS codes found. Nothing to do.")
            return

        logger.info(f"Found {len(doubled)} doubled CDS metric code(s):\n")
        renames, merges = 0, 0

        for metric, clean_code in doubled:
            existing = db.query(Metric).filter_by(code=clean_code).first()

            if existing and existing.id != metric.id:
                # Clean code already exists — move this metric's timeseries
                # onto the existing metric, then delete the doubled metric.
                ts_count = db.query(TimeSeries).filter_by(metric_id=metric.id).count()
                logger.info(
                    f"  MERGE  {metric.code}  ->  {clean_code} "
                    f"(move {ts_count} rows onto existing metric #{existing.id}, "
                    f"delete metric #{metric.id})"
                )
                if apply:
                    db.query(TimeSeries).filter_by(metric_id=metric.id).update(
                        {TimeSeries.metric_id: existing.id}, synchronize_session=False
                    )
                    db.delete(metric)
                merges += 1
            else:
                # Simple rename.
                logger.info(f"  RENAME {metric.code}  ->  {clean_code}")
                if apply:
                    metric.code = clean_code
                renames += 1

        if apply:
            db.commit()
            logger.info(f"\nDone. {renames} renamed, {merges} merged.")
        else:
            logger.info(
                f"\nDRY RUN. Would rename {renames}, merge {merges}. "
                "Re-run with --apply to perform the migration."
            )
    finally:
        db.close()


if __name__ == "__main__":
    apply = "--apply" in sys.argv
    print("=== CDS metric-code migration ===")
    migrate(apply=apply)
    print("=== Complete ===")
