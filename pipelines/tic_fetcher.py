"""
Treasury International Capital (TIC) Holdings Pipeline
-------------------------------------------------------
Fetches monthly US Treasury securities holdings by country from:
https://ticdata.treasury.gov/Publish/mfhhis01.txt

Format: Tab-delimited, repeating year blocks
- Header row: month abbreviations (Dec Nov Oct ... Jan)
- Year row:   Country  YYYY YYYY YYYY ... YYYY
- Data rows:  CountryName  value  value  ...  value
"""

import requests
import logging
from datetime import datetime
from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy import func
from config import settings
from database.models import Metric, TimeSeries, Country, UpdateLog

logger = logging.getLogger(__name__)

TIC_URL = "https://ticdata.treasury.gov/Publish/mfhhis01.txt"

TIC_METRIC = {
    "code": "TIC_HOLDINGS",
    "name": "US Treasury Securities Holdings",
    "category": "holdings",
    "unit": "billions_usd",
    "source": "TIC",
    "description": "Foreign holdings of US Treasury securities by country (TIC data)"
}

# TIC name -> (ISO code, clean name, region)
COUNTRY_MAP = {
    "Japan": ("JPN", "Japan", "Asia"),
    "China, Mainland": ("CHN", "China", "Asia"),
    "United Kingdom": ("GBR", "United Kingdom", "Europe"),
    "Belgium": ("BEL", "Belgium", "Europe"),
    "Luxembourg": ("LUX", "Luxembourg", "Europe"),
    "Cayman Islands": ("CYM", "Cayman Islands", "Caribbean"),
    "Ireland": ("IRL", "Ireland", "Europe"),
    "Switzerland": ("CHE", "Switzerland", "Europe"),
    "France": ("FRA", "France", "Europe"),
    "India": ("IND", "India", "Asia"),
    "Canada": ("CAN", "Canada", "North America"),
    "Taiwan": ("TWN", "Taiwan", "Asia"),
    "Hong Kong": ("HKG", "Hong Kong", "Asia"),
    "Brazil": ("BRA", "Brazil", "South America"),
    "Singapore": ("SGP", "Singapore", "Asia"),
    "Norway": ("NOR", "Norway", "Europe"),
    "Saudi Arabia": ("SAU", "Saudi Arabia", "Middle East"),
    "Korea, South": ("KOR", "South Korea", "Asia"),
    "Germany": ("DEU", "Germany", "Europe"),
    "Netherlands": ("NLD", "Netherlands", "Europe"),
    "United Arab Emirates": ("ARE", "United Arab Emirates", "Middle East"),
    "Thailand": ("THA", "Thailand", "Asia"),
    "Israel": ("ISR", "Israel", "Middle East"),
    "Turkey": ("TUR", "Turkey", "Europe/Asia"),
    "Mexico": ("MEX", "Mexico", "North America"),
    "Sweden": ("SWE", "Sweden", "Europe"),
    "Australia": ("AUS", "Australia", "Oceania"),
    "Poland": ("POL", "Poland", "Europe"),
    "Philippines": ("PHL", "Philippines", "Asia"),
    "Indonesia": ("IDN", "Indonesia", "Asia"),
    "South Africa": ("ZAF", "South Africa", "Africa"),
    "Nigeria": ("NGA", "Nigeria", "Africa"),
    "Egypt": ("EGY", "Egypt", "Africa/Middle East"),
    "Pakistan": ("PAK", "Pakistan", "Asia"),
    "Sri Lanka": ("LKA", "Sri Lanka", "Asia"),
    "Argentina": ("ARG", "Argentina", "South America"),
    "Chile": ("CHL", "Chile", "South America"),
    "Colombia": ("COL", "Colombia", "South America"),
    "Peru": ("PER", "Peru", "South America"),
    "Czech Republic": ("CZE", "Czech Republic", "Europe"),
    "Hungary": ("HUN", "Hungary", "Europe"),
    "Romania": ("ROU", "Romania", "Europe"),
    "Kuwait": ("KWT", "Kuwait", "Middle East"),
    "Qatar": ("QAT", "Qatar", "Middle East"),
    "Iraq": ("IRQ", "Iraq", "Middle East"),
    "Russia": ("RUS", "Russia", "Europe/Asia"),
    "Malaysia": ("MYS", "Malaysia", "Asia"),
    "Vietnam": ("VNM", "Vietnam", "Asia"),
    "Bangladesh": ("BGD", "Bangladesh", "Asia"),
    "Kazakhstan": ("KAZ", "Kazakhstan", "Asia"),
    "Ukraine": ("UKR", "Ukraine", "Europe"),
    "Denmark": ("DNK", "Denmark", "Europe"),
    "Finland": ("FIN", "Finland", "Europe"),
    "Austria": ("AUT", "Austria", "Europe"),
    "Portugal": ("PRT", "Portugal", "Europe"),
    "Spain": ("ESP", "Spain", "Europe"),
    "Italy": ("ITA", "Italy", "Europe"),
    "Greece": ("GRC", "Greece", "Europe"),
    "New Zealand": ("NZL", "New Zealand", "Oceania"),
    "Bermuda": ("BMU", "Bermuda", "Caribbean"),
    "Bahamas": ("BHS", "Bahamas", "Caribbean"),
    "Panama": ("PAN", "Panama", "Central America"),
    "Ecuador": ("ECU", "Ecuador", "South America"),
    "Venezuela": ("VEN", "Venezuela", "South America"),
    "El Salvador": ("SLV", "El Salvador", "Central America"),
}

MONTH_MAP = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4,
    "May": 5, "Jun": 6, "Jul": 7, "Aug": 8,
    "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}


def ensure_tic_metric(db: Session) -> Metric:
    metric = db.query(Metric).filter_by(code=TIC_METRIC["code"]).first()
    if not metric:
        metric = Metric(**TIC_METRIC)
        db.add(metric)
        db.commit()
        logger.info(f"Created metric: {TIC_METRIC['code']}")
    return metric


def ensure_country(db: Session, iso_code: str, name: str, region: str) -> Country:
    country = db.query(Country).filter_by(iso_code=iso_code).first()
    if not country:
        country = Country(iso_code=iso_code, name=name, region=region)
        db.add(country)
        db.commit()
        logger.info(f"Created country: {iso_code} ({name})")
    return country


def fetch_tic_data() -> dict:
    """
    Parse mfhhis01.txt format:

    Block structure (repeats for each year):
        [blank/header lines]
        \t Dec \t Nov \t Oct ... \t Jan \t          <- month row (tab-separated)
        Country \t YYYY \t YYYY ... \t YYYY \t      <- year row
        \t ------ \t ------ ...                     <- separator
        Japan \t 1185.5 \t 1202.7 ...               <- data rows
        ...
        [subtotal rows: Grand Total, For. Official, etc.]

    Returns dict: {(country_name, datetime): value_billions}
    """
    logger.info("Fetching TIC data from Treasury.gov...")
    try:
        response = requests.get(TIC_URL, timeout=30)
        response.raise_for_status()
    except requests.RequestException as e:
        logger.error(f"Failed to fetch TIC data: {e}")
        return {}

    lines = response.text.splitlines()
    holdings = {}

    # We parse in blocks. Each block starts with a month header row.
    # State:
    current_months = []   # list of month ints in column order
    current_years = []    # list of year ints in column order
    current_dates = []    # list of datetime objects in column order

    SKIP_NAMES = {
        "country", "grand total", "of which", "for. official",
        "treasury bills", "t-bonds & notes", "all other", "------",
    }

    for line in lines:
        # Split on tabs
        parts = [p.strip() for p in line.split("\t")]
        # Remove empty leading/trailing
        parts = [p for p in parts if p != ""] if any(p.strip() for p in parts) else []

        if not parts:
            continue

        first = parts[0].lower()

        # ── Month header row ──────────────────────────────────────────────
        # Looks like: ["Dec", "Nov", "Oct", ..., "Jan"]  (first cell blank in raw)
        # After stripping empties, first element is a month abbrev
        if parts[0] in MONTH_MAP:
            current_months = []
            for p in parts:
                if p in MONTH_MAP:
                    current_months.append(MONTH_MAP[p])
            current_years = []   # reset years — will be filled by next year row
            current_dates = []
            continue

        # ── Year header row ───────────────────────────────────────────────
        # Looks like: ["Country", "2025", "2025", ..., "2025"]
        if first == "country" and len(parts) > 1:
            try:
                years = [int(p) for p in parts[1:] if p.isdigit()]
                if years and current_months:
                    current_years = years
                    # Build date list: pair month[i] with year[i]
                    current_dates = []
                    for m, y in zip(current_months, current_years):
                        current_dates.append(datetime(y, m, 1))
            except ValueError:
                pass
            continue

        # ── Skip separator rows ───────────────────────────────────────────
        if all(p.startswith("---") or p == "" for p in parts):
            continue

        # ── Skip known subtotal rows ──────────────────────────────────────
        if any(skip in first for skip in SKIP_NAMES):
            continue

        # ── Data row ──────────────────────────────────────────────────────
        # First element is country name, rest are numeric values
        if not current_dates:
            continue

        country_raw = parts[0].strip('"')  # remove quotes around "China, Mainland"
        values = parts[1:]

        if country_raw not in COUNTRY_MAP:
            continue

        for i, val_str in enumerate(values):
            if i >= len(current_dates):
                break
            val_str = val_str.replace(",", "").strip()
            if not val_str or val_str in ("*", "-", "n/a"):
                continue
            try:
                holdings[(country_raw, current_dates[i])] = Decimal(val_str)
            except Exception:
                pass

    logger.info(f"Parsed {len(holdings)} TIC data points across "
                f"{len(set(c for c, _ in holdings.keys()))} countries")
    return holdings


def compute_stress_scores(db: Session, metric: Metric) -> list:
    """
    Stress leaderboard — countries showing signs of forced selling.

    Score components (max 90 pts):
      - MoM decline magnitude     0–40 pts  (max at -10%)
      - Consecutive decline months 0–30 pts  (max at 6+ months)
      - Acceleration of decline   0–20 pts  (getting worse faster)

    Alert: score >= 25 OR consecutive >= 3
    """
    latest_date = db.query(func.max(TimeSeries.date)).filter(
        TimeSeries.metric_id == metric.id
    ).scalar()

    if not latest_date:
        return []

    countries_with_data = db.query(Country).join(
        TimeSeries, TimeSeries.country_id == Country.id
    ).filter(TimeSeries.metric_id == metric.id).distinct().all()

    scores = []
    for country in countries_with_data:
        from datetime import timedelta
        six_months_ago = latest_date - timedelta(days=185)
        history = db.query(TimeSeries).filter(
            TimeSeries.metric_id == metric.id,
            TimeSeries.country_id == country.id,
            TimeSeries.date >= six_months_ago,
        ).order_by(TimeSeries.date.asc()).all()

        if len(history) < 2:
            continue

        latest_val = float(history[-1].value)
        prev_val = float(history[-2].value)
        if prev_val == 0:
            continue

        mom_pct = (latest_val - prev_val) / prev_val * 100

        # Consecutive declining months
        consecutive = 0
        for i in range(len(history) - 1, 0, -1):
            if float(history[i].value) < float(history[i-1].value):
                consecutive += 1
            else:
                break

        # Acceleration (is decline getting worse?)
        acceleration = 0.0
        if len(history) >= 3:
            prev_prev_val = float(history[-3].value)
            if prev_prev_val != 0:
                mom_prev = (prev_val - prev_prev_val) / prev_prev_val * 100
                acceleration = mom_pct - mom_prev  # negative = accelerating decline

        # Only score countries under stress
        if mom_pct >= 0 and consecutive == 0:
            continue

        stress_score = 0
        if mom_pct < 0:
            stress_score += min(40, abs(mom_pct) * 4)
        stress_score += min(30, consecutive * 5)
        if acceleration < 0:
            stress_score += min(20, abs(acceleration) * 4)

        scores.append({
            "country_iso": country.iso_code,
            "country_name": country.name,
            "region": country.region,
            "latest_holdings_bn": round(latest_val, 2),
            "mom_change_pct": round(mom_pct, 2),
            "consecutive_declining_months": consecutive,
            "acceleration": round(acceleration, 2),
            "stress_score": round(stress_score, 1),
            "alert": stress_score >= 25 or consecutive >= 3,
            "as_of": latest_date.strftime("%Y-%m"),
        })

    return sorted(scores, key=lambda x: x["stress_score"], reverse=True)


def run_tic_fetch(db: Session) -> dict:
    """Main TIC fetch pipeline."""
    from datetime import timedelta
    start_time = datetime.utcnow()
    total_inserted = 0
    total_updated = 0
    errors = []

    try:
        metric = ensure_tic_metric(db)
        holdings = fetch_tic_data()

        if not holdings:
            raise ValueError("No TIC data parsed — check URL or file format")

        for (country_name, date), value in holdings.items():
            if country_name not in COUNTRY_MAP:
                continue

            iso_code, clean_name, region = COUNTRY_MAP[country_name]
            country = ensure_country(db, iso_code, clean_name, region)

            existing = db.query(TimeSeries).filter(
                TimeSeries.metric_id == metric.id,
                TimeSeries.country_id == country.id,
                TimeSeries.date == date,
            ).first()

            if existing:
                existing.value = value
                existing.updated_at = datetime.utcnow()
                total_updated += 1
            else:
                db.add(TimeSeries(
                    metric_id=metric.id,
                    country_id=country.id,
                    date=date,
                    value=value,
                ))
                total_inserted += 1

        db.commit()
        countries_tracked = len(set(
            COUNTRY_MAP[cn][0] for cn, _ in holdings.keys() if cn in COUNTRY_MAP
        ))
        logger.info(f"TIC fetch complete: {total_inserted} inserted, "
                    f"{total_updated} updated across {countries_tracked} countries")

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
            "inserted": total_inserted,
            "updated": total_updated,
            "countries_tracked": countries_tracked,
            "errors": errors,
        }

    except Exception as e:
        logger.error(f"TIC fetch failed: {e}", exc_info=True)
        db.add(UpdateLog(
            pipeline_name="TIC_Holdings",
            status="failed",
            records_inserted=0,
            records_updated=0,
            error_message=str(e),
            started_at=start_time,
            completed_at=datetime.utcnow(),
        ))
        db.commit()
        raise
