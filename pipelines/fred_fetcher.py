import requests
import logging
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from config import settings
from database.models import Metric, TimeSeries, UpdateLog
from decimal import Decimal

logger = logging.getLogger(__name__)

FRED_BASE_URL = "https://api.stlouisfed.org/fred"

# Define FRED series to fetch
FRED_SERIES = {
    "DGS10": {
        "name": "US Treasury 10-Year Yield",
        "category": "treasury",
        "unit": "percent",
    },
    "DGS5": {
        "name": "US Treasury 5-Year Yield",
        "category": "treasury",
        "unit": "percent",
    },
    "DGS2": {
        "name": "US Treasury 2-Year Yield",
        "category": "treasury",
        "unit": "percent",
    },
    "DCOILWTICO": {
        "name": "WTI Crude Oil Spot Price",
        "category": "oil",
        "unit": "usd_per_barrel",
    },
}


def ensure_metrics_exist(db: Session):
    """Create metric records if they don't exist"""
    for code, info in FRED_SERIES.items():
        existing = db.query(Metric).filter_by(code=code).first()
        if not existing:
            metric = Metric(
                code=code,
                name=info["name"],
                category=info["category"],
                unit=info["unit"],
                source="FRED",
                description=f"Fetched from Federal Reserve Economic Data (FRED)"
            )
            db.add(metric)
            logger.info(f"Created metric: {code}")
    db.commit()


def fetch_series(code: str, start_date: datetime = None) -> list:
    """
    Fetch a single FRED series via API
    
    Returns list of dicts: [{"date": "2024-01-15", "value": 4.25}, ...]
    """
    if start_date is None:
        # Default to 2 years back
        start_date = datetime.utcnow() - timedelta(days=730)
    
    params = {
        "series_id": code,
        "api_key": settings.fred_api_key,
        "file_type": "json",
        "observation_start": start_date.strftime("%Y-%m-%d"),
    }
    
    try:
        response = requests.get(f"{FRED_BASE_URL}/series/observations", params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        observations = []
        for obs in data.get("observations", []):
            if obs["value"] != ".":  # FRED uses "." for missing data
                observations.append({
                    "date": datetime.strptime(obs["date"], "%Y-%m-%d"),
                    "value": Decimal(obs["value"]),
                })
        
        logger.info(f"Fetched {len(observations)} observations for {code}")
        return observations
    
    except requests.RequestException as e:
        logger.error(f"Error fetching {code}: {e}")
        return []


def upsert_timeseries(db: Session, metric: Metric, observations: list) -> tuple:
    """
    Upsert timeseries data (insert or update)
    Returns (inserted_count, updated_count)
    """
    inserted = 0
    updated = 0
    
    for obs in observations:
        existing = db.query(TimeSeries).filter(
            TimeSeries.metric_id == metric.id,
            TimeSeries.country_id.is_(None),  # Global metrics have no country
            TimeSeries.date == obs["date"]
        ).first()
        
        if existing:
            existing.value = obs["value"]
            existing.updated_at = datetime.utcnow()
            updated += 1
        else:
            ts = TimeSeries(
                metric_id=metric.id,
                country_id=None,
                date=obs["date"],
                value=obs["value"],
            )
            db.add(ts)
            inserted += 1
    
    db.commit()
    return inserted, updated


def run_fred_fetch(db: Session) -> dict:
    """
    Main FRED fetch pipeline
    Returns status dict with counts and errors
    """
    start_time = datetime.utcnow()
    total_inserted = 0
    total_updated = 0
    errors = []
    
    try:
        # Ensure all metrics exist
        ensure_metrics_exist(db)
        
        # Fetch each series
        for code in FRED_SERIES.keys():
            logger.info(f"Fetching FRED series: {code}")
            
            # Get the metric record
            metric = db.query(Metric).filter_by(code=code).first()
            if not metric:
                logger.error(f"Metric {code} not found after creation")
                errors.append(f"Metric {code} not created")
                continue
            
            # Fetch observations
            observations = fetch_series(code)
            if not observations:
                errors.append(f"No data returned for {code}")
                continue
            
            # Upsert into DB
            inserted, updated = upsert_timeseries(db, metric, observations)
            total_inserted += inserted
            total_updated += updated
            logger.info(f"{code}: inserted {inserted}, updated {updated}")
        
        # Log the update
        status = "success" if not errors else "partial"
        update_log = UpdateLog(
            pipeline_name="FRED",
            status=status,
            records_inserted=total_inserted,
            records_updated=total_updated,
            error_message="; ".join(errors) if errors else None,
            started_at=start_time,
            completed_at=datetime.utcnow(),
        )
        db.add(update_log)
        db.commit()
        
        logger.info(f"FRED fetch complete: {total_inserted} inserted, {total_updated} updated")
        return {
            "status": status,
            "inserted": total_inserted,
            "updated": total_updated,
            "errors": errors,
        }
    
    except Exception as e:
        logger.error(f"FRED fetch failed: {e}", exc_info=True)
        update_log = UpdateLog(
            pipeline_name="FRED",
            status="failed",
            records_inserted=0,
            records_updated=0,
            error_message=str(e),
            started_at=start_time,
            completed_at=datetime.utcnow(),
        )
        db.add(update_log)
        db.commit()
        raise
