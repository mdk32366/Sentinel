"""
Composite Sovereign Stress Scorer
------------------------------------
Four-dimension scoring system:

  DIMENSION 1 — Treasury (0-50 pts)
    MoM decline magnitude:    0-30 pts (scaled)
    Consecutive months:       0-20 pts (4 pts each, cap 5 months)

  DIMENSION 2 — Gold Reserves (0-40 pts)
    QoQ decline magnitude:    0-20 pts (scaled)
    Consecutive quarters:     0-20 pts (4 pts each, cap 5 quarters)

  DIMENSION 3 — Monetary / M2 (0-35 pts)
    >15% YoY M2 growth:       10 pts
    >30% YoY M2 growth:       20 pts
    >50% YoY M2 growth:       35 pts

  DIMENSION 4 — Sovereign Spread (0-15 pts)  ← NEW
    Spread >50bps vs US 10Y:   5 pts  (mild risk premium)
    Spread >100bps vs US 10Y: 10 pts  (elevated)
    Spread >200bps vs US 10Y: 15 pts  (significant stress)
    Spread widening >30bps in 3M: +5 pts (trend component)

MULTIPLIERS (applied to raw sum):
  Cross-asset (selling both T + gold):    1.5x
  Divergence (selling gold into rising):  2.0x

TIERS:
  WATCH:    score < 25
  ELEVATED: 25 ≤ score < 50
  STRESSED: 50 ≤ score < 75
  CRISIS:   score ≥ 75

Sovereign spreads map (ISO → FRED code for 10Y gov bond yield):
  Only OECD countries have data on FRED. EM countries won't have a spread
  component but will score on the other three dimensions.
"""

import logging
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func
from database.models import Metric, TimeSeries, Country

logger = logging.getLogger(__name__)

# FRED codes for 10Y government bond yields (OECD monthly series)
SOVEREIGN_YIELD_CODES = {
    "JPN": "IRLTLT01JPM156N",
    "DEU": "IRLTLT01DEM156N",
    "ITA": "IRLTLT01ITM156N",
    "FRA": "IRLTLT01FRM156N",
    "ESP": "IRLTLT01ESM156N",
    "GBR": "IRLTLT01GBM156N",
    "AUS": "IRLTLT01AUM156N",
    "CAN": "IRLTLT01CAM156N",
}


def get_us_10y_yield(db: Session) -> float | None:
    """Get latest US 10Y yield from DB."""
    metric = db.query(Metric).filter_by(code="DGS10").first()
    if not metric:
        return None
    latest = db.query(TimeSeries).filter(
        TimeSeries.metric_id == metric.id,
        TimeSeries.country_id == None,
    ).order_by(TimeSeries.date.desc()).first()
    return float(latest.value) if latest else None


def get_sovereign_spread(db: Session, iso: str, us_10y: float | None) -> dict:
    """
    Get sovereign bond yield spread vs US 10Y for a given country.
    Returns: {spread_bps, spread_3m_ago_bps, widening, score}
    """
    if us_10y is None or iso not in SOVEREIGN_YIELD_CODES:
        return {"spread_bps": None, "widening_bps": None, "score": 0}

    fred_code = SOVEREIGN_YIELD_CODES[iso]
    metric = db.query(Metric).filter_by(code=fred_code).first()
    if not metric:
        return {"spread_bps": None, "widening_bps": None, "score": 0}

    cutoff_3m = datetime.utcnow() - timedelta(days=120)
    history = db.query(TimeSeries).filter(
        TimeSeries.metric_id == metric.id,
        TimeSeries.country_id == None,
        TimeSeries.date >= cutoff_3m,
    ).order_by(TimeSeries.date.asc()).all()

    if not history:
        return {"spread_bps": None, "widening_bps": None, "score": 0}

    latest_yield = float(history[-1].value)
    spread_bps = (latest_yield - us_10y) * 100

    # 3-month trend: compare current spread to spread 3 months ago
    widening_bps = None
    if len(history) >= 2:
        old_yield = float(history[0].value)
        old_spread = (old_yield - us_10y) * 100
        widening_bps = spread_bps - old_spread  # positive = widening

    # Score: only fires if spread is POSITIVE (country paying more than US)
    # Negative spread = country yields LESS than US = no credit stress signal
    score = 0
    if spread_bps > 200:
        score = 15
    elif spread_bps > 100:
        score = 10
    elif spread_bps > 50:
        score = 5

    # Widening trend bonus — fires regardless of level
    if widening_bps is not None and widening_bps > 30:
        score += 5

    return {
        "spread_bps": round(spread_bps, 1),
        "widening_bps": round(widening_bps, 1) if widening_bps is not None else None,
        "score": min(score, 20),  # cap at 20 to prevent spread from dominating
    }


def get_spot_gold_trend(db: Session, months: int = 3) -> dict:
    """Get recent spot gold price trend."""
    gold_metric = db.query(Metric).filter_by(code="GOLD_SPOT_USD").first()
    if not gold_metric:
        return {"latest_price": None, "trend_3m_pct": None, "rising": None}

    cutoff = datetime.utcnow() - timedelta(days=months * 31)
    history = db.query(TimeSeries).filter(
        TimeSeries.metric_id == gold_metric.id,
        TimeSeries.country_id == None,
        TimeSeries.date >= cutoff,
    ).order_by(TimeSeries.date.asc()).all()

    if len(history) < 2:
        return {"latest_price": None, "trend_3m_pct": None, "rising": None}

    latest = float(history[-1].value)
    start = float(history[0].value)
    trend_3m_pct = (latest - start) / start * 100 if start else None

    return {
        "latest_price": round(latest, 2),
        "trend_3m_pct": round(trend_3m_pct, 2) if trend_3m_pct is not None else None,
        "rising": trend_3m_pct > 2 if trend_3m_pct is not None else None,
    }


def compute_composite_stress(db: Session) -> dict:
    """
    Compute four-dimension composite stress scores for all countries.
    Returns structured dict with tiers and summary.
    """
    tic_metric = db.query(Metric).filter_by(code="TIC_HOLDINGS").first()
    gold_metric = db.query(Metric).filter_by(code="GOLD_RESERVES").first()
    m2_metric = db.query(Metric).filter_by(code="BROAD_MONEY_GROWTH").first()

    if not tic_metric:
        return {"error": "No TIC data loaded"}

    tic_latest = db.query(func.max(TimeSeries.date)).filter(
        TimeSeries.metric_id == tic_metric.id).scalar()
    if not tic_latest:
        return {"error": "No TIC data points"}

    gold_latest = None
    if gold_metric:
        gold_latest = db.query(func.max(TimeSeries.date)).filter(
            TimeSeries.metric_id == gold_metric.id).scalar()

    spot = get_spot_gold_trend(db, months=3)
    spot_rising = spot.get("rising")

    # Get US 10Y yield once — used for all spread calculations
    us_10y = get_us_10y_yield(db)

    results = []
    for country in db.query(Country).all():
        iso = country.iso_code

        # ── DIMENSION 1: Treasury ──────────────────────────────────────────
        tic_hist = db.query(TimeSeries).filter(
            TimeSeries.metric_id == tic_metric.id,
            TimeSeries.country_id == country.id,
            TimeSeries.date >= tic_latest - timedelta(days=185),
        ).order_by(TimeSeries.date.asc()).all()

        if len(tic_hist) < 2:
            continue

        tic_prev = float(tic_hist[-2].value)
        if tic_prev == 0:
            continue

        tic_mom = (float(tic_hist[-1].value) - tic_prev) / tic_prev * 100
        tic_consec = 0
        for i in range(len(tic_hist) - 1, 0, -1):
            if float(tic_hist[i].value) < float(tic_hist[i-1].value):
                tic_consec += 1
            else:
                break

        tic_score = 0
        if tic_mom < 0:
            tic_score += min(30, abs(tic_mom) * 3)
        tic_score += min(20, tic_consec * 4)

        # ── DIMENSION 2: Gold Reserves ─────────────────────────────────────
        gold_score = 0
        gold_mom = None
        gold_consec = 0
        gold_tonnes = None
        selling_gold = False

        if gold_metric and gold_latest:
            gold_hist = db.query(TimeSeries).filter(
                TimeSeries.metric_id == gold_metric.id,
                TimeSeries.country_id == country.id,
                TimeSeries.date >= gold_latest - timedelta(days=400),
            ).order_by(TimeSeries.date.asc()).all()

            if gold_hist:
                gold_tonnes = float(gold_hist[-1].value)
                if len(gold_hist) >= 2:
                    gold_prev = float(gold_hist[-2].value)
                    if gold_prev > 0:
                        gold_mom = (gold_tonnes - gold_prev) / gold_prev * 100
                        for i in range(len(gold_hist) - 1, 0, -1):
                            if float(gold_hist[i].value) < float(gold_hist[i-1].value):
                                gold_consec += 1
                            else:
                                break
                        if gold_mom < 0:
                            gold_score += min(20, abs(gold_mom) * 2)
                        gold_score += min(20, gold_consec * 4)
                        selling_gold = gold_mom < -0.5 or gold_consec >= 2

        # ── DIMENSION 3: Monetary / M2 ─────────────────────────────────────
        monetary_score = 0
        m2_growth_pct = None
        m2_year = None

        if m2_metric:
            m2_rows = db.query(TimeSeries).filter(
                TimeSeries.metric_id == m2_metric.id,
                TimeSeries.country_id == country.id,
            ).order_by(TimeSeries.date.desc()).first()

            if m2_rows:
                m2_growth_pct = float(m2_rows.value)
                m2_year = m2_rows.date.year
                if m2_growth_pct > 50:
                    monetary_score = 35
                elif m2_growth_pct > 30:
                    monetary_score = 20
                elif m2_growth_pct > 15:
                    monetary_score = 10

        # ── DIMENSION 4: Sovereign Spread ──────────────────────────────────
        spread_data = get_sovereign_spread(db, iso, us_10y)
        spread_score = spread_data["score"]
        spread_bps = spread_data["spread_bps"]
        spread_widening = spread_data["widening_bps"]

        # ── MULTIPLIERS ────────────────────────────────────────────────────
        selling_tic = tic_mom < -0.5 or tic_consec >= 2
        cross_asset = selling_tic and selling_gold
        divergence = cross_asset and spot_rising

        if divergence:
            multiplier = 2.0
        elif cross_asset:
            multiplier = 1.5
        else:
            multiplier = 1.0

        raw_score = tic_score + gold_score + monetary_score + spread_score
        composite_score = raw_score * multiplier

        # ── TIER ───────────────────────────────────────────────────────────
        if composite_score >= 75:
            tier = "CRISIS"
        elif composite_score >= 50:
            tier = "STRESSED"
        elif composite_score >= 25:
            tier = "ELEVATED"
        else:
            tier = "WATCH"

        # Skip WATCH countries with zero score to reduce noise
        if composite_score == 0:
            continue

        # ── ACTIVE SIGNALS ─────────────────────────────────────────────────
        signals = []
        if selling_tic and tic_consec >= 3:
            signals.append(f"T-bills: {tic_consec}mo consecutive ↓")
        elif selling_tic:
            signals.append(f"T-bills: {tic_mom:+.1f}% MoM")
        if selling_gold:
            signals.append(f"Gold selling: {gold_mom:+.1f}% QoQ" if gold_mom else "Gold declining")
        if m2_growth_pct and m2_growth_pct > 15:
            signals.append(f"M2 growth: {m2_growth_pct:.0f}% YoY ({m2_year})")
        if spread_bps and spread_bps > 50:
            signals.append(f"Spread: +{spread_bps:.0f}bps vs US")
        if spread_widening and spread_widening > 30:
            signals.append(f"Spread widening: +{spread_widening:.0f}bps (3M)")
        if divergence:
            signals.append("⚡ DIVERGENCE: selling gold into rising price")
        elif cross_asset:
            signals.append("⚠ Cross-asset: selling T-bills + gold")

        results.append({
            "country_iso": iso,
            "country_name": country.name,
            "region": country.region,
            # Treasury
            "tic_holdings_bn": round(float(tic_hist[-1].value), 2),
            "tic_mom_pct": round(tic_mom, 2),
            "tic_consecutive_months": tic_consec,
            "tic_score": round(tic_score, 1),
            # Gold
            "gold_tonnes": round(gold_tonnes, 1) if gold_tonnes else None,
            "gold_mom_pct": round(gold_mom, 2) if gold_mom is not None else None,
            "gold_consecutive_quarters": gold_consec,
            "gold_score": round(gold_score, 1),
            # Monetary
            "m2_growth_pct": round(m2_growth_pct, 1) if m2_growth_pct is not None else None,
            "m2_year": m2_year,
            "monetary_score": round(monetary_score, 1),
            # Spread
            "spread_bps": spread_bps,
            "spread_widening_bps": spread_widening,
            "spread_score": round(spread_score, 1),
            # Multipliers & totals
            "multiplier": multiplier,
            "raw_score": round(raw_score, 1),
            "composite_score": round(composite_score, 1),
            "tier": tier,
            # Flags
            "selling_treasuries": selling_tic,
            "selling_gold": selling_gold,
            "cross_asset": cross_asset,
            "divergence": divergence,
            "active_signals": signals,
            # Context
            "spot_gold_price": spot.get("latest_price"),
            "spot_gold_rising": spot_rising,
            "as_of": tic_latest.strftime("%Y-%m"),
        })

    results.sort(key=lambda x: x["composite_score"], reverse=True)

    crisis = [r for r in results if r["tier"] == "CRISIS"]
    stressed = [r for r in results if r["tier"] == "STRESSED"]
    elevated = [r for r in results if r["tier"] == "ELEVATED"]
    watch = [r for r in results if r["tier"] == "WATCH"]

    return {
        "crisis": crisis,
        "stressed": stressed,
        "elevated": elevated,
        "watch": watch,
        "summary": {
            "crisis": len(crisis),
            "stressed": len(stressed),
            "elevated": len(elevated),
            "watch": len(watch),
            "total": len(results),
            "highest_risk": results[0] if results else None,
            "us_10y_yield": us_10y,
            "countries_with_spread_data": len([r for r in results if r["spread_bps"] is not None]),
        },
        "as_of": tic_latest.strftime("%Y-%m") if tic_latest else None,
    }
