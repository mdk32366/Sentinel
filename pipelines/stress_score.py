"""
Stress-Scoring Algorithm
------------------------
Calculates macro stress index from three factors:
1. Yield Curve: DGS2 - DGS10 spread (inversion = stress)
2. Holdings Concentration: Top country % of total (high concentration = stress)
3. Commodity Volatility: 30-day WTI price volatility (high volatility = stress)

Output: 0-100 stress score, updated daily.
"""

import logging
from datetime import datetime, timedelta
from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy import func
from database.models import Metric, TimeSeries, UpdateLog, Country
import math

logger = logging.getLogger(__name__)


def get_latest_metric_value(db: Session, metric_code: str, country_id=None, days_back=1) -> float:
    """Get most recent value for a metric, optionally for a specific country."""
    query = db.query(TimeSeries).join(Metric).filter(
        Metric.code == metric_code,
    )
    
    if country_id is not None:
        query = query.filter(TimeSeries.country_id == country_id)
    else:
        query = query.filter(TimeSeries.country_id == None)
    
    result = query.order_by(TimeSeries.date.desc()).first()
    
    if result:
        return float(result.value)
    return None


def get_metric_volatility(db: Session, metric_code: str, days: int = 30) -> float:
    """Calculate standard deviation of metric values over N days."""
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)
    
    values = db.query(TimeSeries.value).join(Metric).filter(
        Metric.code == metric_code,
        TimeSeries.country_id == None,
        TimeSeries.date >= start_date,
        TimeSeries.date <= end_date,
    ).order_by(TimeSeries.date).all()
    
    if len(values) < 2:
        return 0.0
    
    values = [float(v[0]) for v in values]
    mean = sum(values) / len(values)
    variance = sum((x - mean) ** 2 for x in values) / len(values)
    return math.sqrt(variance)


def calculate_yield_curve_stress(db: Session) -> tuple:
    """
    Factor 1: Yield curve inversion
    DGS10 - DGS2 spread (positive = normal, negative = inverted)
    Normalized to 0-100 where:
    - -1.0% (severe inversion) = 100 (max stress)
    - +1.0% (steep curve) = 0 (no stress)
    """
    dgs10 = get_latest_metric_value(db, "DGS10")
    dgs2 = get_latest_metric_value(db, "DGS2")
    
    if dgs10 is None or dgs2 is None:
        logger.warning("Missing DGS10 or DGS2 data for yield curve stress")
        return 0.0, 0.0
    
    spread = dgs10 - dgs2
    
    # Map spread to stress: -1% (100) to +1% (0), linear
    if spread < -1.0:
        stress = 100.0
    elif spread > 1.0:
        stress = 0.0
    else:
        stress = 50.0 - (spread * 50.0)  # At 0%, stress = 50
    
    return stress, spread


def calculate_concentration_stress(db: Session) -> tuple:
    """
    Factor 2: Holdings concentration risk
    Top country as % of total foreign holdings
    Normalized to 0-100 where:
    - 30% (very high concentration) = 100 (max stress)
    - 10% or less (diversified) = 0 (no stress)
    """
    # Get all countries' most recent holdings
    metric = db.query(Metric).filter_by(code="TIC_UST_HOLDINGS").first()
    if not metric:
        logger.warning("No TIC_UST_HOLDINGS metric found")
        return 0.0, 0.0
    
    # Get latest date with holdings data
    latest_date = db.query(func.max(TimeSeries.date)).filter(
        TimeSeries.metric_id == metric.id,
        TimeSeries.country_id != None,
    ).scalar()
    
    if not latest_date:
        logger.warning("No holdings data found")
        return 0.0, 0.0
    
    # Get all countries' holdings on that date
    holdings = db.query(
        Country.name,
        TimeSeries.value
    ).join(TimeSeries).filter(
        TimeSeries.metric_id == metric.id,
        TimeSeries.date == latest_date,
        TimeSeries.country_id != None,
    ).order_by(TimeSeries.value.desc()).all()
    
    if not holdings:
        return 0.0, 0.0
    
    total = sum(float(h[1]) for h in holdings)
    if total == 0:
        return 0.0, 0.0
    
    top_country_pct = (float(holdings[0][1]) / total) * 100.0
    
    # Map concentration to stress: 30% (100) to 10% (0), linear
    if top_country_pct >= 30.0:
        stress = 100.0
    elif top_country_pct <= 10.0:
        stress = 0.0
    else:
        # Linear interpolation: 10% = 0, 30% = 100
        stress = (top_country_pct - 10.0) / 20.0 * 100.0
    
    return stress, top_country_pct


def calculate_volatility_stress(db: Session) -> tuple:
    """
    Factor 3: Commodity volatility (WTI crude oil)
    Normalized to 0-100 where:
    - 5%+ daily std dev = 100 (max stress)
    - <1% daily std dev = 0 (no stress)
    """
    # Get 30-day volatility of WTI
    wti_volatility = get_metric_volatility(db, "DCOILWTICO", days=30)
    
    if wti_volatility is None:
        logger.warning("No WTI volatility data")
        return 0.0, 0.0
    
    # Map volatility to stress: 5% (100) to 1% (0), linear
    if wti_volatility >= 5.0:
        stress = 100.0
    elif wti_volatility <= 1.0:
        stress = 0.0
    else:
        # Linear: 1% = 0, 5% = 100
        stress = (wti_volatility - 1.0) / 4.0 * 100.0
    
    return stress, wti_volatility


def calculate_stress_score(db: Session) -> dict:
    """
    Composite stress score: weighted average of three factors.
    Weights: 40% yield curve, 35% concentration, 25% volatility
    """
    yc_stress, yc_spread = calculate_yield_curve_stress(db)
    conc_stress, conc_pct = calculate_concentration_stress(db)
    vol_stress, wti_vol = calculate_volatility_stress(db)
    
    # Weighted composite
    composite = (yc_stress * 0.40) + (conc_stress * 0.35) + (vol_stress * 0.25)
    
    return {
        "overall_score": round(composite, 1),
        "components": {
            "yield_curve": {
                "score": round(yc_stress, 1),
                "value": round(yc_spread, 2),
                "unit": "percentage_points",
                "interpretation": "DGS10 - DGS2 spread"
            },
            "concentration": {
                "score": round(conc_stress, 1),
                "value": round(conc_pct, 1),
                "unit": "percent",
                "interpretation": "Top country % of total holdings"
            },
            "commodity_volatility": {
                "score": round(vol_stress, 1),
                "value": round(wti_vol, 2),
                "unit": "percent",
                "interpretation": "30-day WTI price std dev"
            }
        },
        "weights": {
            "yield_curve": 0.40,
            "concentration": 0.35,
            "commodity_volatility": 0.25,
        },
        "interpretation": stress_interpretation(composite),
        "timestamp": datetime.utcnow().isoformat(),
    }


def stress_interpretation(score: float) -> str:
    """Interpret stress score for humans."""
    if score >= 75:
        return "SEVERE - Multiple stress factors elevated"
    elif score >= 50:
        return "ELEVATED - Moderate stress indicated"
    elif score >= 25:
        return "MODERATE - Watch conditions"
    else:
        return "LOW - Normal market conditions"


def run_stress_score_calculation(db: Session) -> dict:
    """Main stress score calculation pipeline."""
    start_time = datetime.utcnow()
    
    try:
        score_result = calculate_stress_score(db)
        
        # Log the result
        db.add(UpdateLog(
            pipeline_name="Stress_Score",
            status="success",
            records_inserted=1,
            records_updated=0,
            error_message=None,
            started_at=start_time,
            completed_at=datetime.utcnow(),
        ))
        db.commit()
        
        logger.info(f"Stress score calculated: {score_result['overall_score']} ({score_result['interpretation']})")
        
        return {
            "status": "success",
            "data": score_result,
        }
    
    except Exception as e:
        logger.error(f"Stress score calculation failed: {e}")
        db.add(UpdateLog(
            pipeline_name="Stress_Score",
            status="failed",
            records_inserted=0,
            records_updated=0,
            error_message=str(e),
            started_at=start_time,
            completed_at=datetime.utcnow(),
        ))
        db.commit()
        
        return {
            "status": "failed",
            "error": str(e),
        }


def calculate_gold_accumulation_stress(db: Session) -> tuple:
    """
    Factor 4: Central bank gold accumulation rate
    Rapid accumulation = de-dollarization signal = stress.
    Compares latest quarter total vs same quarter one year ago (YoY).
    Normalized 0-100 where:
    - >3% YoY increase in total CB gold = 100 (heavy accumulation)
    - <0% YoY (net selling) = 0 (no stress)
    """
    metric = db.query(Metric).filter_by(code="GOLD_RESERVES").first()
    if not metric:
        return 0.0, 0.0

    from sqlalchemy import func as sqlfunc

    # Get all distinct dates with data, newest first
    all_dates = (
        db.query(TimeSeries.date)
        .filter(TimeSeries.metric_id == metric.id, TimeSeries.country_id != None)
        .distinct()
        .order_by(TimeSeries.date.desc())
        .all()
    )

    if len(all_dates) < 5:
        return 0.0, 0.0

    latest_date = all_dates[0][0]
    # Compare against ~1 year ago (4 quarters back)
    prior_date = all_dates[min(4, len(all_dates) - 1)][0]

    latest_total = db.query(sqlfunc.sum(TimeSeries.value)).filter(
        TimeSeries.metric_id == metric.id,
        TimeSeries.date == latest_date,
        TimeSeries.country_id != None,
        TimeSeries.value > 0,
    ).scalar() or 0

    prior_total = db.query(sqlfunc.sum(TimeSeries.value)).filter(
        TimeSeries.metric_id == metric.id,
        TimeSeries.date == prior_date,
        TimeSeries.country_id != None,
        TimeSeries.value > 0,
    ).scalar() or 0

    if not prior_total:
        return 0.0, 0.0

    pct_change = ((float(latest_total) - float(prior_total)) / float(prior_total)) * 100.0

    # Map: >3% YoY growth = 100 (stress), <0% = 0 (no stress)
    if pct_change >= 3.0:
        stress = 100.0
    elif pct_change <= 0.0:
        stress = 0.0
    else:
        stress = (pct_change / 3.0) * 100.0

    return stress, pct_change


def calculate_stress_score_v2(db: Session) -> dict:
    """
    Composite stress score: weighted average of four factors.
    Weights: 35% yield curve, 30% concentration, 20% volatility, 15% gold accumulation
    """
    yc_stress, yc_spread = calculate_yield_curve_stress(db)
    conc_stress, conc_pct = calculate_concentration_stress(db)
    vol_stress, wti_vol = calculate_volatility_stress(db)
    gold_stress, gold_pct_change = calculate_gold_accumulation_stress(db)

    has_gold = gold_stress > 0 or gold_pct_change != 0.0

    if has_gold:
        composite = (yc_stress * 0.35) + (conc_stress * 0.30) + (vol_stress * 0.20) + (gold_stress * 0.15)
        weights = {"yield_curve": 0.35, "concentration": 0.30, "commodity_volatility": 0.20, "gold_accumulation": 0.15}
    else:
        # Fall back to 3-factor if no gold data yet
        composite = (yc_stress * 0.40) + (conc_stress * 0.35) + (vol_stress * 0.25)
        weights = {"yield_curve": 0.40, "concentration": 0.35, "commodity_volatility": 0.25, "gold_accumulation": 0.0}

    components = {
        "yield_curve": {
            "score": round(yc_stress, 1),
            "value": round(yc_spread, 2),
            "unit": "percentage_points",
            "interpretation": "DGS10 - DGS2 spread"
        },
        "concentration": {
            "score": round(conc_stress, 1),
            "value": round(conc_pct, 1),
            "unit": "percent",
            "interpretation": "Top country % of total holdings"
        },
        "commodity_volatility": {
            "score": round(vol_stress, 1),
            "value": round(wti_vol, 2),
            "unit": "percent",
            "interpretation": "30-day WTI price std dev"
        },
        "gold_accumulation": {
            "score": round(gold_stress, 1),
            "value": round(gold_pct_change, 2),
            "unit": "percent_6m_change",
            "interpretation": "6-month % change in total CB gold holdings"
        },
    }

    return {
        "overall_score": round(composite, 1),
        "components": components,
        "weights": weights,
        "interpretation": stress_interpretation(composite),
        "timestamp": datetime.utcnow().isoformat(),
    }
