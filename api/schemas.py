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
    # D-0094: last_gold_update means Gold_Reserves (kept for compatibility).
    last_gold_update: Optional[datetime] = None
    # D-0094: Gold_Spot_Price gets its own fields. A failed run is visible.
    last_gold_price_run: Optional[datetime] = None
    last_gold_price_status: Optional[str] = None
    last_gold_price_failure: Optional[str] = None  # kind token, never raw text
    last_gold_price_success: Optional[datetime] = None


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
    # D-0085. Sixteen reporters publish `n.a.` for their TOTAL position and a
    # real long-term figure. Their holdings are long-term only and must be
    # labelled as such rather than compared with a total (F-0097's lesson: one
    # measure quietly presented as another).
    long_term_only: bool = False
    # D-0087. The movement and what kind it was. A change in holdings is not
    # self-explanatory: Japan's July was -$12.7bn of position and +$0.9bn of
    # transactions, so it bought while its position fell.
    change_1m_bn: Optional[float] = None
    change_1m_pct: Optional[float] = None
    net_1m_bn: Optional[float] = None
    valuation_1m_bn: Optional[float] = None
    net_3m_bn: Optional[float] = None
    movement: Optional[str] = None
    movement_note: Optional[str] = None


class HoldingsResponse(BaseModel):
    date: str
    total_billions_usd: float
    # D-0085. The figure Treasury publishes for ALL foreign holdings, from SLT
    # Table 5's Grand Total row (D-0079). `total_billions_usd` is the sum of
    # the countries listed below and is smaller - it was labelled "Total Foreign
    # Holdings" on the tab while understating the real total by $537.8bn.
    grand_total_billions_usd: Optional[float] = None
    coverage_pct: Optional[float] = None
    country_count: Optional[int] = None
    long_term_only_count: Optional[int] = None
    holdings: List[HoldingItem]


class GoldReserveItem(BaseModel):
    country_code: str
    country_name: str
    as_of_date: str
    metric_tonnes: float
    percent_of_total: float
    # D-0087. Gold is held in TONNES, a pure quantity, so unlike Treasuries
    # there is no price component to separate out - a change here is always a
    # decision. The "kind" of movement is therefore direction and persistence,
    # which is what dimension 2 actually scores.
    change_1m_tonnes: Optional[float] = None
    change_3m_tonnes: Optional[float] = None
    change_3m_pct: Optional[float] = None
    consecutive_declines: Optional[int] = None
    movement: Optional[str] = None
    movement_note: Optional[str] = None


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

    `country_iso3` (D-0091 / F-0106) is that ISO-3166 alpha-3 code, derived on
    the server from `ISO_BY_CDS_NAME`, or null for a token the map does not
    know. It is what the UI links to the country card with. It must be
    declared here: `response_model` strips undeclared fields silently
    (F-0079 / F-0082).
    """
    country_iso: str
    country_iso3: Optional[str] = None
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
    # F-0101. F-0097 added these to gold_fetcher.py and to the CROSS-ASSET tab
    # and did NOT declare them here, so response_model stripped them and the
    # "n/r" rendering never once appeared. The same defect as F-0082, found by
    # reading the live payload rather than by any test: the composite contract
    # test covers CompositeCountry and nothing covered this model.
    tic_state: Optional[str] = None
    tic_last_reported_bn: Optional[float] = None
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
    # F-0113: every exited country, whichever stress list it falls in or none.
    exited: List[CrossAssetItem] = []
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
    # D-0083 / A-0021. Declared because response_model is a filter, not a
    # validator (F-0079): an undeclared field is stripped in silence, and the
    # whole point of these is that a reader sees them beside the score.
    tic_net_1m_bn: Optional[float] = None
    tic_valuation_1m_bn: Optional[float] = None
    tic_net_3m_bn: Optional[float] = None
    tic_flow_months: Optional[int] = None
    # D-0084. What dimension 1's magnitude was built from, so the surface can
    # say rather than present a bare number.
    tic_3m_pct: Optional[float] = None
    tic_st_drawdown_pct: Optional[float] = None
    tic_magnitude_basis: str = "none"
    tic_price_driven: bool = False
    # A-0017. Dimension 2 will not score a gold reading older than 200 days.
    # The tonnage is still reported - "Venezuela last reported 161t in 2018" is
    # worth seeing - so the flag has to travel with it.
    gold_stale: bool = False
    # D-0089. How much of the 165-point model could speak about this
    # country, and the score as a rate of it. The rescaling the option proposed
    # is deliberately NOT here: it makes Malta read 77.0 - a CRISIS - on 60
    # points of evidence, outranking Japan measured on all of it.
    available_points: Optional[int] = None
    score_pct_of_available: Optional[float] = None
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


# ── Treasury auction demand (ORDER auction-demand §6, D-0098..D-0104) ────────
#
# A filter, like every response_model here: a key the producer sends and the
# model does not declare is dropped without error (F-0079 / F-0101). The
# producer is api.routes._auction_row; tests/test_treasury_auctions.py holds
# the two shut against each other.

class AuctionRow(BaseModel):
    cusip: str
    auction_date: str
    issue_date: Optional[str] = None
    maturity_date: Optional[str] = None
    security_type: str
    security_term: str
    original_security_term: Optional[str] = None
    term_group: Optional[str] = None
    term: Optional[str] = None  # "26W", or a family such as "TIPS10Y" (D-0105); None = no family
    reopening: Optional[bool] = None
    offering_amt: Optional[float] = None
    total_tendered: Optional[float] = None
    total_accepted: Optional[float] = None
    soma_tendered: Optional[float] = None
    soma_accepted: Optional[float] = None
    comp_accepted: Optional[float] = None
    b2c_reported: Optional[float] = None
    b2c_recomputed: Optional[float] = None
    b2c_check: str
    identity_check: str
    b2c_z: Optional[float] = None
    b2c_z_window: int
    b2c_z_reason: Optional[str] = None
    b2c_window_mean: Optional[float] = None  # the chart's band (D-0099)
    b2c_window_sd: Optional[float] = None
    primary_dealer_share: Optional[float] = None
    direct_bidder_share: Optional[float] = None
    indirect_bidder_share: Optional[float] = None
    shares_check: str
    bidder_gap: Optional[float] = None
    dealer_z: Optional[float] = None
    dealer_z_window: int
    dealer_z_reason: Optional[str] = None
    demand_signal: Optional[str] = None  # "alert" | "watch" | None (D-0107)
    demand_signal_reason: Optional[str] = None
    allocation_pct: Optional[float] = None
    high_yield: Optional[float] = None
    high_discnt_rate: Optional[float] = None
    high_investment_rate: Optional[float] = None
    null_reasons: dict


class AuctionListResponse(BaseModel):
    data_as_of: Optional[str] = None
    count: int
    auctions: List[AuctionRow]


class AuctionSummaryResponse(BaseModel):
    data_as_of: Optional[str] = None
    window_n: int
    min_observations: int
    terms: List[AuctionRow]


class AuctionBidderClass(BaseModel):
    tendered: Optional[float] = None
    accepted: Optional[float] = None
    share: Optional[float] = None


class AuctionSoma(BaseModel):
    tendered: Optional[float] = None
    accepted: Optional[float] = None
    excluded_from_b2c: bool


class AuctionDetail(AuctionRow):
    bidders: dict[str, AuctionBidderClass]
    soma: AuctionSoma
    comp_tendered: Optional[float] = None
    noncomp_accepted: Optional[float] = None
    fima_noncomp_accepted: Optional[float] = None


class AuctionDetailResponse(BaseModel):
    data_as_of: Optional[str] = None
    auction: AuctionDetail
