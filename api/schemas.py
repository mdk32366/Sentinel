from pydantic import ConfigDict, Field, BaseModel
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


# ─────────────────────────────────────────────────────────────────────────────
# F-0049 — the remaining E2 endpoints, modelled from production shapes
# ─────────────────────────────────────────────────────────────────────────────

class CdsAllItem(BaseModel):
    """A row of GET /api/cds/all.

    `country_iso` carries the CDS metric namespace's own country token (e.g.
    "RUSSIA"), taken from the `{COUNTRY}_CDS_5Y` metric code. It is NOT an
    ISO-3166 code and is not the `countries.iso_code` used elsewhere.
    """
    country_iso: str
    country_name: str
    cds_5y: float
    # D-0063: carried by the source and previously discarded. implied_pd_pct
    # is the spread rescaled by a constant 1/60 (F-0080) - readable, not
    # independent, and never scored.
    implied_pd_pct: Optional[float] = None
    var_6m_pct: Optional[float] = None
    cds_10y: Optional[float] = None
    cds_term_spread: Optional[float] = None
    as_of: str
    source: str
    # F-0074: why a tenor is blank, when it is blank. A country nobody quotes
    # and a country whose quote was refused as stale or as not-a-running-spread
    # both render as "—", and the reader has to be able to tell which.
    coverage_5y: Optional[str] = None
    coverage_10y: Optional[str] = None


class CdsTenor(BaseModel):
    value: float
    unit: str
    as_of: Optional[str] = None
    source: Optional[str] = None


class CdsHistoryPoint(BaseModel):
    date: str
    value: float


class CdsCountryResponse(BaseModel):
    """GET /api/cds?country=X.

    Two shapes in production: with data it carries the tenor objects; without
    it carries `message` and nulls. One model covers both rather than
    pretending the empty case does not exist - a model that rejected it would
    turn "no CDS for this country" into a 500.
    """
    country: str
    five_year: Optional[CdsTenor] = Field(None, alias="5Y")
    ten_year: Optional[CdsTenor] = Field(None, alias="10Y")
    term_spread: Optional[float] = None
    as_of: Optional[str] = None
    source: Optional[str] = None
    message: Optional[str] = None

    model_config = ConfigDict(populate_by_name=True)

    # F-0074 / D-0061: why a tenor is blank, and the series behind the
    # 5Y number so the country panel can chart it.
    coverage: Optional[str] = None
    coverage_10y: Optional[str] = None
    history: List[CdsHistoryPoint] = []


class CrossAssetItem(BaseModel):
    country_iso: str
    country_name: str
    region: Optional[str] = None
    tic_holdings_bn: float
    tic_mom_pct: Optional[float] = None
    tic_consecutive_months: int
    no_tic_holdings: bool
    gold_tonnes: Optional[float] = None
    gold_mom_pct: Optional[float] = None
    gold_consecutive_months: int
    treseg_signal: str
    treseg_trend_pct: Optional[float] = None
    treseg_latest_bn: Optional[float] = None
    spot_gold_price: float
    spot_gold_3m_pct: float
    spot_gold_rising: bool
    selling_treasuries: bool
    selling_gold: bool
    cross_asset_stress: bool
    divergence_signal: bool
    signal_tier: str
    score_before_multiplier: float
    multiplier: float
    stress_score: float
    alert: bool
    tic_as_of: str
    gold_as_of: str


class CrossAssetStressResponse(BaseModel):
    cross_asset_stress: List[CrossAssetItem]
    treasury_only_stress: List[CrossAssetItem]
    gold_only_stress: List[CrossAssetItem]
    summary: dict
    spot_gold_rising: bool
    spot_gold_price: float
    spot_gold_3m_pct: float
    as_of: str


class CompositeCountry(BaseModel):
    country_iso: str
    country_name: str
    region: Optional[str] = None
    tier: str
    composite_score: float
    raw_score: float
    multiplier: float
    tic_holdings_bn: float
    tic_mom_pct: Optional[float] = None
    tic_consecutive_months: int
    tic_score: float
    no_tic_holdings: bool
    gold_tonnes: Optional[float] = None
    gold_mom_pct: Optional[float] = None
    gold_consecutive_quarters: int
    gold_score: float
    m2_growth_pct: Optional[float] = None
    m2_year: Optional[int] = None
    # F-0092. Declared because response_model is a FILTER, not a validator
    # (F-0079): an undeclared field is stripped silently, which is how the
    # entire CDS dimension once vanished between the scorer and the screen.
    m2_stale: bool = False
    # F-0097. Declared for the same reason as m2_stale: response_model strips
    # undeclared fields silently (F-0079), and a stripped tic_state would leave
    # the UI unable to tell a real liquidation from a country that simply fell
    # below the major-holder reporting threshold.
    tic_state: str = "reported"
    tic_last_reported_bn: Optional[float] = None
    tic_last_reported_date: Optional[str] = None
    monetary_score: int
    spread_bps: Optional[float] = None
    spread_widening_bps: Optional[float] = None
    # D-0066: spread_score removed. A field that is always zero is a trap -
    # a reader takes it for a dimension that happens to be quiet.
    oil_dependent: bool
    oil_signal: Optional[str] = None
    petro_score: int
    treseg_signal: str
    treseg_trend_pct: Optional[float] = None
    treseg_latest_bn: Optional[float] = None
    spot_gold_price: float
    spot_gold_rising: bool
    selling_treasuries: bool
    selling_gold: bool
    cross_asset: bool
    divergence: bool
    # F-0082. Everything below was produced by the scorer and STRIPPED here:
    # a FastAPI response_model drops any field it does not declare, silently.
    #
    # The CDS dimension therefore never reached the UI at all. The COMPOSITE
    # table's CDS column, the CDS tab's "CDS Share" column and the country
    # panel's StressContribution breakdown were all reading a field the API
    # removed on the way out - every one of them rendering a dash.
    #
    # `active_signals` is the Activity column's entire content, which is why
    # that column was the widest on the table and almost always empty.
    active_signals: List[str] = []
    as_of: Optional[str] = None
    brent_price: Optional[float] = None
    brent_3m_pct: Optional[float] = None
    cds_5y: Optional[float] = None
    cds_10y: Optional[float] = None
    cds_term_spread: Optional[float] = None
    cds_widening_pct: Optional[float] = None
    cds_score: float = 0
    cds_coverage: Optional[str] = None
    cds_coverage_10y: Optional[str] = None


class CompositeStressResponse(BaseModel):
    """GET /api/stress/composite.

    `computed_at` and `served_from` are present on live responses (D-0042) and
    absent from a snapshot payload stored before that decision, so both are
    optional.
    """
    crisis: List[CompositeCountry]
    stressed: List[CompositeCountry]
    elevated: List[CompositeCountry]
    watch: List[CompositeCountry]
    summary: dict
    as_of: Optional[str] = None
    computed_at: Optional[str] = None
    served_from: Optional[str] = None
