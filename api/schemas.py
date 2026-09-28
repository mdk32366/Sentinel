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


# ─────────────────────────────────────────────────────────────────────────────
# ORDER-03 E2 — response models for the endpoints App.jsx consumes
#
# Declared only where every field has been OBSERVED populated. Two of the seven
# named in E2 are deliberately left unmodelled; see F-0049 for why guessing the
# type behind a field that is null in every local row is worse than leaving it
# undeclared.
# ─────────────────────────────────────────────────────────────────────────────

class HoldingItem(BaseModel):
    country_code: str
    country_name: str
    holdings_billions_usd: float
    percent_of_total: float


class HoldingsResponse(BaseModel):
    date: str
    total_billions_usd: float
    holdings: List[HoldingItem]


class GoldReserveItem(BaseModel):
    country_code: str
    country_name: str
    as_of_date: str
    metric_tonnes: float
    percent_of_total: float


class GoldReservesResponse(BaseModel):
    as_of: str
    total_metric_tonnes: float
    country_count: int
    reserves: List[GoldReserveItem]
