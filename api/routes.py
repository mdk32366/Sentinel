from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
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
    # Get latest update logs
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
    category: Optional[str] = Query(None, description="Filter by category (e.g., 'treasury', 'oil', 'gold')"),
    db: Session = Depends(get_db)
):
    """List all available metrics"""
    query = db.query(Metric)
    if category:
        query = query.filter_by(category=category)
    metrics = query.all()
    return metrics


@router.get("/countries", response_model=List[CountryResponse])
def list_countries(db: Session = Depends(get_db)):
    """List all countries with data"""
    countries = db.query(Country).order_by(Country.name).all()
    return countries


@router.get("/timeseries", response_model=List[TimeSeriesDataPoint])
def get_timeseries(
    metric_codes: str = Query(..., description="Comma-separated list of metric codes (e.g., 'DGS10,DCOILWTICO')"),
    start_date: Optional[datetime] = Query(None, description="Start date (ISO format)"),
    end_date: Optional[datetime] = Query(None, description="End date (ISO format)"),
    country_iso: Optional[str] = Query(None, description="Filter by country ISO code"),
    db: Session = Depends(get_db)
):
    """
    Query timeseries data for one or more metrics
    
    Example: GET /api/timeseries?metric_codes=DGS10,DCOILWTICO&start_date=2022-01-01
    """
    codes = [code.strip() for code in metric_codes.split(",")]
    
    # Validate metric codes exist
    metrics = db.query(Metric).filter(Metric.code.in_(codes)).all()
    if not metrics:
        raise HTTPException(status_code=404, detail=f"No metrics found for codes: {codes}")
    
    metric_ids = [m.id for m in metrics]
    
    # Set default date range if not provided
    if not end_date:
        end_date = datetime.utcnow()
    if not start_date:
        start_date = end_date - timedelta(days=730)  # Default 2 years
    
    # Build query
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
    
    # Format response
    data_points = [
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
    
    return data_points


@router.get("/metric/{metric_code}", response_model=List[TimeSeriesDataPoint])
def get_metric_data(
    metric_code: str,
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    country_iso: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """
    Get timeseries data for a single metric
    
    Shorthand for /timeseries with single metric_code
    """
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
    """
    Get pipeline execution logs
    
    Useful for monitoring pipeline health and debugging
    """
    query = db.query(UpdateLog)
    if pipeline_name:
        query = query.filter_by(pipeline_name=pipeline_name)
    
    logs = query.order_by(UpdateLog.completed_at.desc()).limit(limit).all()
    return logs


@router.get("/stats")
def get_stats(db: Session = Depends(get_db)):
    """Get database statistics"""
    total_metrics = db.query(Metric).count()
    total_countries = db.query(Country).count()
    total_timeseries = db.query(TimeSeries).count()
    
    # Date range of data
    date_range = db.query(
        TimeSeries.date.min().label("earliest"),
        TimeSeries.date.max().label("latest")
    ).first()
    
    return {
        "metrics": total_metrics,
        "countries": total_countries,
        "timeseries_records": total_timeseries,
        "data_earliest": date_range.earliest,
        "data_latest": date_range.latest,
    }
