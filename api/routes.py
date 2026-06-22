from pipelines.tic_fetcher import run_tic_fetch, compute_stress_scores
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
    # Add these routes to api/routes.py
# Also add to imports at top: from pipelines.tic_fetcher import run_tic_fetch, compute_stress_scores

@router.post("/fetch/tic")
def trigger_tic_fetch(db: Session = Depends(get_db)):
    """Manually trigger a TIC holdings data fetch"""
    try:
        from pipelines.tic_fetcher import run_tic_fetch
        result = run_tic_fetch(db)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/holdings/stress")
def get_stress_leaderboard(
    min_score: float = Query(0, description="Minimum stress score to include"),
    alerts_only: bool = Query(False, description="Only return countries with active alerts"),
    db: Session = Depends(get_db)
):
    """
    Sovereign stress leaderboard — countries showing signs of forced selling.

    Stress score components:
    - MoM decline magnitude (0-40 pts)
    - Consecutive declining months (0-30 pts)
    - Acceleration of decline (0-20 pts)

    Alert threshold: score >= 25 OR 3+ consecutive declining months.
    """
    from pipelines.tic_fetcher import compute_stress_scores
    from database.models import Metric
    
    metric = db.query(Metric).filter_by(code="TIC_HOLDINGS").first()
    if not metric:
        raise HTTPException(status_code=404, detail="TIC holdings data not yet loaded. Run /fetch/tic first.")
    
    scores = compute_stress_scores(db, metric)
    
    if alerts_only:
        scores = [s for s in scores if s["alert"]]
    if min_score > 0:
        scores = [s for s in scores if s["stress_score"] >= min_score]
    
    return {
        "as_of": scores[0]["as_of"] if scores else None,
        "total_countries_under_stress": len(scores),
        "alerts": [s for s in scores if s["alert"]],
        "watch_list": [s for s in scores if not s["alert"]],
    }


@router.get("/holdings/country/{iso_code}")
def get_country_holdings(
    iso_code: str,
    months: int = Query(120, description="Number of months of history"),
    db: Session = Depends(get_db)
):
    """
    Full holdings history for a single country with MoM changes.
    """
    from database.models import Metric, Country, TimeSeries
    
    metric = db.query(Metric).filter_by(code="TIC_HOLDINGS").first()
    if not metric:
        raise HTTPException(status_code=404, detail="TIC data not loaded")
    
    country = db.query(Country).filter_by(iso_code=iso_code.upper()).first()
    if not country:
        raise HTTPException(status_code=404, detail=f"Country {iso_code} not found")
    
    cutoff = datetime.utcnow() - timedelta(days=months * 31)
    history = db.query(TimeSeries).filter(
        TimeSeries.metric_id == metric.id,
        TimeSeries.country_id == country.id,
        TimeSeries.date >= cutoff,
    ).order_by(TimeSeries.date.asc()).all()
    
    result = []
    for i, row in enumerate(history):
        mom_pct = None
        if i > 0:
            prev_val = float(history[i-1].value)
            if prev_val != 0:
                mom_pct = round((float(row.value) - prev_val) / prev_val * 100, 2)
        
        result.append({
            "date": row.date.strftime("%Y-%m"),
            "holdings_bn": round(float(row.value), 2),
            "mom_change_pct": mom_pct,
            "declining": mom_pct is not None and mom_pct < 0,
        })
    
    # Summary stats
    declining_months = sum(1 for r in result if r["declining"])
    
    return {
        "country": {"iso": country.iso_code, "name": country.name, "region": country.region},
        "summary": {
            "latest_holdings_bn": result[-1]["holdings_bn"] if result else None,
            "peak_holdings_bn": max((r["holdings_bn"] for r in result), default=None),
            "declining_months_in_period": declining_months,
            "pct_of_months_declining": round(declining_months / len(result) * 100, 1) if result else None,
        },
        "history": result,
    }


@router.get("/holdings/summary")
def get_holdings_summary(db: Session = Depends(get_db)):
    """
    Top and bottom movers in treasury holdings this month.
    """
    from pipelines.tic_fetcher import compute_stress_scores
    from database.models import Metric, TimeSeries, Country
    from sqlalchemy import func
    
    metric = db.query(Metric).filter_by(code="TIC_HOLDINGS").first()
    if not metric:
        raise HTTPException(status_code=404, detail="TIC data not loaded")
    
    # Get latest date
    latest_date = db.query(func.max(TimeSeries.date)).filter(
        TimeSeries.metric_id == metric.id
    ).scalar()
    
    if not latest_date:
        return {"error": "No data available"}
    
    # Get all latest values
    latest_rows = db.query(TimeSeries, Country).join(
        Country, TimeSeries.country_id == Country.id
    ).filter(
        TimeSeries.metric_id == metric.id,
        TimeSeries.date == latest_date,
    ).order_by(TimeSeries.value.desc()).all()
    
    total = sum(float(r.TimeSeries.value) for r in latest_rows)
    
    stress_scores = compute_stress_scores(db, metric)
    stress_map = {s["country_iso"]: s for s in stress_scores}
    
    countries = []
    for row in latest_rows:
        iso = row.Country.iso_code
        stress = stress_map.get(iso, {})
        countries.append({
            "iso": iso,
            "name": row.Country.name,
            "region": row.Country.region,
            "holdings_bn": round(float(row.TimeSeries.value), 2),
            "share_pct": round(float(row.TimeSeries.value) / total * 100, 2) if total else 0,
            "mom_change_pct": stress.get("mom_change_pct"),
            "consecutive_declining": stress.get("consecutive_declining_months", 0),
            "stress_score": stress.get("stress_score", 0),
            "alert": stress.get("alert", False),
        })
    
    return {
        "as_of": latest_date.strftime("%Y-%m"),
        "total_foreign_holdings_bn": round(total, 2),
        "countries_reporting": len(countries),
        "top_holders": countries[:10],
        "most_stressed": sorted(countries, key=lambda x: x["stress_score"], reverse=True)[:10],
        "biggest_buyers": sorted(
            [c for c in countries if c["mom_change_pct"] is not None and c["mom_change_pct"] > 0],
            key=lambda x: x["mom_change_pct"], reverse=True
        )[:5],
        "biggest_sellers": sorted(
            [c for c in countries if c["mom_change_pct"] is not None and c["mom_change_pct"] < 0],
            key=lambda x: x["mom_change_pct"]
        )[:5],
    }
# Add these to api/routes.py
# Add to imports: from pipelines.gold_fetcher import run_gold_fetch, compute_cross_asset_stress


@router.post("/fetch/gold-price")
def trigger_gold_price_import(db: Session = Depends(get_db)):
    """Import historical spot gold price from WGC CSV."""
    try:
        from pipelines.gold_price_import import run_gold_price_import
        result = run_gold_price_import(db)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@router.get("/holdings/cross-asset-stress")
def get_cross_asset_stress(db: Session = Depends(get_db)):
    """
    Cross-asset stress leaderboard — countries selling BOTH treasuries AND gold.

    This is the highest-priority distress signal. A country reducing treasury
    holdings is repositioning. A country reducing BOTH treasuries AND gold
    is a forced seller under acute financial stress.

    Score receives a 1.5x multiplier when both assets are declining.
    Alert threshold: cross_asset=true OR score >= 30.
    """
    from pipelines.gold_fetcher import compute_cross_asset_stress
    results = compute_cross_asset_stress(db)

    cross_asset = [r for r in results if r["cross_asset_stress"]]
    treasury_only = [r for r in results if r["selling_treasuries"] and not r["cross_asset_stress"]]
    gold_only = [r for r in results if r["selling_gold"] and not r["cross_asset_stress"]]

    return {
        "summary": {
            "cross_asset_stressed": len(cross_asset),
            "treasury_only": len(treasury_only),
            "gold_only": len(gold_only),
            "highest_risk": cross_asset[0] if cross_asset else None,
        },
        "cross_asset_stress": cross_asset,
        "treasury_only_stress": treasury_only,
        "gold_only_stress": gold_only,
    }


@router.get("/holdings/gold/{iso_code}")
def get_country_gold(
    iso_code: str,
    months: int = Query(36, description="Months of history"),
    db: Session = Depends(get_db)
):
    """Gold reserve history for a single country with MoM changes."""
    from database.models import Metric, Country, TimeSeries

    metric = db.query(Metric).filter_by(code="GOLD_RESERVES").first()
    if not metric:
        raise HTTPException(status_code=404, detail="Gold data not loaded. Run /fetch/gold first.")

    country = db.query(Country).filter_by(iso_code=iso_code.upper()).first()
    if not country:
        raise HTTPException(status_code=404, detail=f"Country {iso_code} not found")

    cutoff = datetime.utcnow() - timedelta(days=months * 31)
    history = db.query(TimeSeries).filter(
        TimeSeries.metric_id == metric.id,
        TimeSeries.country_id == country.id,
        TimeSeries.date >= cutoff,
    ).order_by(TimeSeries.date.asc()).all()

    result = []
    for i, row in enumerate(history):
        mom_pct = None
        if i > 0:
            prev = float(history[i-1].value)
            if prev != 0:
                mom_pct = round((float(row.value) - prev) / prev * 100, 3)
        result.append({
            "date": row.date.strftime("%Y-%m"),
            "tonnes": round(float(row.value), 2),
            "mom_change_pct": mom_pct,
            "declining": mom_pct is not None and mom_pct < 0,
        })

    peak = max((r["tonnes"] for r in result), default=None)
    drawdown = None
    if result and peak:
        latest = result[-1]["tonnes"]
        drawdown = round((latest - peak) / peak * 100, 2)

    return {
        "country": {"iso": country.iso_code, "name": country.name, "region": country.region},
        "summary": {
            "latest_tonnes": result[-1]["tonnes"] if result else None,
            "peak_tonnes": peak,
            "drawdown_from_peak_pct": drawdown,
            "declining_months": sum(1 for r in result if r["declining"]),
        },
        "history": result,
    }

 
@router.post("/fetch/gold") 
def trigger_gold_fetch(db: Session = Depends(get_db)): 
    """Import WGC gold reserves snapshot CSV.""" 
    try: 
        from pipelines.gold_fetcher import run_gold_fetch 
        result = run_gold_fetch(db) 
        return result 
    except Exception as e: 
        raise HTTPException(status_code=500, detail=str(e)) 
