"""
Per-country data age
--------------------
`A-0017`. `pipelines/freshness_watchdog.py` answers "is this SOURCE current".
Nothing answered "is this source current **for this country**", and the two are
different questions with different answers.

`F-0092` is why it matters: `money_supply` is `ok` at the source, correctly,
because 2025 data exists for the countries that still report - and Canada's
newest broad money figure is **2008**. Dimension 3 was scoring it. Only
dimension 3 has a per-country cutoff now; this module measures the same exposure
everywhere else rather than guessing at four more cutoffs.

Read-only. It computes no verdict and changes no score: the honest first step is
a number, and `A-0017` stays open until that number says which dimensions need a
rule of their own.

Two storage shapes, both handled, because the difference is invisible from the
outside and each needs a different query:

  per-country metric codes   CDS (`CHINA_CDS_5Y`), sovereign yields
                             (`IRLTLT01JPM156N`), reserves ex-gold
                             (`TRESEGCNM052N`) - one metric row per country,
                             so the age is MAX(date) per metric.
  one metric, country column  `GOLD_RESERVES`, `BROAD_MONEY_GROWTH`, `TIC%` -
                             so the age is MAX(date) GROUP BY country_id.
"""

import logging
from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from database.models import Country, Metric, TimeSeries
from pipelines.freshness_watchdog import CHECKS

logger = logging.getLogger(__name__)

# Sources stored as one metric with a country_id column. Everything else in
# CHECKS is either per-country metric codes or a single global series.
COUNTRY_COLUMN_PATTERNS = {"GOLD_RESERVES", "BROAD_MONEY_GROWTH", "TIC%"}

# Age buckets, in days. Chosen to straddle the publication cadences actually in
# play - monthly, quarterly, annual - so a bucket boundary means something.
BUCKETS = [90, 180, 365, 730, 1825]

# A country is called a laggard when its own newest row is more than this
# multiple of the source's tolerance. Expressed as a multiple of the watchdog's
# own number rather than as a fresh constant, so it cannot drift away from it.
LAGGARD_TOLERANCE_MULTIPLE = 2.0


def _bucket_label(age_days: int) -> str:
    lo = 0
    for hi in BUCKETS:
        if age_days <= hi:
            return f"{lo}-{hi}d"
        lo = hi + 1
    return f">{BUCKETS[-1]}d"


def _clause(patterns):
    clause = None
    for p in patterns:
        c = Metric.code.like(p, escape="\\")
        clause = c if clause is None else (clause | c)
    return clause


def _ages_per_country_metric(db: Session, patterns, now: datetime) -> dict:
    """{metric_code: age_days} - one metric per country."""
    rows = (
        db.query(Metric.code, func.max(TimeSeries.date))
        .join(TimeSeries, TimeSeries.metric_id == Metric.id)
        .filter(_clause(patterns))
        .group_by(Metric.code)
        .all()
    )
    return {code: (now - dt).days for code, dt in rows if dt is not None}


def _ages_by_country_column(db: Session, patterns, now: datetime) -> dict:
    """{iso_code: age_days} - one metric, many countries."""
    rows = (
        db.query(Country.iso_code, func.max(TimeSeries.date))
        .join(TimeSeries, TimeSeries.country_id == Country.id)
        .join(Metric, TimeSeries.metric_id == Metric.id)
        .filter(_clause(patterns))
        .group_by(Country.iso_code)
        .all()
    )
    return {iso: (now - dt).days for iso, dt in rows if dt is not None}


def _percentile(sorted_vals, q: float):
    if not sorted_vals:
        return None
    i = min(len(sorted_vals) - 1, max(0, round(q * (len(sorted_vals) - 1))))
    return sorted_vals[i]


def per_country_age_report(db: Session, now: datetime | None = None) -> dict:
    """The distribution of per-country data age, per monitored source."""
    now = now or datetime.utcnow()
    out = []

    for check in CHECKS:
        patterns = check.get("patterns") or []
        by_country_column = bool(set(patterns) & COUNTRY_COLUMN_PATTERNS)

        if by_country_column:
            ages = _ages_by_country_column(db, patterns, now)
            unit = "country"
        else:
            ages = _ages_per_country_metric(db, patterns, now)
            unit = "series"

        if not ages:
            out.append({
                "key": check["key"], "label": check["label"], "unit": unit,
                "entities": 0, "ages": None, "buckets": {}, "laggards": [],
                "source_tolerance_days": check.get("max_age_days"),
            })
            continue

        vals = sorted(ages.values())
        tol = check.get("max_age_days") or 0
        threshold = tol * LAGGARD_TOLERANCE_MULTIPLE

        buckets = {}
        for v in vals:
            label = _bucket_label(v)
            buckets[label] = buckets.get(label, 0) + 1

        laggards = sorted(
            ({"name": k, "age_days": v} for k, v in ages.items() if v > threshold),
            key=lambda d: -d["age_days"],
        )

        out.append({
            "key": check["key"],
            "label": check["label"],
            "unit": unit,
            "entities": len(vals),
            "ages": {
                "min": vals[0],
                "p50": _percentile(vals, 0.5),
                "p90": _percentile(vals, 0.9),
                "max": vals[-1],
            },
            "buckets": buckets,
            "source_tolerance_days": tol,
            "laggard_threshold_days": round(threshold),
            "laggard_count": len(laggards),
            "laggards": laggards[:15],
        })

    return {
        "as_of": now.isoformat(),
        "laggard_threshold_multiple": LAGGARD_TOLERANCE_MULTIPLE,
        "sources": out,
    }
