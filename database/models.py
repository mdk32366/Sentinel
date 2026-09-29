from sqlalchemy import Text, Column, Integer, String, Float, DateTime, ForeignKey, Index, Numeric
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
