from sqlalchemy import (
    Boolean, Column, Date, DateTime, Float, ForeignKey, Index, Integer, Numeric,
    String, Text, UniqueConstraint,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime

Base = declarative_base()


class Metric(Base):
    """Metadata for each tracked metric (e.g., Treasury 10Y, WTI Crude, Gold Holdings)"""
    __tablename__ = "metrics"
    
    id = Column(Integer, primary_key=True)
    code = Column(String(50), unique=True, nullable=False, index=True)  # DGS10, DCOILWTICO, etc.
    name = Column(String(255), nullable=False)  # "US Treasury 10-Year Yield"
    category = Column(String(50), nullable=False)  # "treasury", "oil", "gold", "holdings"
    unit = Column(String(50), nullable=False)  # "percent", "usd_per_barrel", "fine_troy_ounces", etc.
    source = Column(String(100), nullable=False)  # "FRED", "TIC", "IMF", "World Gold Council"
    description = Column(String(500))
    created_at = Column(DateTime, default=datetime.utcnow)
    
    timeseries = relationship("TimeSeries", back_populates="metric", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Metric {self.code}: {self.name}>"


class Country(Base):
    """Country/region codes for Treasury holdings and gold reserves"""
    __tablename__ = "countries"
    
    id = Column(Integer, primary_key=True)
    iso_code = Column(String(3), unique=True, nullable=False, index=True)  # USA, CHN, JPN, etc.
    name = Column(String(255), nullable=False, index=True)
    region = Column(String(100))  # "Asia", "Europe", etc.
    created_at = Column(DateTime, default=datetime.utcnow)
    
    timeseries = relationship("TimeSeries", back_populates="country", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Country {self.iso_code}: {self.name}>"


class TimeSeries(Base):
    """Core timeseries data: metric values by date, optionally by country"""
    __tablename__ = "timeseries"
    
    id = Column(Integer, primary_key=True)
    metric_id = Column(Integer, ForeignKey("metrics.id"), nullable=False, index=True)
    country_id = Column(Integer, ForeignKey("countries.id"), index=True)  # NULL for global metrics like oil
    date = Column(DateTime, nullable=False, index=True)
    value = Column(Numeric(20, 8), nullable=False)  # Precise decimal for financial data
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    metric = relationship("Metric", back_populates="timeseries")
    country = relationship("Country", back_populates="timeseries")
    
    __table_args__ = (
        Index('ix_metric_date', 'metric_id', 'date', unique=False),
        Index('ix_country_date', 'country_id', 'date', unique=False),
        # F-0073: NULLS NOT DISTINCT is load-bearing. Every macro series has
        # country_id IS NULL, and Postgres treats NULLs as DISTINCT in a
        # unique index by default - so without this the constraint exists,
        # reads as correct, and never rejects a duplicate for any of them.
        # 1,190 had accumulated before anyone looked.
        #
        # SQLite ignores the dialect kwarg and shares the same NULL semantics,
        # so the in-memory test databases do NOT enforce this. It is covered
        # by asserting the emitted DDL and against production; it cannot be
        # covered by inserting into SQLite.
        Index('ix_metric_country_date', 'metric_id', 'country_id', 'date',
              unique=True, postgresql_nulls_not_distinct=True),
    )
    
    def __repr__(self):
        return f"<TimeSeries {self.metric_id} @ {self.date}: {self.value}>"


class CompositeSnapshot(Base):
    """A computed composite stress result, stored so the endpoint is a read.

    ORDER-03 D3. The payload is the scorer's own output, kept whole as JSON
    text rather than shredded into columns: the shape belongs to the scorer,
    and a schema that mirrors it would have to change every time the scorer
    gains a dimension - against a project with no migrations (F-0022).

    Text, not JSONB, so the same code runs on the SQLite databases the test
    suite builds.
    """
    __tablename__ = "composite_snapshots"

    id = Column(Integer, primary_key=True)
    computed_at = Column(DateTime, nullable=False, index=True)
    country_count = Column(Integer, default=0)
    payload = Column(Text, nullable=False)

    def __repr__(self):
        return f"<CompositeSnapshot {self.country_count} countries @ {self.computed_at}>"


class TreasuryAuction(Base):
    """One Treasury marketable auction result, with its demand metrics (D-0098).

    Natural key `(cusip, auction_date)`: a reopening sells an existing CUSIP
    again, so CUSIP alone is not unique. Amounts are whole dollars, as the
    source publishes them. Every nullable column is NULL only with a reason in
    `null_reasons`; a missing amount is never stored as 0.

    `raw` and `null_reasons` are JSON as Text, not JSONB, for the same reason as
    CompositeSnapshot: the suite runs on SQLite.
    """
    __tablename__ = "treasury_auctions"

    id = Column(Integer, primary_key=True)
    cusip = Column(String(9), nullable=False, index=True)
    auction_date = Column(Date, nullable=False, index=True)
    issue_date = Column(Date)
    maturity_date = Column(Date)
    security_type = Column(String(10), nullable=False)
    security_term = Column(String(40), nullable=False)
    original_security_term = Column(String(40))
    # D-0103. NULL for TIPS, FRNs and CMBs, which are stored but never charted.
    term_group = Column(String(40), index=True)
    reopening = Column(Boolean)
    inflation_indexed = Column(Boolean)
    floating_rate = Column(Boolean)
    cash_management_bill = Column(Boolean)

    offering_amt = Column(Numeric(20, 2))
    total_tendered = Column(Numeric(20, 2))
    total_accepted = Column(Numeric(20, 2))
    soma_tendered = Column(Numeric(20, 2))
    soma_accepted = Column(Numeric(20, 2))
    comp_tendered = Column(Numeric(20, 2))
    comp_accepted = Column(Numeric(20, 2))
    noncomp_accepted = Column(Numeric(20, 2))
    fima_noncomp_tendered = Column(Numeric(20, 2))
    fima_noncomp_accepted = Column(Numeric(20, 2))
    primary_dealer_tendered = Column(Numeric(20, 2))
    primary_dealer_accepted = Column(Numeric(20, 2))
    direct_bidder_tendered = Column(Numeric(20, 2))
    direct_bidder_accepted = Column(Numeric(20, 2))
    indirect_bidder_tendered = Column(Numeric(20, 2))
    indirect_bidder_accepted = Column(Numeric(20, 2))

    high_yield = Column(Numeric(12, 6))
    high_discnt_rate = Column(Numeric(12, 6))
    high_investment_rate = Column(Numeric(12, 6))
    allocation_pct = Column(Numeric(12, 6))  # % allotted at high

    b2c_reported = Column(Numeric(12, 6))
    b2c_recomputed = Column(Numeric(18, 10))
    b2c_check = Column(String(12), nullable=False)  # ok | mismatch | unverifiable
    # A-0025: total - SOMA == comp + noncomp + FIMA tendered. ok | fail | unverifiable
    identity_check = Column(String(12), nullable=False)

    primary_dealer_share = Column(Numeric(18, 12))
    direct_bidder_share = Column(Numeric(18, 12))
    indirect_bidder_share = Column(Numeric(18, 12))
    shares_check = Column(String(12), nullable=False)  # ok | gap | unverifiable (D-0104)
    bidder_gap = Column(Numeric(20, 2))

    null_reasons = Column(Text, nullable=False, default="{}")
    raw = Column(Text, nullable=False)
    source_record_date = Column(Date)
    ingested_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("cusip", "auction_date", name="uq_treasury_auction_cusip_date"),
    )

    def __repr__(self):
        return f"<TreasuryAuction {self.cusip} {self.auction_date} {self.security_term}>"


class UpdateLog(Base):
    """Pipeline execution log for monitoring fetch health"""
    __tablename__ = "update_logs"
    
    id = Column(Integer, primary_key=True)
    pipeline_name = Column(String(100), nullable=False, index=True)  # "FRED", "TIC", "Gold", etc.
    status = Column(String(20), nullable=False)  # "success", "partial", "failed"
    records_inserted = Column(Integer, default=0)
    records_updated = Column(Integer, default=0)
    error_message = Column(String(500))
    started_at = Column(DateTime, nullable=False)
    completed_at = Column(DateTime, nullable=False)
    
    def __repr__(self):
        return f"<UpdateLog {self.pipeline_name}: {self.status} @ {self.completed_at}>"
