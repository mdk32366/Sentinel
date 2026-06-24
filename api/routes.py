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
    from pipelines.stress_score import calculate_stress_score_v2 as calculate_stress_score
    
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
    Units: fine troy ounces. If date not provided, returns latest available date.
    """
    metric = db.query(Metric).filter_by(code="GOLD_RESERVES").first()
    if not metric:
        raise HTTPException(status_code=404, detail="Gold reserves data not yet loaded")

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
        latest_date = db.query(func.max(TimeSeries.date)).filter(
            TimeSeries.metric_id == metric.id
        ).scalar()
        if latest_date:
            query = query.filter(TimeSeries.date == latest_date)
    else:
        query = query.filter(TimeSeries.date == date)

    results = query.order_by(TimeSeries.value.desc()).all()
    if not results:
        raise HTTPException(status_code=404, detail="No gold reserves data found")

    total_tonnes = sum(float(r[3]) for r in results)

    return {
        "date": results[0][2].isoformat() if results else None,
        "total_metric_tonnes": round(total_tonnes, 1),
        "reserves": [
            {
                "country_code": r[0],
                "country_name": r[1],
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
