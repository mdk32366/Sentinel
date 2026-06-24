"""
Composite Sovereign Stress Scorer
------------------------------------
Five-dimension scoring system:

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

  DIMENSION 4 — Sovereign Spread (0-20 pts)
    Spread >50bps vs US 10Y:   5 pts  (mild risk premium)
    Spread >100bps vs US 10Y: 10 pts  (elevated)
    Spread >200bps vs US 10Y: 15 pts  (significant stress)
    Spread widening >30bps in 3M: +5 pts (trend component)

  DIMENSION 5 — Petrodollar / Oil Pressure (0-20 pts)  ← NEW
    Only fires for oil-dependent economies.
    Brent down >10% over 3M:  5 pts  (mild revenue pressure)
    Brent down >20% over 3M: 10 pts  (significant)
    Brent down >30% over 3M: 20 pts  (severe — forced seller risk)
    Convergence bonus: +5 pts if oil falling AND country selling treasuries
    simultaneously (confirms petrodollar recycling breakdown)

    Oil-dependent nations: Gulf states, Russia/CIS oil exporters,
    Nigeria, Algeria, Libya, Angola, Mexico, Colombia, Ecuador,
    Venezuela, Norway, Kazakhstan, Azerbaijan.

MULTIPLIERS (applied to raw sum):
  Cross-asset (selling both T + gold):    1.5x
  Divergence (selling gold into rising):  2.0x

TIERS:
  WATCH:    score < 25
  ELEVATED: 25 ≤ score < 50
  STRESSED: 50 ≤ score < 75
  CRISIS:   score ≥ 75
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
    "NLD": "IRLTLT01NLM156N",
    "NOR": "IRLTLT01NOM156N",
    "SWE": "IRLTLT01SEM156N",
    "CHE": "IRLTLT01CHM156N",
    "BEL": "IRLTLT01BEM156N",
    "KOR": "IRLTLT01KRM156N",
}

# Countries whose external reserve dynamics are significantly driven by
# oil/gas export revenues. When Brent falls, these countries experience
# reduced petrodollar recycling — meaning less USD flowing back into
# Treasuries, and potential forced selling to cover fiscal gaps.
OIL_DEPENDENT_COUNTRIES = {
    # Gulf / Middle East
    "SAU", "ARE", "KWT", "QAT", "IRQ", "OMN", "BHR",
    # Russia / CIS
    "RUS", "KAZ", "AZE",
    # Africa
    "NGA", "AGO", "DZA", "LBY",
    # Latin America
    "VEN", "ECU", "COL", "MEX",
    # Europe/Other
    "NOR",
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


def get_brent_trend(db: Session, months: int = 3) -> dict:
    """
    Get Brent crude price trend over the past N months.
    Uses DCOILBRENTEU (daily) from FRED.
    Falls back to WTI (DCOILWTICO) if Brent not available.
    Returns: {latest_price, start_price, change_pct, falling}
    """
    for code in ("DCOILBRENTEU", "DCOILWTICO"):
        metric = db.query(Metric).filter_by(code=code).first()
        if not metric:
            continue

        cutoff = datetime.utcnow() - timedelta(days=months * 31)
        history = db.query(TimeSeries).filter(
            TimeSeries.metric_id == metric.id,
            TimeSeries.country_id == None,
            TimeSeries.date >= cutoff,
        ).order_by(TimeSeries.date.asc()).all()

        if len(history) < 10:
            continue

        latest = float(history[-1].value)
        start = float(history[0].value)
        change_pct = (latest - start) / start * 100 if start else None

        return {
            "source": code,
            "latest_price": round(latest, 2),
            "start_price": round(start, 2),
            "change_pct": round(change_pct, 1) if change_pct is not None else None,
            "falling": change_pct < -10 if change_pct is not None else None,
            "change_3m_pct": round(change_pct, 1) if change_pct is not None else None,
        }

    return {
        "source": None,
        "latest_price": None,
        "start_price": None,
        "change_pct": None,
        "falling": None,
        "change_3m_pct": None,
    }


def get_petrodollar_score(iso: str, brent: dict, selling_tic: bool) -> dict:
    """
    Compute petrodollar stress score for a given country.
    Only fires for oil-dependent economies.

    The signal: oil revenue is the primary source of USD for these countries.
    When Brent falls, their ability to recycle petrodollars into US Treasuries
    weakens. Combined with active treasury selling, this confirms a revenue
    stress dynamic rather than strategic repositioning.
    """
    if iso not in OIL_DEPENDENT_COUNTRIES:
        return {"score": 0, "oil_dependent": False, "oil_signal": None}

    change_pct = brent.get("change_pct")
    if change_pct is None:
        return {"score": 0, "oil_dependent": True, "oil_signal": "no price data"}

    score = 0
    signal = None

    if change_pct <= -30:
        score = 20
        signal = f"Brent {change_pct:.1f}% (3M) — severe revenue shock"
    elif change_pct <= -20:
        score = 10
        signal = f"Brent {change_pct:.1f}% (3M) — significant revenue pressure"
    elif change_pct <= -10:
        score = 5
        signal = f"Brent {change_pct:.1f}% (3M) — mild revenue pressure"

    # Convergence bonus: oil falling AND selling treasuries simultaneously
    # This is the clearest petrodollar recycling breakdown signal
    if score > 0 and selling_tic:
        score += 5
        signal += " + treasury selling (petrodollar recycling breakdown)"

    return {
        "score": min(score, 20),
        "oil_dependent": True,
        "oil_signal": signal,
    }


def get_sovereign_spread(db: Session, iso: str, us_10y: float | None) -> dict:
    """
    Get sovereign bond yield spread vs US 10Y for a given country.
    Returns: {spread_bps, widening_bps, score}
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

    widening_bps = None
    if len(history) >= 2:
        old_yield = float(history[0].value)
        old_spread = (old_yield - us_10y) * 100
        widening_bps = spread_bps - old_spread

    score = 0
    if spread_bps > 200:
        score = 15
    elif spread_bps > 100:
        score = 10
    elif spread_bps > 50:
        score = 5

    if widening_bps is not None and widening_bps > 30:
        score += 5

    return {
        "spread_bps": round(spread_bps, 1),
        "widening_bps": round(widening_bps, 1) if widening_bps is not None else None,
        "score": min(score, 20),
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
    Compute five-dimension composite stress scores for all countries.
    Returns structured dict with tiers and summary.
    """
    tic_metric = db.query(Metric).filter_by(code="TIC_UST_HOLDINGS").first()
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
    us_10y = get_us_10y_yield(db)

    # Fetch Brent trend once — applies to all oil-dependent countries
    brent = get_brent_trend(db, months=3)

    results = []
    for country in db.query(Country).all():
        iso = country.iso_code

        # ── DIMENSION 1: Treasury ──────────────────────────────────────────
        tic_hist = db.query(TimeSeries).filter(
            TimeSeries.metric_id == tic_metric.id,
            TimeSeries.country_id == country.id,
            TimeSeries.date >= tic_latest - timedelta(days=185),
        ).order_by(TimeSeries.date.asc()).all()

        tic_mom = 0
        tic_consec = 0
        tic_score = 0
        selling_tic = False
        no_tic_holdings = len(tic_hist) == 0

        if len(tic_hist) >= 2:
            tic_prev = float(tic_hist[-2].value)
            if tic_prev > 0:
                tic_mom = (float(tic_hist[-1].value) - tic_prev) / tic_prev * 100
                for i in range(len(tic_hist) - 1, 0, -1):
                    if float(tic_hist[i].value) < float(tic_hist[i-1].value):
                        tic_consec += 1
                    else:
                        break
                if tic_mom < 0:
                    tic_score += min(30, abs(tic_mom) * 3)
                tic_score += min(20, tic_consec * 4)
                selling_tic = tic_mom < -0.5 or tic_consec >= 2
        elif no_tic_holdings:
            # Country holds zero US Treasuries — completed liquidation is max stress
            # Only flag if they have meaningful gold reserves (confirms de-dollarization)
            tic_score = 0  # Will get boosted by cross-asset multiplier if gold present
            tic_mom = None
            tic_consec = 0

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
            m2_row = db.query(TimeSeries).filter(
                TimeSeries.metric_id == m2_metric.id,
                TimeSeries.country_id == country.id,
            ).order_by(TimeSeries.date.desc()).first()

            if m2_row:
                m2_growth_pct = float(m2_row.value)
                m2_year = m2_row.date.year
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

        # ── DIMENSION 5: Petrodollar / Oil Pressure ────────────────────────
        selling_tic = (tic_mom is not None and (tic_mom < -0.5 or tic_consec >= 2))
        petro_data = get_petrodollar_score(iso, brent, selling_tic)
        petro_score = petro_data["score"]
        oil_dependent = petro_data["oil_dependent"]
        oil_signal = petro_data["oil_signal"]

        # ── MULTIPLIERS ────────────────────────────────────────────────────
        cross_asset = selling_tic and selling_gold
        divergence = cross_asset and spot_rising

        if divergence:
            multiplier = 2.0
        elif cross_asset:
            multiplier = 1.5
        else:
            multiplier = 1.0

        raw_score = tic_score + gold_score + monetary_score + spread_score + petro_score
        composite_score = raw_score * multiplier

        if composite_score >= 75:
            tier = "CRISIS"
        elif composite_score >= 50:
            tier = "STRESSED"
        elif composite_score >= 25:
            tier = "ELEVATED"
        else:
            tier = "WATCH"

        if composite_score == 0:
            continue

        # ── ACTIVE SIGNALS ─────────────────────────────────────────────────
        signals = []
        if no_tic_holdings and gold_tonnes and gold_tonnes > 50:
            signals.append("⚠ Zero US Treasuries held — completed liquidation")
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
        if oil_signal:
            signals.append(f"🛢 {oil_signal}")
        if divergence:
            signals.append("⚡ DIVERGENCE: selling gold into rising price")
        elif cross_asset:
            signals.append("⚠ Cross-asset: selling T-bills + gold")

        # Skip countries with no signals at all
        if not signals and composite_score == 0:
            continue

        # ── DIMENSION 6: Non-dollar reserve trend (TRESEG) ────────────────
        treseg = get_treseg_signal(db, iso, no_tic_holdings)

        # Boost score if exited TIC AND rebuilding non-gold reserves
        # (active de-dollarization into alternative system)
        if no_tic_holdings and treseg["signal"] == "REBUILDING":
            signals.append(f"⚡ Non-$ reserves rebuilding: +{treseg['trend_pct']}% YoY (de-dollarization)")
            composite_score = min(composite_score * 1.2, 150)  # 20% boost, capped at 150
        elif no_tic_holdings and treseg["signal"] == "DEPLETING":
            signals.append(f"⚠ Non-$ reserves depleting: {treseg['trend_pct']}% YoY (distress)")

        results.append({
            "country_iso": iso,
            "country_name": country.name,
            "region": country.region,
            # Treasury
            "tic_holdings_bn": round(float(tic_hist[-1].value), 2) if tic_hist else 0,
            "tic_mom_pct": round(tic_mom, 2) if tic_mom is not None else None,
            "tic_consecutive_months": tic_consec,
            "tic_score": round(tic_score, 1),
            "no_tic_holdings": no_tic_holdings,
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
            # Petrodollar
            "oil_dependent": oil_dependent,
            "oil_signal": oil_signal,
            "brent_3m_pct": brent.get("change_3m_pct"),
            "brent_price": brent.get("latest_price"),
            "petro_score": round(petro_score, 1),
            # Non-dollar reserves (TRESEG)
            "treseg_signal": treseg["signal"],
            "treseg_trend_pct": treseg["trend_pct"],
            "treseg_latest_bn": treseg["latest_bn"],
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
            "brent_price": brent.get("latest_price"),
            "brent_3m_pct": brent.get("change_3m_pct"),
            "brent_source": brent.get("source"),
            "countries_with_spread_data": len([r for r in results if r["spread_bps"] is not None]),
            "oil_dependent_countries": len([r for r in results if r["oil_dependent"]]),
        },
        "as_of": tic_latest.strftime("%Y-%m") if tic_latest else None,
    }


# ── TRESEG country mapping ────────────────────────────────────────────────────
TRESEG_MAP = {
    "CHN": "TRESEGCNM052N",
    "JPN": "TRESEGJPM052N",
    "RUS": "TRESEGRUM052N",
    "IND": "TRESEGINM052N",
    "TUR": "TRESEGTRM052N",
    "DEU": "TRESEGDEM052N",
    "FRA": "TRESEGFRM052N",
    "GBR": "TRESEGGBM052N",
    "SAU": "TRESEGSAM052N",
    "BRA": "TRESEGBRM052N",
    "USA": "TRESEGUSM052N",
    "IDN": "TRESEGIDM052N",
}


def get_treseg_signal(db: Session, iso: str, no_tic: bool) -> dict:
    """
    Get total reserves ex-gold trend for a country.
    Returns signal: REBUILDING / DEPLETING / STABLE / NO_DATA
    Analytically significant mainly when no_tic=True (exited Treasuries).
    """
    fred_code = TRESEG_MAP.get(iso)
    if not fred_code:
        return {"signal": "NO_DATA", "trend_pct": None, "latest_bn": None}

    metric = db.query(Metric).filter_by(code=fred_code).first()
    if not metric:
        return {"signal": "NO_DATA", "trend_pct": None, "latest_bn": None}

    history = db.query(TimeSeries).filter(
        TimeSeries.metric_id == metric.id,
        TimeSeries.country_id == None,
    ).order_by(TimeSeries.date.desc()).limit(13).all()

    if len(history) < 2:
        return {"signal": "NO_DATA", "trend_pct": None, "latest_bn": None}

    latest = float(history[0].value)
    prior = float(history[min(12, len(history)-1)].value)

    if prior == 0:
        return {"signal": "NO_DATA", "trend_pct": None, "latest_bn": round(latest/1000, 1)}

    trend_pct = (latest - prior) / prior * 100

    if trend_pct > 5:
        signal = "REBUILDING"
    elif trend_pct < -5:
        signal = "DEPLETING"
    else:
        signal = "STABLE"

    return {
        "signal": signal,
        "trend_pct": round(trend_pct, 1),
        "latest_bn": round(latest / 1000, 1),
    }
