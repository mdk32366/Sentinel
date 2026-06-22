"""
Gold Reserves Pipeline + Cross-Asset Stress Scorer
----------------------------------------------------
Imports World Gold Council gold reserves CSV and computes cross-asset
stress signals combining treasury holdings, gold reserves, and spot gold price.

SIGNAL HIERARCHY:
  Base:           Country selling treasuries OR gold
  Cross-asset:    Country selling BOTH treasuries AND gold (1.5x multiplier)
  Divergence:     Selling gold reserves INTO rising spot price (2x multiplier)
                  → Strongest possible distress signal. Country is a forced
                    seller even when gold is at peak value. They need cash NOW.

Download CSV monthly from:
  https://www.gold.org/goldhub/data/gold-reserves-by-country
Save to: C:\projects\sentinel\data\gold_reserves.csv
"""

import csv
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from sqlalchemy.orm import Session
from sqlalchemy import func
from database.models import Metric, TimeSeries, Country, UpdateLog

logger = logging.getLogger(__name__)

CSV_PATH = Path(__file__).parent.parent / "data" / "gold_reserves.csv"

GOLD_METRIC = {
    "code": "GOLD_RESERVES",
    "name": "Central Bank Gold Reserves",
    "category": "gold",
    "unit": "tonnes",
    "source": "WGC",
    "description": "Official gold reserves held by central banks (World Gold Council)"
}

WGC_COUNTRY_MAP = {
    "United States of America": "USA", "United States": "USA",
    "Germany": "DEU", "Italy": "ITA", "France": "FRA",
    "Russian Federation": "RUS", "Russia": "RUS",
    "China": "CHN", "China, Mainland": "CHN",
    "Switzerland": "CHE", "Japan": "JPN", "India": "IND",
    "Netherlands": "NLD", "Turkey": "TUR", "Türkiye": "TUR",
    "Taiwan": "TWN", "Portugal": "PRT", "Kazakhstan": "KAZ",
    "Uzbekistan": "UZB", "Saudi Arabia": "SAU",
    "United Kingdom": "GBR", "Spain": "ESP", "Austria": "AUT",
    "Belgium": "BEL", "Poland": "POL", "Philippines": "PHL",
    "Thailand": "THA", "Singapore": "SGP", "Sweden": "SWE",
    "South Africa": "ZAF", "Mexico": "MEX", "Libya": "LBY",
    "Greece": "GRC", "South Korea": "KOR", "Korea, Republic of": "KOR",
    "Romania": "ROU", "Iraq": "IRQ", "Czechia": "CZE",
    "Czech Republic": "CZE", "Egypt": "EGY", "Brazil": "BRA",
    "Hungary": "HUN", "Australia": "AUS", "Belarus": "BLR",
    "Denmark": "DNK", "Pakistan": "PAK", "Slovakia": "SVK",
    "Finland": "FIN", "Bulgaria": "BGR", "Norway": "NOR",
    "Malaysia": "MYS", "Indonesia": "IDN", "Argentina": "ARG",
    "Ukraine": "UKR", "Canada": "CAN", "Qatar": "QAT",
    "Kuwait": "KWT", "Serbia": "SRB", "Latvia": "LVA",
    "Lithuania": "LTU", "Bangladesh": "BGD", "Peru": "PER",
    "Colombia": "COL", "Chile": "CHL", "Israel": "ISR",
    "United Arab Emirates": "ARE", "Iceland": "ISL",
    "Ireland": "IRL", "Luxembourg": "LUX", "Croatia": "HRV",
    "Slovenia": "SVN", "Estonia": "EST", "Armenia": "ARM",
    "Georgia": "GEO", "Azerbaijan": "AZE", "Mongolia": "MNG",
    "Kyrgyzstan": "KGZ", "Morocco": "MAR", "Vietnam": "VNM",
    "New Zealand": "NZL", "Jordan": "JOR", "Ghana": "GHA",
}


def ensure_gold_metric(db: Session) -> Metric:
    metric = db.query(Metric).filter_by(code=GOLD_METRIC["code"]).first()
    if not metric:
        metric = Metric(**GOLD_METRIC)
        db.add(metric)
        db.commit()
        logger.info("Created metric: GOLD_RESERVES")
    return metric


def get_spot_gold_trend(db: Session, months: int = 3) -> dict:
    """
    Get recent spot gold price trend from FRED data.
    Returns: {latest_price, mom_pct, trend_3m_pct, rising}
    """
    gold_price_metric = db.query(Metric).filter_by(code="GOLD_SPOT_USD").first()
    if not gold_price_metric:
        return {"latest_price": None, "mom_pct": None, "trend_3m_pct": None, "rising": None}

    cutoff = datetime.utcnow() - timedelta(days=months * 31)
    history = db.query(TimeSeries).filter(
        TimeSeries.metric_id == gold_price_metric.id,
        TimeSeries.country_id == None,
        TimeSeries.date >= cutoff,
    ).order_by(TimeSeries.date.asc()).all()

    if len(history) < 2:
        return {"latest_price": None, "mom_pct": None, "trend_3m_pct": None, "rising": None}

    latest = float(history[-1].value)
    month_ago = float(history[max(0, len(history)-22)].value)  # ~1 month of trading days
    start = float(history[0].value)

    mom_pct = (latest - month_ago) / month_ago * 100 if month_ago else None
    trend_3m_pct = (latest - start) / start * 100 if start else None

    return {
        "latest_price": round(latest, 2),
        "mom_pct": round(mom_pct, 2) if mom_pct else None,
        "trend_3m_pct": round(trend_3m_pct, 2) if trend_3m_pct else None,
        "rising": trend_3m_pct > 2 if trend_3m_pct is not None else None,
    }


def import_wgc_csv(db: Session, csv_path: Path = CSV_PATH,
                   as_of_date: datetime = None) -> dict:
    """Import WGC gold reserves snapshot CSV."""
    if not csv_path.exists():
        raise FileNotFoundError(
            f"Gold reserves CSV not found at {csv_path}\n"
            f"Download from: https://www.gold.org/goldhub/data/gold-reserves-by-country\n"
            f"Save as: {csv_path}"
        )

    if as_of_date is None:
        now = datetime.utcnow()
        as_of_date = datetime(now.year, now.month, 1)

    metric = ensure_gold_metric(db)
    inserted = updated = skipped = 0

    with open(csv_path, newline='', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            country_name = row.get('Country', '').strip()
            tonnes_str = row.get('Gold Reserves Tonnes', '').strip()

            if not tonnes_str or tonnes_str == 'AWAITED':
                skipped += 1
                continue
            try:
                tonnes = Decimal(tonnes_str)
            except Exception:
                skipped += 1
                continue

            if tonnes <= 0:
                skipped += 1
                continue

            iso_code = WGC_COUNTRY_MAP.get(country_name)
            if not iso_code:
                logger.debug(f"No ISO mapping for: {country_name}")
                skipped += 1
                continue

            country = db.query(Country).filter_by(iso_code=iso_code).first()
            if not country:
                skipped += 1
                continue

            existing = db.query(TimeSeries).filter(
                TimeSeries.metric_id == metric.id,
                TimeSeries.country_id == country.id,
                TimeSeries.date == as_of_date,
            ).first()

            if existing:
                existing.value = tonnes
                existing.updated_at = datetime.utcnow()
                updated += 1
            else:
                db.add(TimeSeries(
                    metric_id=metric.id,
                    country_id=country.id,
                    date=as_of_date,
                    value=tonnes,
                ))
                inserted += 1

    db.commit()
    logger.info(f"WGC import: {inserted} inserted, {updated} updated, {skipped} skipped")
    return {
        "status": "success",
        "inserted": inserted,
        "updated": updated,
        "skipped": skipped,
        "as_of": as_of_date.strftime("%Y-%m"),
    }


def compute_cross_asset_stress(db: Session) -> list:
    """
    Cross-asset stress scoring with three signal tiers:

    TIER 1 — Treasury stress only (base score)
    TIER 2 — Treasury + gold reserves selling (1.5x multiplier)
    TIER 3 — Treasury + gold reserves selling INTO rising spot price (2x multiplier)
              The divergence signal: selling gold at peak prices = forced seller

    Score components:
      TIC MoM decline magnitude   0–30 pts
      TIC consecutive months      0–20 pts
      Gold MoM decline magnitude  0–30 pts
      Gold consecutive months     0–20 pts
      Max base: 100 pts
      Cross-asset multiplier: 1.5x
      Divergence multiplier: 2.0x (overrides 1.5x)
    """
    tic_metric = db.query(Metric).filter_by(code="TIC_HOLDINGS").first()
    gold_metric = db.query(Metric).filter_by(code="GOLD_RESERVES").first()

    if not tic_metric or not gold_metric:
        return []

    tic_latest = db.query(func.max(TimeSeries.date)).filter(
        TimeSeries.metric_id == tic_metric.id).scalar()
    gold_latest = db.query(func.max(TimeSeries.date)).filter(
        TimeSeries.metric_id == gold_metric.id).scalar()

    if not tic_latest or not gold_latest:
        return []

    # Get spot gold trend once — applies to all countries
    spot = get_spot_gold_trend(db, months=3)
    spot_rising = spot.get("rising")

    results = []
    for country in db.query(Country).all():
        # TIC history
        tic_hist = db.query(TimeSeries).filter(
            TimeSeries.metric_id == tic_metric.id,
            TimeSeries.country_id == country.id,
            TimeSeries.date >= tic_latest - timedelta(days=185),
        ).order_by(TimeSeries.date.asc()).all()

        # Gold history
        gold_hist = db.query(TimeSeries).filter(
            TimeSeries.metric_id == gold_metric.id,
            TimeSeries.country_id == country.id,
            TimeSeries.date >= gold_latest - timedelta(days=185),
        ).order_by(TimeSeries.date.asc()).all()

        if len(tic_hist) < 2 or len(gold_hist) < 1:
            continue

        # TIC metrics
        tic_prev = float(tic_hist[-2].value)
        if tic_prev == 0:
            continue
        tic_mom = (float(tic_hist[-1].value) - tic_prev) / tic_prev * 100
        tic_consec = sum(1 for i in range(len(tic_hist)-1, 0, -1)
                         if float(tic_hist[i].value) < float(tic_hist[i-1].value))

        # Gold metrics
        gold_tonnes = float(gold_hist[-1].value)
        gold_mom = None
        gold_consec = 0
        if len(gold_hist) >= 2:
            gold_prev = float(gold_hist[-2].value)
            if gold_prev > 0:
                gold_mom = (gold_tonnes - gold_prev) / gold_prev * 100
                gold_consec = sum(1 for i in range(len(gold_hist)-1, 0, -1)
                                  if float(gold_hist[i].value) < float(gold_hist[i-1].value))

        selling_tic = tic_mom < -0.5 or tic_consec >= 2
        selling_gold = (gold_mom is not None and gold_mom < -0.5) or gold_consec >= 2

        if not (selling_tic or selling_gold):
            continue

        # Base score
        score = 0
        if tic_mom < 0:
            score += min(30, abs(tic_mom) * 3)
        score += min(20, tic_consec * 4)
        if gold_mom is not None and gold_mom < 0:
            score += min(30, abs(gold_mom) * 3)
        score += min(20, gold_consec * 4)

        # Signal tier and multiplier
        cross_asset = selling_tic and selling_gold
        divergence = cross_asset and spot_rising  # selling gold INTO rising prices

        if divergence:
            multiplier = 2.0
            signal_tier = "DIVERGENCE"
        elif cross_asset:
            multiplier = 1.5
            signal_tier = "CROSS_ASSET"
        else:
            multiplier = 1.0
            signal_tier = "TREASURY_ONLY" if selling_tic else "GOLD_ONLY"

        final_score = score * multiplier

        results.append({
            "country_iso": country.iso_code,
            "country_name": country.name,
            "region": country.region,
            # Treasury data
            "tic_holdings_bn": round(float(tic_hist[-1].value), 2),
            "tic_mom_pct": round(tic_mom, 2),
            "tic_consecutive_months": tic_consec,
            # Gold reserves data
            "gold_tonnes": round(gold_tonnes, 1),
            "gold_mom_pct": round(gold_mom, 2) if gold_mom is not None else None,
            "gold_consecutive_months": gold_consec,
            # Spot gold context
            "spot_gold_price": spot.get("latest_price"),
            "spot_gold_3m_pct": spot.get("trend_3m_pct"),
            "spot_gold_rising": spot_rising,
            # Signal classification
            "selling_treasuries": selling_tic,
            "selling_gold": selling_gold,
            "cross_asset_stress": cross_asset,
            "divergence_signal": divergence,
            "signal_tier": signal_tier,
            "score_before_multiplier": round(score, 1),
            "multiplier": multiplier,
            "stress_score": round(final_score, 1),
            "alert": divergence or cross_asset or final_score >= 30,
            "tic_as_of": tic_latest.strftime("%Y-%m"),
            "gold_as_of": gold_latest.strftime("%Y-%m"),
        })

    return sorted(results,
                  key=lambda x: (x["divergence_signal"], x["cross_asset_stress"], x["stress_score"]),
                  reverse=True)


def run_gold_fetch(db: Session) -> dict:
    """Main entry point — called by /api/fetch/gold route."""
    start_time = datetime.utcnow()
    try:
        result = import_wgc_csv(db)
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
        return result
    except Exception as e:
        logger.error(f"Gold import failed: {e}")
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
        raise

