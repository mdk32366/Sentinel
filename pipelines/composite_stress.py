"""
Composite Sovereign Stress Scorer
-----------------------------------
Combines three signal dimensions into a single distress score:

  1. TREASURY DIMENSION (0-50 pts)
     - MoM decline magnitude: 0-30 pts (max at -10%)
     - Consecutive declining months: 0-20 pts (max at 5+ months)

  2. GOLD DIMENSION (0-40 pts)
     - QoQ decline magnitude: 0-25 pts (max at -5%)
     - Consecutive declining quarters: 0-15 pts (max at 3+ quarters)

  3. MONETARY DIMENSION (0-35 pts)
     - M2 growth >15%:  +10 pts (elevated financing pressure)
     - M2 growth >30%:  +20 pts (significant debasement)
     - M2 growth >50%:  +35 pts (crisis-level printing)
     Note: These are additive thresholds — >50% gives the full 35pts

  MULTIPLIERS (applied to base score):
     - All three dimensions firing:       1.5×
     - Gold selling INTO rising spot:     2.0×
     - Both multipliers:                  2.0× (not stacked)

  INTERPRETATION:
     0-25:   Watch — one signal, may be tactical
     25-50:  Elevated — multiple signals, monitor closely
     50-75:  Stressed — strong cross-asset confirmation
     75-100: Crisis — all signals firing, likely forced seller
     100+:   Acute crisis — with multipliers applied

  SIGNAL TIERS (for display):
     WATCH        < 25
     ELEVATED     25-50
     STRESSED     50-75
     CRISIS       75+
"""

import logging
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func
from database.models import Metric, TimeSeries, Country

logger = logging.getLogger(__name__)


def get_latest_spot_trend(db: Session) -> bool:
    """Returns True if spot gold has risen >2% over last 3 months."""
    metric = db.query(Metric).filter_by(code="GOLD_SPOT_USD").first()
    if not metric:
        return False
    cutoff = datetime.utcnow() - timedelta(days=95)
    history = db.query(TimeSeries).filter(
        TimeSeries.metric_id == metric.id,
        TimeSeries.country_id == None,
        TimeSeries.date >= cutoff,
    ).order_by(TimeSeries.date.asc()).all()
    if len(history) < 2:
        return False
    start = float(history[0].value)
    end = float(history[-1].value)
    return ((end - start) / start * 100) > 2 if start else False


def compute_composite_stress(db: Session) -> list:
    """
    Compute composite sovereign stress scores for all countries.
    Returns sorted list of country stress profiles.
    """
    tic_metric  = db.query(Metric).filter_by(code="TIC_HOLDINGS").first()
    gold_metric = db.query(Metric).filter_by(code="GOLD_RESERVES").first()
    m2_metric   = db.query(Metric).filter_by(code="BROAD_MONEY_GROWTH").first()

    if not tic_metric:
        return []

    tic_latest = db.query(func.max(TimeSeries.date)).filter(
        TimeSeries.metric_id == tic_metric.id).scalar()
    if not tic_latest:
        return []

    gold_latest = None
    if gold_metric:
        gold_latest = db.query(func.max(TimeSeries.date)).filter(
            TimeSeries.metric_id == gold_metric.id).scalar()

    spot_rising = get_latest_spot_trend(db)
    results = []

    for country in db.query(Country).all():

        # ── TREASURY DIMENSION ──────────────────────────────────────────
        tic_hist = db.query(TimeSeries).filter(
            TimeSeries.metric_id == tic_metric.id,
            TimeSeries.country_id == country.id,
            TimeSeries.date >= tic_latest - timedelta(days=215),
        ).order_by(TimeSeries.date.asc()).all()

        if len(tic_hist) < 2:
            continue

        tic_prev = float(tic_hist[-2].value)
        if tic_prev == 0:
            continue
        tic_mom = (float(tic_hist[-1].value) - tic_prev) / tic_prev * 100
        tic_consec = sum(1 for i in range(len(tic_hist)-1, 0, -1)
                         if float(tic_hist[i].value) < float(tic_hist[i-1].value))

        t_score = 0
        if tic_mom < 0:
            t_score += min(30, abs(tic_mom) * 3)
        t_score += min(20, tic_consec * 4)

        # ── GOLD DIMENSION ──────────────────────────────────────────────
        g_score = 0
        gold_mom = None
        gold_consec = 0
        gold_tonnes = None

        if gold_metric and gold_latest:
            gold_hist = db.query(TimeSeries).filter(
                TimeSeries.metric_id == gold_metric.id,
                TimeSeries.country_id == country.id,
                TimeSeries.date >= gold_latest - timedelta(days=400),
            ).order_by(TimeSeries.date.asc()).all()

            if len(gold_hist) >= 1:
                gold_tonnes = float(gold_hist[-1].value)
                if len(gold_hist) >= 2:
                    gold_prev = float(gold_hist[-2].value)
                    if gold_prev > 0:
                        gold_mom = (gold_tonnes - gold_prev) / gold_prev * 100
                        gold_consec = sum(
                            1 for i in range(len(gold_hist)-1, 0, -1)
                            if float(gold_hist[i].value) < float(gold_hist[i-1].value)
                        )
                        if gold_mom < 0:
                            g_score += min(25, abs(gold_mom) * 5)
                        g_score += min(15, gold_consec * 5)

        # ── MONETARY DIMENSION ──────────────────────────────────────────
        m_score = 0
        m2_growth = None
        m2_year = None

        if m2_metric:
            # Get most recent non-null M2 reading
            m2_hist = db.query(TimeSeries).filter(
                TimeSeries.metric_id == m2_metric.id,
                TimeSeries.country_id == country.id,
            ).order_by(TimeSeries.date.desc()).limit(5).all()

            for m2_row in m2_hist:
                val = float(m2_row.value)
                if val != 0:
                    m2_growth = val
                    m2_year = m2_row.date.year
                    break

            if m2_growth is not None:
                if m2_growth > 50:
                    m_score = 35
                elif m2_growth > 30:
                    m_score = 20
                elif m2_growth > 15:
                    m_score = 10

        # ── COMPOSITE SCORING ───────────────────────────────────────────
        base_score = t_score + g_score + m_score

        selling_tic  = tic_mom < -0.5 or tic_consec >= 2
        selling_gold = (gold_mom is not None and gold_mom < -0.5) or gold_consec >= 2
        printing     = m2_growth is not None and m2_growth > 15

        all_three    = selling_tic and selling_gold and printing
        cross_asset  = selling_tic and selling_gold
        divergence   = cross_asset and spot_rising

        if divergence:
            multiplier = 2.0
        elif all_three or cross_asset:
            multiplier = 1.5
        else:
            multiplier = 1.0

        final_score = round(base_score * multiplier, 1)

        # Tier classification
        if final_score >= 75:
            tier = "CRISIS"
            tier_color = "#FF4444"
        elif final_score >= 50:
            tier = "STRESSED"
            tier_color = "#E07B5A"
        elif final_score >= 25:
            tier = "ELEVATED"
            tier_color = "#E8C547"
        elif base_score > 0:
            tier = "WATCH"
            tier_color = "#5A6878"
        else:
            continue  # No stress signals at all

        # Active signals list for display
        active_signals = []
        if selling_tic:
            active_signals.append(f"Treasury selling ({tic_consec}mo consecutive)" if tic_consec >= 2 else f"Treasury MoM {tic_mom:.1f}%")
        if selling_gold:
            active_signals.append(f"Gold reserves declining ({gold_consec}q)" if gold_consec >= 2 else f"Gold MoM {gold_mom:.1f}%")
        if printing:
            active_signals.append(f"M2 growth {m2_growth:.0f}% ({m2_year})")
        if divergence:
            active_signals.append("Selling gold INTO rising spot price")

        results.append({
            # Identity
            "country_iso":   country.iso_code,
            "country_name":  country.name,
            "region":        country.region,
            # Treasury
            "tic_holdings_bn":       round(float(tic_hist[-1].value), 2),
            "tic_mom_pct":           round(tic_mom, 2),
            "tic_consecutive_months": tic_consec,
            "tic_score":             round(t_score, 1),
            "selling_treasuries":    selling_tic,
            # Gold
            "gold_tonnes":           round(gold_tonnes, 1) if gold_tonnes else None,
            "gold_mom_pct":          round(gold_mom, 2) if gold_mom is not None else None,
            "gold_consecutive_qtrs": gold_consec,
            "gold_score":            round(g_score, 1),
            "selling_gold":          selling_gold,
            # Monetary
            "m2_growth_pct":         round(m2_growth, 1) if m2_growth is not None else None,
            "m2_year":               m2_year,
            "monetary_score":        m_score,
            "printing":              printing,
            # Composite
            "base_score":            round(base_score, 1),
            "multiplier":            multiplier,
            "composite_score":       final_score,
            "tier":                  tier,
            "tier_color":            tier_color,
            "active_signals":        active_signals,
            # Flags
            "cross_asset":           cross_asset,
            "all_three":             all_three,
            "divergence":            divergence,
            "spot_gold_rising":      spot_rising,
            "as_of":                 tic_latest.strftime("%Y-%m"),
        })

    return sorted(results, key=lambda x: x["composite_score"], reverse=True)
