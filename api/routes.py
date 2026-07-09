import httpx
from pipelines.fred_fetcher import run_fred_fetch
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta
from typing import List, Optional
from database.connection import get_db
from database.models import Metric, TimeSeries, UpdateLog, Country
from api.schemas import (
    MetricResponse,
    CountryResponse,
    TimeSeriesDataPoint,
    TimeSeriesQuery,
    UpdateLogResponse,
    HealthResponse,
)
from pipelines.scheduler import scheduler
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["treasury-monitor"])


@router.get("/health", response_model=HealthResponse)
def health_check(db: Session = Depends(get_db)):
    """System health check"""
    fred_log = db.query(UpdateLog).filter_by(pipeline_name="FRED").order_by(UpdateLog.completed_at.desc()).first()
    treasury_log = db.query(UpdateLog).filter_by(pipeline_name="TIC_Holdings").order_by(UpdateLog.completed_at.desc()).first()
    gold_log = db.query(UpdateLog).filter_by(pipeline_name="Gold_Reserves").order_by(UpdateLog.completed_at.desc()).first()

    return HealthResponse(
        status="healthy",
        database="connected",
        scheduler="running" if scheduler.running else "stopped",
        last_fred_update=fred_log.completed_at if fred_log else None,
        last_treasury_update=treasury_log.completed_at if treasury_log else None,
        last_gold_update=gold_log.completed_at if gold_log else None,
    )


@router.get("/metrics", response_model=List[MetricResponse])
def list_metrics(
    category: Optional[str] = Query(None, description="Filter by category"),
    db: Session = Depends(get_db)
):
    """List all available metrics"""
    query = db.query(Metric)
    if category:
        query = query.filter_by(category=category)
    return query.all()


@router.get("/countries", response_model=List[CountryResponse])
def list_countries(db: Session = Depends(get_db)):
    """List all countries with data"""
    return db.query(Country).order_by(Country.name).all()


@router.get("/timeseries", response_model=List[TimeSeriesDataPoint])
def get_timeseries(
    metric_codes: str = Query(..., description="Comma-separated metric codes"),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    country_iso: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """Query timeseries data for one or more metrics"""
    codes = [code.strip() for code in metric_codes.split(",")]

    metrics = db.query(Metric).filter(Metric.code.in_(codes)).all()
    if not metrics:
        raise HTTPException(status_code=404, detail=f"No metrics found for codes: {codes}")

    metric_ids = [m.id for m in metrics]

    if not end_date:
        end_date = datetime.utcnow()
    if not start_date:
        start_date = end_date - timedelta(days=730)

    query = db.query(
        TimeSeries.date,
        TimeSeries.value,
        Metric.code,
        Metric.name,
        Country.iso_code,
        Country.name
    ).join(
        Metric, TimeSeries.metric_id == Metric.id
    ).outerjoin(
        Country, TimeSeries.country_id == Country.id
    ).filter(
        TimeSeries.metric_id.in_(metric_ids),
        TimeSeries.date >= start_date,
        TimeSeries.date <= end_date,
    )

    if country_iso:
        query = query.filter(Country.iso_code == country_iso)

    results = query.order_by(TimeSeries.date.asc()).all()

    return [
        TimeSeriesDataPoint(
            date=row[0],
            value=float(row[1]),
            metric_code=row[2],
            metric_name=row[3],
            country_code=row[4],
            country_name=row[5],
        )
        for row in results
    ]


@router.get("/metric/{metric_code}", response_model=List[TimeSeriesDataPoint])
def get_metric_data(
    metric_code: str,
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    country_iso: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """Get timeseries data for a single metric"""
    return get_timeseries(
        metric_codes=metric_code,
        start_date=start_date,
        end_date=end_date,
        country_iso=country_iso,
        db=db
    )


@router.get("/pipeline-logs", response_model=List[UpdateLogResponse])
def get_pipeline_logs(
    pipeline_name: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db)
):
    """Get pipeline execution logs"""
    query = db.query(UpdateLog)
    if pipeline_name:
        query = query.filter_by(pipeline_name=pipeline_name)
    return query.order_by(UpdateLog.completed_at.desc()).limit(limit).all()


@router.get("/stats")
def get_stats(db: Session = Depends(get_db)):
    """Get database statistics"""
    total_metrics = db.query(Metric).count()
    total_countries = db.query(Country).count()
    total_timeseries = db.query(TimeSeries).count()

    date_range = db.query(
        func.min(TimeSeries.date).label("earliest"),
        func.max(TimeSeries.date).label("latest")
    ).first()

    return {
        "metrics": total_metrics,
        "countries": total_countries,
        "timeseries_records": total_timeseries,
        "data_earliest": date_range.earliest,
        "data_latest": date_range.latest,
    }


@router.post("/fetch/fred")
def trigger_fred_fetch(db: Session = Depends(get_db)):
    """Manually trigger a FRED data fetch"""
    try:
        result = run_fred_fetch(db)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/holdings")
def get_all_holdings(
    country_iso: Optional[str] = Query(None),
    date: Optional[datetime] = Query(None),
    db: Session = Depends(get_db)
):
    """
    Get Treasury holdings data by country.
    If date not provided, returns latest available date.
    """
    metric = db.query(Metric).filter_by(code="TIC_UST_HOLDINGS").first()
    if not metric:
        raise HTTPException(status_code=404, detail="Holdings data not yet loaded")
    
    query = db.query(
        Country.iso_code,
        Country.name,
        TimeSeries.date,
        TimeSeries.value
    ).join(TimeSeries).filter(
        TimeSeries.metric_id == metric.id,
        TimeSeries.country_id != None,
    )
    
    if country_iso:
        query = query.filter(Country.iso_code == country_iso)
    
    if not date:
        # Get latest date
        latest_date = db.query(func.max(TimeSeries.date)).filter(
            TimeSeries.metric_id == metric.id
        ).scalar()
        if latest_date:
            query = query.filter(TimeSeries.date == latest_date)
    else:
        query = query.filter(TimeSeries.date == date)
    
    results = query.order_by(TimeSeries.value.desc()).all()
    
    if not results:
        raise HTTPException(status_code=404, detail="No holdings data found")
    
    total = sum(float(r[3]) for r in results)
    
    return {
        "date": results[0][2].isoformat() if results else None,
        "total_billions_usd": round(float(total), 2),
        "holdings": [
            {
                "country_code": r[0],
                "country_name": r[1],
                "holdings_billions_usd": round(float(r[3]), 2),
                "percent_of_total": round((float(r[3]) / total) * 100, 1),
            }
            for r in results
        ]
    }



@router.get("/holdings/cross-asset-stress")
def get_cross_asset_stress(db: Session = Depends(get_db)):
    """
    Cross-asset stress: countries selling both Treasuries AND gold,
    with optional divergence multiplier when gold spot is rising.
    """
    try:
        from pipelines.experimental.gold_fetcher import compute_cross_asset_stress
        result = compute_cross_asset_stress(db)
        # Wrap into expected format
        cross = [r for r in result if r.get("cross_asset_stress") or r.get("divergence_signal")]
        treasury_only = [r for r in result if not r.get("cross_asset_stress") and not r.get("divergence_signal") and r.get("selling_treasuries")]
        gold_only = [r for r in result if not r.get("selling_treasuries") and r.get("selling_gold")]
        spot = result[0] if result else {}
        return {
            "cross_asset_stress": cross,
            "treasury_only_stress": treasury_only,
            "gold_only_stress": gold_only,
            "summary": {
                "cross_asset_stressed": len(cross),
                "treasury_only": len(treasury_only),
                "gold_only": len(gold_only),
                "total_stressed": len(result),
            },
            "spot_gold_rising": spot.get("spot_gold_rising"),
            "spot_gold_price": spot.get("spot_gold_price"),
            "spot_gold_3m_pct": spot.get("spot_gold_3m_pct"),
            "as_of": spot.get("tic_as_of"),
        }
    except Exception as e:
        logger.error(f"Cross-asset stress calculation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/holdings/{country_iso}")
def get_country_holdings(
    country_iso: str,
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    db: Session = Depends(get_db)
):
    """Get historical Treasury holdings for a specific country."""
    metric = db.query(Metric).filter_by(code="TIC_UST_HOLDINGS").first()
    if not metric:
        raise HTTPException(status_code=404, detail="Holdings data not yet loaded")
    
    country = db.query(Country).filter_by(iso_code=country_iso).first()
    if not country:
        raise HTTPException(status_code=404, detail=f"Country {country_iso} not found")
    
    query = db.query(TimeSeries).filter(
        TimeSeries.metric_id == metric.id,
        TimeSeries.country_id == country.id,
    )
    
    if not end_date:
        end_date = datetime.utcnow()
    if not start_date:
        start_date = end_date - timedelta(days=730)
    
    query = query.filter(
        TimeSeries.date >= start_date,
        TimeSeries.date <= end_date,
    )
    
    results = query.order_by(TimeSeries.date.asc()).all()
    
    return {
        "country_code": country_iso,
        "country_name": country.name,
        "data_points": len(results),
        "holdings": [
            {
                "date": r.date.isoformat(),
                "holdings_billions_usd": round(float(r.value), 2),
            }
            for r in results
        ]
    }


@router.get("/stress-score")
def get_stress_score(db: Session = Depends(get_db)):
    """
    Get current macroeconomic stress score.
    Scale: 0-100, where 0 = low stress, 100 = severe stress.
    Based on: yield curve spread, holdings concentration, commodity volatility.
    """
    from pipelines.stress_score_v2 import calculate_stress_score_v2 as calculate_stress_score
    
    try:
        result = calculate_stress_score(db)
        return result
    except Exception as e:
        logger.error(f"Stress score calculation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/fetch/treasury-holdings")
def trigger_treasury_fetch(db: Session = Depends(get_db)):
    """Manually trigger Treasury holdings fetch"""
    from pipelines.treasury_holdings import run_treasury_holdings_fetch
    
    try:
        result = run_treasury_holdings_fetch(db)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/gold-reserves")
def get_gold_reserves(
    country_iso: Optional[str] = Query(None),
    date: Optional[datetime] = Query(None),
    db: Session = Depends(get_db)
):
    """
    Get central bank gold reserves by country.
    Returns each country's most recent available value (dates vary due to
    reporting lags — e.g. some countries show AWAITED for the latest quarter).
    Units: metric tonnes.
    """
    metric = db.query(Metric).filter_by(code="GOLD_RESERVES").first()
    if not metric:
        raise HTTPException(status_code=404, detail="Gold reserves data not yet loaded")

    if date:
        # Specific date requested — single-date query
        results = db.query(
            Country.iso_code,
            Country.name,
            TimeSeries.date,
            TimeSeries.value
        ).join(TimeSeries).filter(
            TimeSeries.metric_id == metric.id,
            TimeSeries.country_id != None,
            TimeSeries.date == date,
            TimeSeries.value > 0,
        )
        if country_iso:
            results = results.filter(Country.iso_code == country_iso)
        results = results.order_by(TimeSeries.value.desc()).all()
    else:
        # Per-country latest: subquery gets max date per country_id
        latest_per_country = db.query(
            TimeSeries.country_id,
            func.max(TimeSeries.date).label("max_date")
        ).filter(
            TimeSeries.metric_id == metric.id,
            TimeSeries.country_id != None,
            TimeSeries.value > 0,
        ).group_by(TimeSeries.country_id).subquery()

        query = db.query(
            Country.iso_code,
            Country.name,
            TimeSeries.date,
            TimeSeries.value
        ).join(
            TimeSeries, TimeSeries.country_id == Country.id
        ).join(
            latest_per_country,
            (TimeSeries.country_id == latest_per_country.c.country_id) &
            (TimeSeries.date == latest_per_country.c.max_date)
        ).filter(
            TimeSeries.metric_id == metric.id,
        )

        if country_iso:
            query = query.filter(Country.iso_code == country_iso)

        results = query.order_by(TimeSeries.value.desc()).all()

    if not results:
        raise HTTPException(status_code=404, detail="No gold reserves data found")

    total_tonnes = sum(float(r[3]) for r in results)

    return {
        "as_of": "per-country latest (varies by reporting lag)",
        "total_metric_tonnes": round(total_tonnes, 1),
        "country_count": len(results),
        "reserves": [
            {
                "country_code": r[0],
                "country_name": r[1],
                "as_of_date": f"{r[2].year}-Q{(r[2].month - 1) // 3 + 1}" if r[2] else None,
                "metric_tonnes": round(float(r[3]), 1),
                "percent_of_total": round((float(r[3]) / total_tonnes) * 100, 1),
            }
            for r in results
        ]
    }


@router.get("/gold-reserves/{country_iso}")
def get_country_gold_reserves(
    country_iso: str,
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    db: Session = Depends(get_db)
):
    """Get historical gold reserves for a specific country."""
    metric = db.query(Metric).filter_by(code="GOLD_RESERVES").first()
    if not metric:
        raise HTTPException(status_code=404, detail="Gold reserves data not yet loaded")

    country = db.query(Country).filter_by(iso_code=country_iso).first()
    if not country:
        raise HTTPException(status_code=404, detail=f"Country {country_iso} not found")

    if not end_date:
        end_date = datetime.utcnow()
    if not start_date:
        start_date = end_date - timedelta(days=3650)

    results = db.query(TimeSeries).filter(
        TimeSeries.metric_id == metric.id,
        TimeSeries.country_id == country.id,
        TimeSeries.date >= start_date,
        TimeSeries.date <= end_date,
    ).order_by(TimeSeries.date.asc()).all()

    return {
        "country_code": country_iso,
        "country_name": country.name,
        "data_points": len(results),
        "reserves": [
            {
                "date": r.date.isoformat(),
                "metric_tonnes": round(float(r.value), 1),
            }
            for r in results
        ]
    }


@router.post("/fetch/gold-reserves")
def trigger_gold_fetch(db: Session = Depends(get_db)):
    """Manually trigger gold reserves fetch"""
    from pipelines.gold_reserves import run_gold_reserves_fetch
    try:
        result = run_gold_reserves_fetch(db)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/analyze/country")
async def analyze_country(payload: dict, db: Session = Depends(get_db)):
    """
    Generate sovereign analysis using Grok (replaces Claude).
    Expects: { "prompt": "..." }
    Returns: { "text": "..." }
    """
    if not settings.grok_api_key:
        raise HTTPException(status_code=503, detail="GROK_API_KEY not configured")

    prompt = payload.get("prompt", "")
    if not prompt:
        raise HTTPException(status_code=400, detail="prompt required")

    system_prompt = (
        "You are a brutally honest sovereign risk analyst. "
        "No sugarcoating. Focus on maximal truth and structural realities. "
        "Be direct and specific with numbers and implications."
    )

    payload_data = {
        "model": "grok-2-latest",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.35,
        "max_tokens": 750,
    }

    headers = {
        "Authorization": f"Bearer {settings.grok_api_key}",
        "Content-Type": "application/json"
    }

    try:
        async with httpx.AsyncClient(timeout=75.0) as client:
            response = await client.post(
                "https://api.x.ai/v1/chat/completions",
                json=payload_data,
                headers=headers
            )
            response.raise_for_status()
            data = response.json()
            text = data["choices"][0]["message"]["content"].strip()
            return {"text": text}
    except Exception as e:
        logger.error(f"Grok API call failed: {e}")
        raise HTTPException(status_code=502, detail=f"Grok analysis failed: {str(e)}")


@router.get("/cds/all")
async def get_all_cds(db: Session = Depends(get_db)):
    """
    Returns latest 5Y and 10Y CDS for all countries that have data.
    Used by the CDS Tab.
    """
    from sqlalchemy import func as sqlfunc

    cds5y_metrics = db.query(Metric).filter(
        Metric.code.like("%_CDS_5Y")
    ).all()

    results = []

    for metric5y in cds5y_metrics:
        country_code = metric5y.code.replace("_CDS_5Y", "")

        cds5y = get_latest_metric_value(db, metric5y.code)
        cds10y = get_latest_metric_value(db, f"{country_code}_CDS_10Y")

        term_spread = None
        if cds5y is not None and cds10y is not None:
            term_spread = round(cds10y - cds5y, 1)

        results.append({
            "country_iso": country_code,
            "country_name": country_code,
            "cds_5y": cds5y,
            "cds_10y": cds10y,
            "cds_term_spread": term_spread
        })

    results.sort(key=lambda x: (x["cds_5y"] or 0), reverse=True)
    return results

@router.get("/stress/composite")
def get_composite_stress(db: Session = Depends(get_db)):
    """
    5-dimension composite sovereign stress scorer.
    Scores all countries on: Treasury MoM + consecutive months,
    Gold reserves trend, M2 monetary growth, Sovereign spread vs US 10Y,
    Petrodollar / oil pressure.
    Applies cross-asset (1.5x) and divergence (2.0x) multipliers.
    Returns tiered results: CRISIS / STRESSED / ELEVATED / WATCH.
    """
    try:
        from pipelines.experimental.composite_stress import compute_composite_stress
        result = compute_composite_stress(db)
        return result
    except Exception as e:
        logger.error(f"Composite stress calculation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/holdings/country/{iso_code}")
def get_country_tic_history(
    iso_code: str,
    months: int = Query(24, ge=1, le=120),
    db: Session = Depends(get_db)
):
    """Get TIC holdings history for a specific country (legacy endpoint)."""
    metric = db.query(Metric).filter_by(code="TIC_UST_HOLDINGS").first()
    if not metric:
        raise HTTPException(status_code=404, detail="TIC data not loaded")

    country = db.query(Country).filter_by(iso_code=iso_code).first()
    if not country:
        raise HTTPException(status_code=404, detail=f"Country {iso_code} not found")

    cutoff = datetime.utcnow() - timedelta(days=months * 31)
    rows = db.query(TimeSeries).filter(
        TimeSeries.metric_id == metric.id,
        TimeSeries.country_id == country.id,
        TimeSeries.date >= cutoff,
    ).order_by(TimeSeries.date.asc()).all()

    history = []
    for i, r in enumerate(rows):
        mom = None
        if i > 0:
            prev = float(rows[i-1].value)
            if prev:
                mom = round((float(r.value) - prev) / prev * 100, 2)
        history.append({
            "date": r.date.strftime("%Y-%m"),
            "holdings_bn": round(float(r.value), 2),
            "mom_change_pct": mom,
        })

    latest = float(rows[-1].value) if rows else None
    peak = max((float(r.value) for r in rows), default=None)

    return {
        "country": {"iso": iso_code, "name": country.name, "region": country.region},
        "summary": {
            "latest_holdings_bn": round(latest, 2) if latest else None,
            "peak_holdings_bn": round(peak, 2) if peak else None,
            "drawdown_from_peak_pct": round((latest - peak) / peak * 100, 1) if latest and peak and peak > 0 else None,
            "months": len(rows),
        },
        "history": history,
    }
from fastapi import Query
from typing import Optional

@router.get("/cds")
async def get_latest_cds(country: str = Query(..., description="Country ISO code (e.g. TUR, MEX, BRA)"), db: Session = Depends(get_db)):
    """
    Returns the latest 5Y and 10Y CDS values for a country.
    Used by the frontend to enrich Grok analysis prompts.
    """
    country_upper = country.upper()

    cds5y_code = f"{country_upper}_CDS_5Y"
    cds10y_code = f"{country_upper}_CDS_10Y"

    cds5y = get_latest_metric_value(db, cds5y_code)
    cds10y = get_latest_metric_value(db, cds10y_code)

    if cds5y is None and cds10y is None:
        return {
            "country": country_upper,
            "5Y": None,
            "10Y": None,
            "term_spread": None,
            "message": "No CDS data available for this country"
        }

    term_spread = None
    if cds5y is not None and cds10y is not None:
        term_spread = round(cds10y - cds5y, 1)

    return {
        "country": country_upper,
        "5Y": {
            "value": cds5y,
            "unit": "bps"
        } if cds5y is not None else None,
        "10Y": {
            "value": cds10y,
            "unit": "bps"
        } if cds10y is not None else None,
        "term_spread": term_spread
        
    }