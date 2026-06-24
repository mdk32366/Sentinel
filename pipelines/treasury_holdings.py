"""
Treasury Holdings Data Pipeline
--------------------------------
Fetches US Treasury holdings by country from TIC (Treasury International Capital)
Data source: https://ticdata.treasury.gov/Publish/mfhhis01.txt
Runs monthly on day 15 via scheduler.
"""

import requests
import logging
from datetime import datetime
from decimal import Decimal
from sqlalchemy.orm import Session
from database.models import Metric, Country, TimeSeries, UpdateLog
import re

logger = logging.getLogger(__name__)

TIC_MFH_URL = "https://ticdata.treasury.gov/Publish/mfhhis01.txt"

# Country ISO code mappings (TIC table country names -> ISO-3166-1 alpha-3)
COUNTRY_MAPPING = {
    "Japan": "JPN",
    "United Kingdom": "GBR",
    "China, Mainland": "CHN",
    "Belgium": "BEL",
    "Canada": "CAN",
    "Luxembourg": "LUX",
    "Cayman Islands": "CYM",
    "France": "FRA",
    "Ireland": "IRL",
    "Germany": "DEU",
    "Netherlands": "NLD",
    "Switzerland": "CHE",
    "Australia": "AUS",
    "Taiwan": "TWN",
    "South Korea": "KOR",
    "India": "IND",
    "Mexico": "MEX",
    "Brazil": "BRA",
    "Russia": "RUS",
    "Saudi Arabia": "SAU",
    "Singapore": "SGP",
    "Hong Kong": "HKG",
    "Norway": "NOR",
    "Sweden": "SWE",
    "Spain": "ESP",
    "Italy": "ITA",
    "Austria": "AUT",
    "Denmark": "DNK",
    "Finland": "FIN",
    "Greece": "GRC",
    "Portugal": "PRT",
    "Turkey": "TUR",
    "Israel": "ISR",
    "United Arab Emirates": "ARE",
    "Thailand": "THA",
    "Malaysia": "MYS",
    "Indonesia": "IDN",
    "Philippines": "PHL",
    "Vietnam": "VNM",
    "New Zealand": "NZL",
    "Chile": "CHL",
    "Argentina": "ARG",
    "South Africa": "ZAF",
    "Egypt": "EGY",
}


def ensure_metric(db: Session, metric_code: str, metric_name: str) -> Metric:
    """Ensure metric exists, create if not."""
    metric = db.query(Metric).filter_by(code=metric_code).first()
    if not metric:
        metric = Metric(
            code=metric_code,
            name=metric_name,
            category="holdings",
            unit="billions_usd",
            source="TIC",
            description=f"Foreign holdings of US Treasury securities - {metric_name}",
        )
        db.add(metric)
        db.commit()
        logger.info(f"Created metric: {metric_code}")
    return metric


def ensure_country(db: Session, iso_code: str, country_name: str) -> Country:
    """Ensure country exists, create if not."""
    country = db.query(Country).filter_by(iso_code=iso_code).first()
    if not country:
        country = Country(iso_code=iso_code, name=country_name)
        db.add(country)
        db.commit()
        logger.info(f"Created country: {iso_code} ({country_name})")
    return country


def fetch_tic_mfh_data() -> str:
    """Fetch the TIC MFH table from Treasury."""
    try:
        r = requests.get(TIC_MFH_URL, timeout=30)
        r.raise_for_status()
        return r.text
    except Exception as e:
        logger.error(f"Failed to fetch TIC MFH data: {e}")
        raise


def parse_tic_mfh(text: str) -> dict:
    """
    Parse the TIC MFH fixed-width text file.
    Returns: {country_name: {date: value_in_billions}}
    """
    lines = text.strip().split("\n")
    result = {}
    
    # Find the header line with month/year columns
    header_idx = -1
    for i, line in enumerate(lines):
        if "AT END OF PERIOD" in line or "HOLDINGS" in line:
            header_idx = i
            break
    
    if header_idx == -1:
        logger.error("Could not find header in TIC MFH data")
        return result
    
    # Parse column headers for dates (e.g., "Dec 2025", "Nov 2025", etc.)
    # The format is roughly: Country | Dec 2025 | Nov 2025 | Oct 2025 | ... | Jan YYYY
    header_line = None
    for i in range(header_idx, min(header_idx + 5, len(lines))):
        if "Dec" in lines[i] or any(m in lines[i] for m in ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov"]):
            header_line = lines[i]
            break
    
    if not header_line:
        logger.error("Could not find date headers in TIC MFH data")
        return result
    
    # Extract month-year pairs from header
    # Example: "Dec 2025", "Nov 2025", etc.
    month_abbr = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    dates = []
    parts = header_line.split()
    i = 0
    while i < len(parts):
        if parts[i] in month_abbr:
            if i + 1 < len(parts) and parts[i + 1].isdigit():
                month_str = parts[i]
                year_str = parts[i + 1]
                dates.append(f"{month_str} {year_str}")
                i += 2
            else:
                i += 1
        else:
            i += 1
    
    logger.info(f"Parsed {len(dates)} date columns: {dates[:3]}...")
    
    # Parse data rows
    # Skip header lines and find data
    data_start = header_idx + 5
    for line in lines[data_start:]:
        # Skip empty lines and separator lines
        if not line.strip() or line.strip().startswith("---") or "Country" in line:
            continue
        
        # Split by whitespace, but country name may have multiple words
        parts = line.split()
        if len(parts) < 2:
            continue
        
        # Try to identify where country name ends and data begins
        # Look for the first numeric value
        country_name = None
        values = []
        
        for j, part in enumerate(parts):
            try:
                val = float(part)
                # Found first numeric value; everything before is country name
                country_name = " ".join(parts[:j])
                values = [float(p) for p in parts[j:] if p.replace(".", "").isdigit()]
                break
            except ValueError:
                continue
        
        if country_name and len(values) > 0:
            # Trim common suffixes
            country_name = country_name.replace('"', "").strip()
            if country_name not in result:
                result[country_name] = {}
            
            # Zip dates with values
            for date_str, val in zip(dates[:len(values)], values):
                result[country_name][date_str] = val
    
    logger.info(f"Parsed {len(result)} countries from TIC MFH data")
    return result


def run_treasury_holdings_fetch(db: Session) -> dict:
    """Main TIC holdings fetch pipeline."""
    start_time = datetime.utcnow()
    total_inserted = 0
    total_updated = 0
    errors = []
    
    try:
        # Fetch and parse TIC data
        tic_text = fetch_tic_mfh_data()
        holdings_by_country = parse_tic_mfh(tic_text)
        
        if not holdings_by_country:
            raise ValueError("No holdings data parsed from TIC file")
        
        # Ensure metric exists
        metric = ensure_metric(db, "TIC_UST_HOLDINGS", "Foreign Holdings of US Treasury Securities")
        
        # Process each country's holdings
        for country_name, date_values in holdings_by_country.items():
            iso_code = COUNTRY_MAPPING.get(country_name)
            if not iso_code:
                logger.warning(f"Skipping {country_name} - no ISO code mapping")
                continue
            
            country = ensure_country(db, iso_code, country_name)
            
            for date_str, value_billions in date_values.items():
                try:
                    # Parse date string (e.g., "Dec 2025" -> 2025-12-01)
                    date_obj = datetime.strptime(f"{date_str} 1", "%b %Y %d")
                    value = Decimal(str(value_billions))
                    
                    # Upsert into TimeSeries
                    existing = db.query(TimeSeries).filter(
                        TimeSeries.metric_id == metric.id,
                        TimeSeries.country_id == country.id,
                        TimeSeries.date == date_obj,
                    ).first()
                    
                    if existing:
                        existing.value = value
                        existing.updated_at = datetime.utcnow()
                        total_updated += 1
                    else:
                        db.add(TimeSeries(
                            metric_id=metric.id,
                            country_id=country.id,
                            date=date_obj,
                            value=value,
                        ))
                        total_inserted += 1
                
                except Exception as e:
                    logger.error(f"Error processing {country_name} {date_str}: {e}")
                    errors.append(f"{country_name}: {str(e)}")
            
            db.commit()
            logger.info(f"TIC {country_name}: {len(date_values)} months processed")
        
    except Exception as e:
        logger.error(f"TIC holdings fetch failed: {e}")
        errors.append(str(e))
    
    status = "success" if not errors else "partial"
    db.add(UpdateLog(
        pipeline_name="TIC_Holdings",
        status=status,
        records_inserted=total_inserted,
        records_updated=total_updated,
        error_message="; ".join(errors) if errors else None,
        started_at=start_time,
        completed_at=datetime.utcnow(),
    ))
    db.commit()
    
    logger.info(f"TIC holdings fetch complete: {total_inserted} inserted, {total_updated} updated")
    return {
        "status": status,
        "inserted": total_inserted,
        "updated": total_updated,
        "errors": errors,
    }
