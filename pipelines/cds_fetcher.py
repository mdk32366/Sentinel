"""
CDS Data Pipeline - Multi-Tenor + Flexible URL Handling
-------------------------------------------------------
Handles both "5-year" and "5-years" URL variations on Investing.com.
"""

import logging
import re
from datetime import datetime
from decimal import Decimal
from typing import Dict, Optional, List

import requests
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from database.models import Metric, TimeSeries, UpdateLog

logger = logging.getLogger(__name__)


# ============================================================
# CDS INSTRUMENTS
# ============================================================
CDS_INSTRUMENTS = {
    "France": {
        "5Y": {
            "slug": "france-cds-5-years-usd",
            "code": "FRANCE_CDS_5Y",
        },
    },
    "Germany": {
        "5Y": {
            "slug": "germany-cds-5-year-usd",
            "code": "GERMANY_CDS_5Y",
        },
        "10Y": {
            "slug": "germany-cds-10-year-usd",
            "code": "GERMANY_CDS_10Y",
        },
    },
    "Greece": {
        "5Y": {
            "slug": "greece-cds-5-years-usd",
            "code": "GREECE_CDS_5Y",
        },
        "10Y": {
            "slug": "greece-cds-10-years-usd",
            "code": "GREECE_CDS_10Y",
        },
    },
    "Italy": {
        "5Y": {
            "slug": "italy-cds-5-years-usd",
            "code": "ITALY_CDS_5Y",
        },
        "10Y": {
            "slug": "italy-cds-10-years-usd",
            "code": "ITALY_CDS_10Y",
        },
    },
    "Spain": {
        "5Y": {
            "slug": "spain-cds-5-years-usd",
            "code": "SPAIN_CDS_5Y",
        },
        "10Y": {
            "slug": "spain-cds-10-years-usd",
            "code": "SPAIN_CDS_10Y",
        },
    },
    "Switzerland": {
        "5Y": {
            "slug": "switzerland-cds-5-year-usd",
            "code": "SWITZERLAND_CDS_5Y",
        },
        "10Y": {
            "slug": "switzerland-cds-10-year-usd",
            "code": "SWITZERLAND_CDS_10Y",
        },
    },
    "Russia": {
        "5Y": {
            "slug": "russia-cds-5-years-usd",
            "code": "RUSSIA_CDS_5Y",
        },
        "10Y": {
            "slug": "russia-cds-10-years-usd",
            "code": "RUSSIA_CDS_10Y",
        },
    },
    "Turkey": {
        "5Y": {
            "slug": "turkey-cds-5-year-usd",
            "code": "TURKEY_CDS_5Y",
        },
        "10Y": {
            "slug": "turkey-cds-10-years-usd",
            "code": "TURKEY_CDS_10Y",
        },
    },
    "Saudi Arabia": {
        "5Y": {
            "slug": "saudi-arabia-cds-5-year-usd",
            "code": "SAUDI_ARABIA_CDS_5Y",
        },
        "10Y": {
            "slug": "saudi-arabia-cds-10-year-usd",
            "code": "SAUDI_ARABIA_CDS_10Y",
        },
    },
    "Egypt": {
        "5Y": {
            "slug": "egypt-cds-5-years-usd",
            "code": "EGYPT_CDS_5Y",
        },
    },
    "China": {
        "5Y": {
            "slug": "china-cds-5-years-usd",
            "code": "CHINA_CDS_5Y",
        },
        "10Y": {
            "slug": "china-cds-10-year-usd",
            "code": "CHINA_CDS_10Y",
        },
    },
    "Japan": {
        "5Y": {
            "slug": "japan-cds-5-year-usd",
            "code": "JAPAN_CDS_5Y",
        },
        "10Y": {
            "slug": "japan-cds-10-year-usd",
            "code": "JAPAN_CDS_10Y",
        },
    },
    "South Korea": {
        "5Y": {
            "slug": "south-korea-cds-5-year-usd",
            "code": "SOUTH_KOREA_CDS_5Y",
        },
        "10Y": {
            "slug": "south-korea-cds-10-year-usd",
            "code": "SOUTH_KOREA_CDS_10Y",
        },
    },
    "India": {
        "5Y": {
            "slug": "india-cds-5-year-usd",
            "code": "INDIA_CDS_5Y",
        },
        "10Y": {
            "slug": "india-cds-10-year-usd",
            "code": "INDIA_CDS_10Y",
        },
    },
    "Indonesia": {
        "5Y": {
            "slug": "indonesia-cds-5-years-usd",
            "code": "INDONESIA_CDS_5Y",
        },
        "10Y": {
            "slug": "indonesia-cds-10-year-usd",
            "code": "INDONESIA_CDS_10Y",
        },
    },
    "United States": {
        "5Y": {
            "slug": "united-states-cds-5-years-usd",
            "code": "UNITED_STATES_CDS_5Y",
        },
        "10Y": {
            "slug": "united-states-cds-10-years-usd",
            "code": "UNITED_STATES_CDS_10Y",
        },
    },
    "Canada": {
        "5Y": {
            "slug": "canada-cds-5-years-usd",
            "code": "CANADA_CDS_5Y",
        },
    },
    "Mexico": {
        "5Y": {
            "slug": "mexico-cds-5-years-usd",
            "code": "MEXICO_CDS_5Y",
        },
    },
    "Brazil": {
        "5Y": {
            "slug": "brazil-cds-5-years-usd",
            "code": "BRAZIL_CDS_5Y",
        },
        "10Y": {
            "slug": "brazil-cds-10-years-usd",
            "code": "BRAZIL_CDS_10Y",
        },
    },
    "Australia": {
        "5Y": {
            "slug": "australia-cds-5-years-usd",
            "code": "AUSTRALIA_CDS_5Y",
        },
        "10Y": {
            "slug": "australia-cds-10-years-usd",
            "code": "AUSTRALIA_CDS_10Y",
        },
    },
    "South Africa": {
        "5Y": {
            "slug": "south-africa-cds-5-year-usd",
            "code": "SOUTH_AFRICA_CDS_5Y",
        },
        "10Y": {
            "slug": "south-africa-cds-10-year-usd",
            "code": "SOUTH_AFRICA_CDS_10Y",
        },
    },
}


def ensure_metric(db: Session, code: str, name: str, description: str = "") -> Metric:
    metric = db.query(Metric).filter_by(code=code).first()
    if not metric:
        metric = Metric(
            code=code,
            name=name,
            category="sovereign_cds",
            unit="bps",
            source="Investing.com",
            description=description,
        )
        db.add(metric)
        db.commit()
        logger.info(f"Created CDS metric: {code}")
    return metric


def fetch_cds_value(slug: str, timeout: int = 20) -> Optional[Decimal]:
    """
    Try the given slug first.
    If it 404s, automatically try the alternative ("year" <-> "years").
    """
    base_url = "https://www.investing.com/rates-bonds/"

    # Generate both possible URL variations
    if "year-usd" in slug:
        alternatives = [slug, slug.replace("year-usd", "years-usd")]
    elif "years-usd" in slug:
        alternatives = [slug, slug.replace("years-usd", "year-usd")]
    else:
        alternatives = [slug]

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    }

    for candidate in alternatives:
        url = f"{base_url}{candidate}"
        try:
            resp = requests.get(url, headers=headers, timeout=timeout)
            if resp.status_code == 404:
                continue  # Try the other variation

            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            page_text = soup.get_text(separator=" ", strip=True)

            # Primary pattern: price + daily change
            pattern = r'(\d{2,4}(?:\.\d{1,2})?)\s*[\+\-]?\d+\s*\([+\-]?\d+\.?\d*\%\)'
            matches = re.findall(pattern, page_text)
            for m in matches:
                try:
                    val = Decimal(m)
                    if 50 < val < 3000:
                        return val
                except Exception:
                    continue

            # Fallback
            numbers = re.findall(r'\b(\d{2,4}(?:\.\d{1,2})?)\b', page_text[:6000])
            for n in numbers:
                try:
                    val = Decimal(n)
                    if 100 < val < 800:
                        return val
                except Exception:
                    continue

        except Exception as e:
            logger.debug(f"Error fetching {candidate}: {e}")
            continue

    logger.warning(f"Could not fetch valid CDS value for slug: {slug}")
    return None


def run_cds_fetch(db: Session) -> dict:
    start_time = datetime.utcnow()
    total_inserted = 0
    total_updated = 0
    errors = []

    today = datetime.utcnow().date()

    for country, tenors in CDS_INSTRUMENTS.items():
        for tenor, info in tenors.items():
            try:
                # info['code'] already includes the tenor (e.g. "FRANCE_CDS_5Y"),
                # so use it directly. Previously this appended "_{tenor}" again,
                # producing doubled codes like "FRANCE_CDS_5Y_5Y".
                metric_name = info['code']
                metric = ensure_metric(
                    db,
                    code=metric_name,
                    name=f"{country} {tenor} CDS Spread",
                    description=f"{country} {tenor} Sovereign CDS from Investing.com",
                )

                value = fetch_cds_value(info["slug"])
                if value is None:
                    errors.append(f"{metric_name}: fetch returned None")
                    continue

                existing = db.query(TimeSeries).filter(
                    TimeSeries.metric_id == metric.id,
                    TimeSeries.date == today,
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
                        date=today,
                        value=value,
                    ))
                    total_inserted += 1

                db.commit()
                logger.info(f"CDS {metric_name}: {value} bps")

            except Exception as e:
                logger.error(f"Error processing {country} {tenor}: {e}")
                errors.append(f"{country} {tenor}: {str(e)}")

    status = "success" if not errors else "partial"

    db.add(UpdateLog(
        pipeline_name="CDS_MultiTenor",
        status=status,
        records_inserted=total_inserted,
        records_updated=total_updated,
        error_message="; ".join(errors) if errors else None,
        started_at=start_time,
        completed_at=datetime.utcnow(),
    ))
    db.commit()

    return {
        "status": status,
        "inserted": total_inserted,
        "updated": total_updated,
        "errors": errors,
    }