from pydantic import BaseModel
from datetime import datetime
from decimal import Decimal
from typing import List, Optional


class MetricBase(BaseModel):
    code: str
    name: str
    category: str
    unit: str
    source: str
    description: Optional[str] = None


class MetricResponse(MetricBase):
    id: int
    created_at: datetime
    
    class Config:
        from_attributes = True


class CountryBase(BaseModel):
    iso_code: str
    name: str
    region: Optional[str] = None


class CountryResponse(CountryBase):
    id: int
    created_at: datetime
    
    class Config:
        from_attributes = True


class TimeSeriesBase(BaseModel):
    metric_id: int
    country_id: Optional[int] = None
    date: datetime
    value: Decimal


class TimeSeriesResponse(TimeSeriesBase):
    id: int
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class TimeSeriesDataPoint(BaseModel):
    """Flattened response for time series queries"""
    date: datetime
    value: float
    metric_code: str
    metric_name: str
    country_code: Optional[str] = None
    country_name: Optional[str] = None


class TimeSeriesQuery(BaseModel):
    """Query parameters for time series data"""
    metric_codes: List[str]
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    country_iso: Optional[str] = None


class UpdateLogResponse(BaseModel):
    id: int
    pipeline_name: str
    status: str
    records_inserted: int
    records_updated: int
    error_message: Optional[str] = None
    started_at: datetime
    completed_at: datetime
    
    class Config:
        from_attributes = True


class HealthResponse(BaseModel):
    status: str
    database: str
    scheduler: str
    last_fred_update: Optional[datetime] = None
    last_treasury_update: Optional[datetime] = None
    last_gold_update: Optional[datetime] = None
