"""
Broad Money Growth Pipeline
----------------------------
Imports annual broad money growth (% YoY) from a local JSON file
downloaded from the World Bank API.

To refresh the data:
  curl "https://api.worldbank.org/v2/country/JP;CN;GB;BE;CA;LU;FR;IE;TW;CH;SG;HK;NO;IN;BR;SA;KR;DE;NL;AE;TH;IL;TR;MX;SE;AU;PL;PH;ID;ZA;EG;AR;CL;CO;PE;CZ;HU;RO;KW;QA;RU;MY;VN;BD;KZ;UA;KY/indicator/FM.LBL.BMNY.ZG?format=json&mrv=30&per_page=2000" -o C:\\projects\\sentinel\\data\\money_supply.json

Signal thresholds:
  >15%  Elevated — watch
  >30%  Significant debasement — pressure on currency and reserves
  >50%  Crisis-level — reserve drawdown typically follows
  >100% Hyperinflationary episode
"""

import json
import logging
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from sqlalchemy.orm import Session
from database.models import Metric, TimeSeries, Country, UpdateLog

logger = logging.getLogger(__name__)

JSON_PATH = Path(__file__).parent.parent / "data" / "money_supply.json"

MONEY_METRIC = {
    "code": "BROAD_MONEY_GROWTH",
    "name": "Broad Money Growth (Annual %)",
    "category": "monetary",
    "unit": "%",
    "source": "WorldBank_IMF",
    "description": "Annual % growth in broad money supply. Source: World Bank / IMF IFS."
}


def ensure_money_metric(db: Session) -> Metric:
    metric = db.query(Metric).filter_by(code=MONEY_METRIC["code"]).first()
    if not metric:
        metric = Metric(**MONEY_METRIC)
        db.add(metric)
        db.commit()
        logger.info("Created metric: BROAD_MONEY_GROWTH")
    return metric


def run_money_supply_fetch(db: Session) -> dict:
    """Import broad money growth from local World Bank JSON file."""
    start_time = datetime.utcnow()
    inserted = updated = skipped = 0

    if not JSON_PATH.exists():
        raise FileNotFoundError(
            f"Money supply data not found at {JSON_PATH}\n"
            f"Run this curl command to download it:\n"
            f'curl "https://api.worldbank.org/v2/country/JP;CN;GB;BE;CA;LU;FR;IE;TW;'
            f'CH;SG;HK;NO;IN;BR;SA;KR;DE;NL;AE;TH;IL;TR;MX;SE;AU;PL;PH;ID;ZA;EG;'
            f'AR;CL;CO;PE;CZ;HU;RO;KW;QA;RU;MY;VN;BD;KZ;UA;KY/indicator/'
            f'FM.LBL.BMNY.ZG?format=json&mrv=30&per_page=2000" '
            f'-o {JSON_PATH}'
        )

    try:
        with open(JSON_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        raise ValueError(f"Failed to parse {JSON_PATH}: {e}")

    if len(data) < 2 or not data[1]:
        raise ValueError("JSON file has no data records")

    metric = ensure_money_metric(db)
    countries_found = set()

    for item in data[1]:
        iso3 = item.get("countryiso3code")
        date_str = item.get("date")
        value = item.get("value")

        # Skip nulls — many countries have reporting gaps
        if not iso3 or not date_str or value is None:
            skipped += 1
            continue

        country = db.query(Country).filter_by(iso_code=iso3).first()
        if not country:
            skipped += 1
            continue

        try:
            year = int(date_str)
            date = datetime(year, 1, 1)
            pct = Decimal(str(round(float(value), 4)))
        except (ValueError, TypeError):
            skipped += 1
            continue

        countries_found.add(iso3)

        existing = db.query(TimeSeries).filter(
            TimeSeries.metric_id == metric.id,
            TimeSeries.country_id == country.id,
            TimeSeries.date == date,
        ).first()

        if existing:
            existing.value = pct
            existing.updated_at = datetime.utcnow()
            updated += 1
        else:
            db.add(TimeSeries(
                metric_id=metric.id,
                country_id=country.id,
                date=date,
                value=pct,
            ))
            inserted += 1

    db.commit()
    logger.info(f"Money supply import: {inserted} inserted, {updated} updated, "
                f"{skipped} skipped, {len(countries_found)} countries")

    db.add(UpdateLog(
        pipeline_name="Broad_Money_Growth",
        status="success",
        records_inserted=inserted,
        records_updated=updated,
        error_message=None,
        started_at=start_time,
        completed_at=datetime.utcnow(),
    ))
    db.commit()

    return {
        "status": "success",
        "inserted": inserted,
        "updated": updated,
        "skipped": skipped,
        "countries": len(countries_found),
    }
