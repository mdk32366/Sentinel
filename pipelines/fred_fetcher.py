"""
FRED Data Pipeline
------------------
Fetches economic time series from the Federal Reserve Economic Data API.
Runs daily at 2am via scheduler.
"""

import requests
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from sqlalchemy.orm import Session
from database.models import Metric, TimeSeries, UpdateLog
from config import settings

logger = logging.getLogger(__name__)

FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"

FRED_METRICS = [
    {"code": "DGS10",             "name": "10-Year Treasury Yield",         "category": "treasury",   "unit": "%",          "description": "Market yield on US Treasury securities at 10-year constant maturity"},
    {"code": "DGS5",              "name": "5-Year Treasury Yield",          "category": "treasury",   "unit": "%",          "description": "Market yield on US Treasury securities at 5-year constant maturity"},
    {"code": "DGS2",              "name": "2-Year Treasury Yield",          "category": "treasury",   "unit": "%",          "description": "Market yield on US Treasury securities at 2-year constant maturity"},
    {"code": "FEDFUNDS",          "name": "Federal Funds Rate",             "category": "monetary",   "unit": "%",          "description": "Effective federal funds rate"},
    {"code": "DFII10",            "name": "10-Year Real Yield (TIPS)",      "category": "treasury",   "unit": "%",          "description": "Market yield on US Treasury inflation-indexed securities at 10-year constant maturity"},
    {"code": "DCOILWTICO",        "name": "WTI Crude Oil Price",            "category": "commodity",  "unit": "$/bbl",      "description": "Crude oil prices: West Texas Intermediate (WTI)"},
    {"code": "DTWEXBGS",          "name": "US Dollar Index",                "category": "fx",         "unit": "index",      "description": "Nominal broad US dollar index"},
    {"code": "CPIAUCSL",          "name": "Consumer Price Index (CPI)",     "category": "inflation",  "unit": "index",      "description": "Consumer price index for all urban consumers: all items"},
    {"code": "M2SL",              "name": "M2 Money Supply",                "category": "monetary",   "unit": "billions",   "description": "M2 money stock"},
    {"code": "IRLTLT01JPM156N", "name": "Japan 10Y Gov Bond Yield",    "category": "sovereign_yield", "unit": "%", "source": "FRED", "description": "Japan 10-year government bond yield, monthly (OECD)"},
    {"code": "IRLTLT01DEM156N", "name": "Germany 10Y Gov Bond Yield",  "category": "sovereign_yield", "unit": "%", "source": "FRED", "description": "Germany 10-year government bond yield, monthly (OECD)"},
    {"code": "IRLTLT01ITM156N", "name": "Italy 10Y Gov Bond Yield",    "category": "sovereign_yield", "unit": "%", "source": "FRED", "description": "Italy 10-year government bond yield, monthly (OECD)"},
    {"code": "IRLTLT01FRM156N", "name": "France 10Y Gov Bond Yield",   "category": "sovereign_yield", "unit": "%", "source": "FRED", "description": "France 10-year government bond yield, monthly (OECD)"},
    {"code": "IRLTLT01ESM156N", "name": "Spain 10Y Gov Bond Yield",    "category": "sovereign_yield", "unit": "%", "source": "FRED", "description": "Spain 10-year government bond yield, monthly (OECD)"},
    {"code": "IRLTLT01GBM156N", "name": "UK 10Y Gov Bond Yield",       "category": "sovereign_yield", "unit": "%", "source": "FRED", "description": "UK 10-year government bond yield, monthly (OECD)"},
    {"code": "IRLTLT01AUM156N", "name": "Australia 10Y Gov Bond Yield","category": "sovereign_yield", "unit": "%", "source": "FRED", "description": "Australia 10-year government bond yield, monthly (OECD)"},
    {"code": "IRLTLT01CAM156N", "name": "Canada 10Y Gov Bond Yield",   "category": "sovereign_yield", "unit": "%", "source": "FRED", "description": "Canada 10-year government bond yield, monthly (OECD)"},
]


def ensure_metric(db: Session, metric_data: dict) -> Metric:
    metric = db.query(Metric).filter_by(code=metric_data["code"]).first()
    if not metric:
        metric = Metric(**metric_data)
        db.add(metric)
        db.commit()
        logger.info(f"Created metric: {metric_data['code']}")
    return metric


def fetch_fred_series(series_id: str, start_date: str, end_date: str) -> list:
    """Fetch observations from FRED API."""
    params = {
        "series_id": series_id,
        "api_key": settings.fred_api_key,
        "file_type": "json",
        "observation_start": start_date,
        "observation_end": end_date,
    }
    r = requests.get(FRED_BASE, params=params, timeout=30)
    r.raise_for_status()
    data = r.json()
    return data.get("observations", [])


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

            for obs in observations:
                value_str = obs.get("value", ".")
                if value_str == ".":
                    continue
                try:
                    value = Decimal(value_str)
                    date = datetime.strptime(obs["date"], "%Y-%m-%d")
                except Exception:
                    continue

                existing = db.query(TimeSeries).filter(
                    TimeSeries.metric_id == metric.id,
                    TimeSeries.date == date,
                    TimeSeries.country_id == None,
                ).first()

                if existing:
                    existing.value = value
                    existing.updated_at = datetime.utcnow()
                    total_updated += 1
                else:
                    db.add(TimeSeries(
                        metric_id=metric.id,
                        country_id=None,
                        date=date,
                        value=value,
                    ))
                    total_inserted += 1

            db.commit()
            logger.info(f"FRED {metric_data['code']}: fetched {len(observations)} observations")

        except Exception as e:
            logger.error(f"FRED fetch failed for {metric_data['code']}: {e}")
            errors.append(f"{metric_data['code']}: {str(e)}")

    status = "success" if not errors else "partial"
    db.add(UpdateLog(
        pipeline_name="FRED",
        status=status,
        records_inserted=total_inserted,
        records_updated=total_updated,
        error_message="; ".join(errors) if errors else None,
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
