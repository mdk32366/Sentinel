"""Sentinel D-0114: a fixed, offline input for the dimension-4 scorer tests.

In-memory SQLite. TIC, gold, US 10Y, the monthly IRLTLT 10Y for the four FB
countries plus Italy (an EZ member with no FB leg), and daily FB_xx_10Y rows:

  FR, DE  five years of business days, OAT-Bund cycling 40..80bp, 85bp today
  GB      fresh, 5.38% on the last day (128bp over the 4.10% US 10Y)
  JP      last row 2026-10-10: stale at the frozen clock (limit 7 days)

``build(...)`` lets a test drop or age one leg.
"""
from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.models import Base, Country, Metric, TimeSeries

NOW = datetime(2026, 10, 22, 12, 0, 0)
MONTHS = [datetime(2026, m, 28) for m in range(3, 10)]
COUNTRIES = [("JPN", "Japan"), ("DEU", "Germany"), ("GBR", "United Kingdom"),
             ("FRA", "France"), ("ITA", "Italy"), ("CHN", "China"), ("USA", "United States")]
TIC = {"JPN": [1150, 1140, 1120, 1100, 1090, 1080, 1060], "DEU": [90, 91, 92, 92, 93, 94, 95],
       "GBR": [700, 705, 690, 680, 690, 695, 700], "FRA": [300, 290, 280, 270, 260, 250, 240],
       "ITA": [46, 45, 45, 44, 43, 42, 41], "CHN": [780, 770, 760, 750, 740, 730, 720]}
GOLD = {"JPN": 846, "DEU": 3351, "GBR": 310, "FRA": 2437, "ITA": 2452, "CHN": 2280}
MONTHLY = {"IRLTLT01JPM156N": 1.6, "IRLTLT01DEM156N": 2.6, "IRLTLT01GBM156N": 4.6,
           "IRLTLT01FRM156N": 3.2, "IRLTLT01ITM156N": 4.9}
US_10Y = 4.10
LAST_DAY = datetime(2026, 10, 21)


def business_days(start, end):
    d = start
    while d <= end:
        if d.weekday() < 5:
            yield d
        d += timedelta(days=1)


def fr_de_history(end=LAST_DAY):
    """(date, fr, de) for five years plus a month of business days."""
    out = []
    for i, d in enumerate(business_days(end - timedelta(days=5 * 365 + 30), end)):
        de = 2.50 + (i % 50) / 1000
        spread = 0.85 if d == end else 0.40 + (i % 41) / 100
        out.append((d, round(de + spread, 4), round(de, 4)))
    return out


def build(drop=(), fr_last=None, de_last=None, gb_last=None, jp_last=datetime(2026, 10, 10)):
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
    us = metric("DGS10", "treasury")
    for d in business_days(datetime(2026, 6, 1), LAST_DAY):
        db.add(TimeSeries(metric_id=us, country_id=None, date=d, value=US_10Y))
    for code, base in MONTHLY.items():
        mid = metric(code, "treasury")
        for i, d in enumerate(MONTHS):
            db.add(TimeSeries(metric_id=mid, country_id=None, date=d, value=base + i / 100))

    def daily(code, rows, last):
        if code in drop:
            return
        mid = metric(code, "foreign_bond")
        for d, v in rows:
            if last is None or d <= last:
                db.add(TimeSeries(metric_id=mid, country_id=None, date=d, value=v))

    hist = fr_de_history()
    daily("FB_FR_10Y", [(d, fr) for d, fr, _ in hist], fr_last)
    daily("FB_DE_10Y", [(d, de) for d, _, de in hist], de_last)
    recent = list(business_days(datetime(2026, 6, 1), LAST_DAY))
    daily("FB_GB_10Y", [(d, 5.38 if d == LAST_DAY else 5.20 + i / 1000)
                        for i, d in enumerate(recent)], gb_last)
    daily("FB_JP_10Y", [(d, 2.90) for d in recent], jp_last)
    db.commit()
    return db
