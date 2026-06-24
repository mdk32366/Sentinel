"""
Gold Reserves Pipeline + Cross-Asset Stress Scorer
----------------------------------------------------
Imports World Gold Council historical gold reserves CSV and computes
cross-asset stress signals.

CSV format (historical):
  - Wide format: Country | Q4 00 | Q1 01 | Q2 01 | ...
  - Quarterly data back to Q4 2000
  - Values in tonnes, "AWAITED" for unreported

Download from: https://www.gold.org/goldhub/data/gold-reserves-by-country
Save to: C:\projects\sentinel\data\gold_reserves.csv
Re-download monthly to keep current.

SIGNAL HIERARCHY:
  TREASURY_ONLY:  Country selling treasuries (1x)
  CROSS_ASSET:    Selling both treasuries AND gold (1.5x)
  DIVERGENCE:     Selling gold INTO rising spot price (2x) — maximum distress
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
    "description": "Official gold reserves held by central banks (World Gold Council, quarterly)"
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
    "Kyrgyz Republic": "KGZ", "Venezuela": "VEN",
    "Ecuador": "ECU", "Bolivia": "BOL", "Cambodia": "KHM",
    "Sri Lanka": "LKA", "Tunisia": "TUN", "Algeria": "DZA",
    "Nigeria": "NGA", "Tanzania": "TZA", "Kenya": "KEN",
    "Ethiopia": "ETH", "Mozambique": "MOZ", "Zimbabwe": "ZWE",
    "Cameroon": "CMR", "Senegal": "SEN", "Uganda": "UGA",
    "Malta": "MLT", "Cyprus": "CYP", "Albania": "ALB",
    "North Macedonia": "MKD", "Bosnia and Herzegovina": "BIH",
    "Kosovo": "XKX", "Moldova": "MDA", "Tajikistan": "TJK",
    "Turkmenistan": "TKM", "Myanmar": "MMR", "Laos": "LAO",
    "Nepal": "NPL", "Afghanistan": "AFG", "Oman": "OMN",
    "Bahrain": "BHR", "Syria": "SYR", "Lebanon": "LBN",
    "Libya": "LBY", "Sudan": "SDN", "Mauritius": "MUS",
    "Guatemala": "GTM", "Costa Rica": "CRI", "El Salvador": "SLV",
    "Honduras": "HND", "Nicaragua": "NIC", "Panama": "PAN",
    "Paraguay": "PRY", "Uruguay": "URY",
}


def parse_quarter(q_str: str) -> datetime:
    """
    Parse quarter string like 'Q4 00', 'Q1 26' into first-of-quarter datetime.
    Q1 = Jan, Q2 = Apr, Q3 = Jul, Q4 = Oct
    """
    parts = q_str.strip().split()
    quarter = int(parts[0][1])  # Q1 -> 1
    year_2d = int(parts[1])
    year = 2000 + year_2d if year_2d <= 99 else year_2d
    month = {1: 1, 2: 4, 3: 7, 4: 10}[quarter]
    return datetime(year, month, 1)


def ensure_gold_metric(db: Session) -> Metric:
    metric = db.query(Metric).filter_by(code=GOLD_METRIC["code"]).first()
    if not metric:
        metric = Metric(**GOLD_METRIC)
        db.add(metric)
        db.commit()
        logger.info("Created metric: GOLD_RESERVES")
    return metric


def get_spot_gold_trend(db: Session, months: int = 3) -> dict:
    """Get recent spot gold price trend."""
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
    month_ago = float(history[max(0, len(history)-22)].value)
    start = float(history[0].value)

    mom_pct = (latest - month_ago) / month_ago * 100 if month_ago else None
    trend_3m_pct = (latest - start) / start * 100 if start else None

    return {
        "latest_price": round(latest, 2),
        "mom_pct": round(mom_pct, 2) if mom_pct else None,
        "trend_3m_pct": round(trend_3m_pct, 2) if trend_3m_pct else None,
        "rising": trend_3m_pct > 2 if trend_3m_pct is not None else None,
    }


def import_wgc_csv(db: Session, csv_path: Path = CSV_PATH) -> dict:
    """
    Import WGC historical gold reserves CSV.

    Format: Wide, Country × Quarter (Q4 00 → Q1 26)
    Values: tonnes or "AWAITED"
    """
    if not csv_path.exists():
        raise FileNotFoundError(
            f"Gold reserves CSV not found at {csv_path}\n"
            f"Download from: https://www.gold.org/goldhub/data/gold-reserves-by-country\n"
            f"Save as: {csv_path}"
        )

    metric = ensure_gold_metric(db)
    inserted = updated = skipped = 0

    with open(csv_path, newline='', encoding='utf-8-sig') as f:
        reader = csv.reader(f)
        headers = next(reader)

        # Parse quarter dates for all columns
        quarter_dates = []
        for h in headers[1:]:
            try:
                quarter_dates.append(parse_quarter(h))
            except Exception:
                quarter_dates.append(None)

        for row in reader:
            if not row:
                continue
            country_name = row[0].strip()
            iso_code = WGC_COUNTRY_MAP.get(country_name)
            if not iso_code:
                logger.debug(f"No ISO mapping for: {country_name}")
                skipped += 1
                continue

            country = db.query(Country).filter_by(iso_code=iso_code).first()
            if not country:
                skipped += 1
                continue

            for i, value_str in enumerate(row[1:]):
                if i >= len(quarter_dates) or quarter_dates[i] is None:
                    continue
                value_str = value_str.strip()
                if not value_str or value_str == 'AWAITED':
                    continue
                try:
                    tonnes = Decimal(value_str)
                except Exception:
                    continue

                if tonnes < 0:
                    continue

                date = quarter_dates[i]
                existing = db.query(TimeSeries).filter(
                    TimeSeries.metric_id == metric.id,
                    TimeSeries.country_id == country.id,
                    TimeSeries.date == date,
                ).first()

                if existing:
                    existing.value = tonnes
                    existing.updated_at = datetime.utcnow()
                    updated += 1
                else:
                    db.add(TimeSeries(
                        metric_id=metric.id,
                        country_id=country.id,
                        date=date,
                        value=tonnes,
                    ))
                    inserted += 1

    db.commit()
    logger.info(f"WGC historical import: {inserted} inserted, {updated} updated, {skipped} countries skipped")
    return {
        "status": "success",
        "inserted": inserted,
        "updated": updated,
        "skipped": skipped,
        "note": "Quarterly data Q4 2000 to present",
    }


def compute_cross_asset_stress(db: Session) -> list:
    """
    Three-tier cross-asset stress scoring:
      TIER 1 TREASURY_ONLY:  selling treasuries (1x)
      TIER 2 CROSS_ASSET:    selling treasuries + gold (1.5x)
      TIER 3 DIVERGENCE:     selling gold INTO rising spot price (2x)
    """
    tic_metric = db.query(Metric).filter_by(code="TIC_UST_HOLDINGS").first()
    gold_metric = db.query(Metric).filter_by(code="GOLD_RESERVES").first()

    if not tic_metric or not gold_metric:
        return []

    tic_latest = db.query(func.max(TimeSeries.date)).filter(
        TimeSeries.metric_id == tic_metric.id).scalar()
    gold_latest = db.query(func.max(TimeSeries.date)).filter(
        TimeSeries.metric_id == gold_metric.id).scalar()

    if not tic_latest or not gold_latest:
        return []

    spot = get_spot_gold_trend(db, months=3)
    spot_rising = spot.get("rising")

    results = []
    for country in db.query(Country).all():
        tic_hist = db.query(TimeSeries).filter(
            TimeSeries.metric_id == tic_metric.id,
            TimeSeries.country_id == country.id,
            TimeSeries.date >= tic_latest - timedelta(days=185),
        ).order_by(TimeSeries.date.asc()).all()

        # Gold: use last 4 quarters for trend
        gold_hist = db.query(TimeSeries).filter(
            TimeSeries.metric_id == gold_metric.id,
            TimeSeries.country_id == country.id,
            TimeSeries.date >= gold_latest - timedelta(days=400),
        ).order_by(TimeSeries.date.asc()).all()

        if len(gold_hist) < 1:
            continue

        gold_tonnes = float(gold_hist[-1].value)
        gold_mom = None
        gold_consec = 0
        if len(gold_hist) >= 2:
            gold_prev = float(gold_hist[-2].value)
            if gold_prev > 0:
                gold_mom = (gold_tonnes - gold_prev) / gold_prev * 100
                gold_consec = sum(1 for i in range(len(gold_hist)-1, 0, -1)
                                  if float(gold_hist[i].value) < float(gold_hist[i-1].value))

        selling_gold = (gold_mom is not None and gold_mom < -0.5) or gold_consec >= 2

        # ── EXITED TIER: zero TIC holdings + significant gold ─────────────────
        # Completed liquidation is the most severe de-dollarization signal.
        # Requires: no TIC history AND gold reserves > 50t
        no_tic = len(tic_hist) == 0
        if no_tic:
            if gold_tonnes < 50:
                continue  # Skip — small gold holder, not analytically significant

            score = 50  # Base penalty for completed liquidation
            if gold_tonnes > 500:
                score += 20  # Large gold holder amplifies signal
            if selling_gold:
                score += 20  # Also selling gold = maximum stress
            if selling_gold and spot_rising:
                multiplier = 2.0
                signal_tier = "DIVERGENCE"
            elif selling_gold:
                multiplier = 1.5
                signal_tier = "EXITED+GOLD_SELL"
            else:
                multiplier = 1.0
                signal_tier = "EXITED"

            # ── TRESEG: non-dollar reserve trend for EXITED countries ─────
            try:
                from pipelines.experimental.composite_stress import get_treseg_signal
                treseg = get_treseg_signal(db, country.iso_code, True)
            except Exception:
                treseg = {"signal": "NO_DATA", "trend_pct": None, "latest_bn": None}

            # Boost score if rebuilding in alternative currencies
            if treseg["signal"] == "REBUILDING":
                score = min(score * 1.2, 150)

            results.append({
                "country_iso": country.iso_code,
                "country_name": country.name,
                "region": country.region,
                "tic_holdings_bn": 0.0,
                "tic_mom_pct": None,
                "tic_consecutive_months": 0,
                "no_tic_holdings": True,
                "gold_tonnes": round(gold_tonnes, 1),
                "gold_mom_pct": round(gold_mom, 2) if gold_mom is not None else None,
                "gold_consecutive_months": gold_consec,
                "treseg_signal": treseg["signal"],
                "treseg_trend_pct": treseg["trend_pct"],
                "treseg_latest_bn": treseg["latest_bn"],
                "spot_gold_price": spot.get("latest_price"),
                "spot_gold_3m_pct": spot.get("trend_3m_pct"),
                "spot_gold_rising": spot_rising,
                "selling_treasuries": False,
                "selling_gold": selling_gold,
                "cross_asset_stress": False,
                "divergence_signal": selling_gold and spot_rising,
                "signal_tier": signal_tier,
                "score_before_multiplier": round(score, 1),
                "multiplier": multiplier,
                "stress_score": round(score * multiplier, 1),
                "alert": True,
                "tic_as_of": tic_latest.strftime("%Y-%m"),
                "gold_as_of": gold_latest.strftime("%Y-%m"),
            })
            continue

        # ── Standard path: active TIC holders ────────────────────────────────
        if len(tic_hist) < 2:
            continue

        tic_prev = float(tic_hist[-2].value)
        if tic_prev == 0:
            continue
        tic_mom = (float(tic_hist[-1].value) - tic_prev) / tic_prev * 100
        tic_consec = sum(1 for i in range(len(tic_hist)-1, 0, -1)
                         if float(tic_hist[i].value) < float(tic_hist[i-1].value))

        selling_tic = tic_mom < -0.5 or tic_consec >= 2

        if not (selling_tic or selling_gold):
            continue

        cross_asset = selling_tic and selling_gold
        divergence = cross_asset and spot_rising

        score = 0
        if tic_mom < 0:
            score += min(30, abs(tic_mom) * 3)
        score += min(20, tic_consec * 4)
        if gold_mom is not None and gold_mom < 0:
            score += min(30, abs(gold_mom) * 3)
        score += min(20, gold_consec * 4)

        if divergence:
            multiplier = 2.0
            signal_tier = "DIVERGENCE"
        elif cross_asset:
            multiplier = 1.5
            signal_tier = "CROSS_ASSET"
        else:
            multiplier = 1.0
            signal_tier = "TREASURY_ONLY" if selling_tic else "GOLD_ONLY"

        # ── TRESEG: non-dollar reserve trend ──────────────────────────────
        try:
            from pipelines.experimental.composite_stress import get_treseg_signal
            treseg = get_treseg_signal(db, country.iso_code, False)
        except Exception:
            treseg = {"signal": "NO_DATA", "trend_pct": None, "latest_bn": None}

        results.append({
            "country_iso": country.iso_code,
            "country_name": country.name,
            "region": country.region,
            "tic_holdings_bn": round(float(tic_hist[-1].value), 2),
            "tic_mom_pct": round(tic_mom, 2),
            "tic_consecutive_months": tic_consec,
            "no_tic_holdings": False,
            "gold_tonnes": round(gold_tonnes, 1),
            "gold_mom_pct": round(gold_mom, 2) if gold_mom is not None else None,
            "gold_consecutive_months": gold_consec,
            "treseg_signal": treseg["signal"],
            "treseg_trend_pct": treseg["trend_pct"],
            "treseg_latest_bn": treseg["latest_bn"],
            "spot_gold_price": spot.get("latest_price"),
            "spot_gold_3m_pct": spot.get("trend_3m_pct"),
            "spot_gold_rising": spot_rising,
            "selling_treasuries": selling_tic,
            "selling_gold": selling_gold,
            "cross_asset_stress": cross_asset,
            "divergence_signal": divergence,
            "signal_tier": signal_tier,
            "score_before_multiplier": round(score, 1),
            "multiplier": multiplier,
            "stress_score": round(score * multiplier, 1),
            "alert": divergence or cross_asset or (score * multiplier) >= 30,
            "tic_as_of": tic_latest.strftime("%Y-%m"),
            "gold_as_of": gold_latest.strftime("%Y-%m"),
        })

    return sorted(results,
                  key=lambda x: (x["divergence_signal"] or False, x["cross_asset_stress"] or False, x["stress_score"] or 0),
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
