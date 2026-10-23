"""Sentinel D-0113: a fixed, offline input for the scorer golden.

Seeds an in-memory SQLite with TIC, gold, M2, CDS-free yields, DGS10/DGS2 and
the FB_ daily bond codes, so the golden also proves the FB_ rows change nothing.
"""
from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.models import Base, Country, Metric, TimeSeries

MONTHS = [datetime(2026, m, 28) for m in range(3, 10)]
COUNTRIES = [("JPN", "Japan"), ("DEU", "Germany"), ("GBR", "United Kingdom"),
             ("FRA", "France"), ("ITA", "Italy"), ("CHN", "China"), ("USA", "United States")]
TIC = {"JPN": [1150, 1140, 1120, 1100, 1090, 1080, 1060], "DEU": [90, 91, 92, 92, 93, 94, 95],
       "GBR": [700, 705, 690, 680, 690, 695, 700], "FRA": [300, 290, 280, 270, 260, 250, 240],
       "ITA": [40, 41, 41, 42, 42, 43, 43], "CHN": [780, 770, 760, 750, 740, 730, 720]}
GOLD = {"JPN": 846, "DEU": 3351, "GBR": 310, "FRA": 2437, "ITA": 2452, "CHN": 2280}
YIELDS = {"JPN": "IRLTLT01JPM156N", "DEU": "IRLTLT01DEM156N", "GBR": "IRLTLT01GBM156N",
          "FRA": "IRLTLT01FRM156N", "ITA": "IRLTLT01ITM156N"}


def build():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    ids = {}
    for iso, name in COUNTRIES:
        c = Country(iso_code=iso, name=name)
        db.add(c)
        db.flush()
        ids[iso] = c.id

    def metric(code, cat="x"):
        m = Metric(code=code, name=code, category=cat, unit="u", source="fixture")
        db.add(m)
        db.flush()
        return m.id

    tic = metric("TIC_UST_HOLDINGS", "holdings")
    gold = metric("GOLD_RESERVES", "gold")
    for iso, vals in TIC.items():
        for d, v in zip(MONTHS, vals):
            db.add(TimeSeries(metric_id=tic, country_id=ids[iso], date=d, value=v))
        for i, d in enumerate(MONTHS):
            db.add(TimeSeries(metric_id=gold, country_id=ids[iso], date=d, value=GOLD[iso] + i))
    for code, base in [("DGS10", 4.2), ("DGS2", 3.9)] + [(c, 3.0) for c in YIELDS.values()]:
        mid = metric(code, "treasury")
        for i, d in enumerate(MONTHS):
            db.add(TimeSeries(metric_id=mid, country_id=None, date=d, value=base + i / 100))
    for cc in ("DE", "GB", "JP", "FR"):
        for t in (2, 5, 7, 10, 30):
            mid = metric(f"FB_{cc}_{t:02d}Y", "foreign_bonds")
            for i, d in enumerate(MONTHS):
                db.add(TimeSeries(metric_id=mid, country_id=None, date=d, value=9 + i))
    db.commit()
    return db
