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

logger = logging.getLogger(__name__)

TIC_MFH_URL = "https://ticdata.treasury.gov/Publish/mfhhis01.txt"

MONTH_ABBR_SET = {"Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"}

SKIP_ROWS = {
    "All Other", "Grand Total", "For. Official",
    "Treasury Bills", "T-Bonds & Notes", "Of which:",
    "Country",
}

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
    "Korea, South": "KOR",
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
    "Bermuda": "BMU",
    "El Salvador": "SLV",
    "Kuwait": "KWT",
    "Poland": "POL",
    "Colombia": "COL",
    "Peru": "PER",
}


def ensure_metric(db: Session) -> Metric:
    metric = db.query(Metric).filter_by(code="TIC_UST_HOLDINGS").first()
    if not metric:
        metric = Metric(
            code="TIC_UST_HOLDINGS",
            name="Foreign Holdings of US Treasury Securities",
            category="holdings",
            unit="billions_usd",
            source="TIC",
            description="Foreign holdings of US Treasury securities by country (billions USD)",
        )
        db.add(metric)
        db.commit()
        logger.info("Created metric: TIC_UST_HOLDINGS")
    return metric


def ensure_country(db: Session, iso_code: str, country_name: str) -> Country:
    country = db.query(Country).filter_by(iso_code=iso_code).first()
    if not country:
        country = Country(iso_code=iso_code, name=country_name)
        db.add(country)
        db.commit()
        logger.info(f"Created country: {iso_code} ({country_name})")
    return country


def fetch_tic_mfh_data() -> str:
    r = requests.get(TIC_MFH_URL, timeout=30)
    r.raise_for_status()
    return r.text


def parse_tic_mfh(text: str) -> dict:
    """
    Parse the tab-delimited TIC MFH file.
    Structure:
      - Leading header rows (ignore)
      - Month row: \tDec\tNov\t... (first col blank)
      - Year row: Country\t2025\t2025\t...
      - Separator row: \t------\t...
      - Data rows: Japan\t1185.5\t...
      - Summary rows: Grand Total\t... (skipped)
      - Repeats for prior years

    Returns: {country_name: {date_str: value_billions}}
    """
    result = {}
    # Normalise line endings
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")

    current_dates = []
    pending_months = []

    for line in lines:
        cols = [c.strip() for c in line.split("\t")]
        non_empty = [c for c in cols if c and c != "------"]

        if not non_empty:
            continue

        # Month header row: first col blank, first non-empty value is a month abbr
        if cols[0] == "" and non_empty[0] in MONTH_ABBR_SET:
            pending_months = [c for c in non_empty if c in MONTH_ABBR_SET]
            continue

        # Year row: first col is "Country", rest are 4-digit years
        if cols[0] == "Country" and pending_months:
            years = [c for c in non_empty if c.isdigit() and len(c) == 4]
            if years:
                current_dates = [f"{m} {y}" for m, y in zip(pending_months, years)]
            pending_months = []
            continue

        # Country data row
        country = cols[0].strip('"').strip()
        if (not country
                or country in SKIP_ROWS
                or "---" in country
                or "HOLDINGS" in country
                or "billions" in country
                or "AT END" in country
                or "MAJOR" in country):
            continue

        if not current_dates:
            continue

        # Parse numeric values
        values = []
        for c in cols[1:]:
            if not c or c == "------":
                continue
            try:
                values.append(float(c))
            except ValueError:
                continue

        if values:
            if country not in result:
                result[country] = {}
            for date_str, val in zip(current_dates[:len(values)], values):
                result[country][date_str] = val

    logger.info(f"Parsed {len(result)} countries from TIC MFH data")
    return result


def run_treasury_holdings_fetch(db: Session) -> dict:
    """Main TIC holdings fetch pipeline."""
    start_time = datetime.utcnow()
    total_inserted = 0
    total_updated = 0
    errors = []
    countries_loaded = 0

    try:
        tic_text = fetch_tic_mfh_data()
        holdings_by_country = parse_tic_mfh(tic_text)

        if not holdings_by_country:
            raise ValueError("No holdings data parsed from TIC file — format may have changed")

        metric = ensure_metric(db)

        for country_name, date_values in holdings_by_country.items():
            iso_code = COUNTRY_MAPPING.get(country_name)
            if not iso_code:
                logger.debug(f"Skipping {country_name!r} — no ISO mapping")
                continue

            country = ensure_country(db, iso_code, country_name)
            countries_loaded += 1

            for date_str, value_billions in date_values.items():
                try:
                    date_obj = datetime.strptime(f"01 {date_str}", "%d %b %Y")
                    value = Decimal(str(value_billions))

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
                    errors.append(f"{country_name}/{date_str}: {str(e)}")

            db.commit()

        logger.info(
            f"TIC holdings: {countries_loaded} countries, "
            f"{total_inserted} inserted, {total_updated} updated"
        )

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

    return {
        "status": status,
        "countries": countries_loaded,
        "inserted": total_inserted,
        "updated": total_updated,
        "errors": errors,
    }
