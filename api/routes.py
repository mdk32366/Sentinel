import json
import httpx
import time
from pipelines.fred_fetcher import run_fred_fetch
from fastapi import APIRouter, Depends, Query, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta
from typing import List, Optional
from database.connection import get_db, get_session
from config import settings
from database.models import Metric, TimeSeries, UpdateLog, Country
from api.schemas import (
    HoldingsResponse,
    GoldReservesResponse,
    CdsAllItem,
    CdsCountryResponse,
    CrossAssetStressResponse,
    CompositeStressResponse,
    MetricResponse,
    CountryResponse,
    TimeSeriesDataPoint,
    TimeSeriesQuery,
    UpdateLogResponse,
    HealthResponse,
)
from pipelines.scheduler import scheduler
from pipelines.cds_fetcher import (
    run_cds_fetch,
    get_cds_coverage,
    admit_cds_quote,
    cds_country_for_code,
    latest_cds_observation,
    pair_cds_tenors,
)
# F-0078: ISO -> the CDS metric namespace token ("TUR" -> "TURKEY").
from pipelines.composite_stress import CDS_NAME_BY_ISO, ISO_BY_CDS_NAME
from pipelines.stress_score_v2 import get_latest_metric_value
# ORDER-03 B2 / F-0020: previously imported inside the handler bodies, which
# hid these dependencies from any static read of the imports.
from pipelines.gold_fetcher import compute_cross_asset_stress
from pipelines.composite_stress import (
    compute_composite_stress,
    latest_composite_snapshot,
    persist_composite_snapshot,
)
from pipelines.freshness_watchdog import get_freshness_report
from pipelines.fetch_failure import parse_failure_prefix
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["treasury-monitor"])


@router.get("/health")
def health_check():
    """Liveness only.

    ORDER-03 A0 / F-0019: this path is listed in main.py OPEN_PATHS and is
    served WITHOUT authentication for the Docker and Fly probes. It therefore
    carries no pipeline detail, no scheduler state and no database state -
    those moved to GET /api/pipeline-status, behind auth. Do not add data here.

    It also takes no database session: the Fly probe hits this every 15s and a
    liveness check should not consume a connection from a pool of 10.
    """
    return {"status": "healthy"}


@router.get("/freshness")
def freshness(db: Session = Depends(get_db)):
    """Per-source data freshness.

    ORDER-01 B6, as amended by ORDER-03 A0. B6 originally asked for a
    `data_freshness` block on `/api/health` as well. That instruction is wrong
    and is not followed: `/api/health` is listed in `main.py` OPEN_PATHS and is
    served unauthenticated to the Fly and Docker probes, so per-source staleness
    and pipeline names do not belong on it (`D-0035`, `F-0019`). This endpoint
    sits behind the same Basic Auth as every other route.

    Thresholds are per-source, not uniform (`D-0024`): a rule that alerts on
    healthy Treasury data every weekend teaches you to scroll past the one that
    matters.
    """
    return get_freshness_report(db)


@router.get("/pipeline-status", response_model=HealthResponse)
def pipeline_status(db: Session = Depends(get_db)):
    """Pipeline freshness detail. Authenticated - this is what /api/health used
    to return to anyone who asked."""
    fred_log = db.query(UpdateLog).filter_by(pipeline_name="FRED").order_by(UpdateLog.completed_at.desc()).first()
    treasury_log = db.query(UpdateLog).filter_by(pipeline_name="TIC_Holdings").order_by(UpdateLog.completed_at.desc()).first()
    # D-0094: last_gold_update remains Gold_Reserves (reserves, not price).
    gold_log = db.query(UpdateLog).filter_by(pipeline_name="Gold_Reserves").order_by(UpdateLog.completed_at.desc()).first()
    gold_price_log = (
        db.query(UpdateLog)
        .filter_by(pipeline_name="Gold_Spot_Price")
        .order_by(UpdateLog.completed_at.desc())
        .first()
    )
    gold_price_success = (
        db.query(UpdateLog)
        .filter(
            UpdateLog.pipeline_name == "Gold_Spot_Price",
            UpdateLog.status.in_(["success", "partial"]),
        )
        .order_by(UpdateLog.completed_at.desc())
        .first()
    )
    gold_price_failure = None
    if gold_price_log is not None and gold_price_log.status == "failed":
        gold_price_failure = parse_failure_prefix(gold_price_log.error_message)
        # Legacy unprefixed failed rows still surface as a failure; kind stays
        # None rather than inventing "blocked".

    return HealthResponse(
        status="healthy",
        database="connected",
        scheduler="running" if scheduler.running else "stopped",
        last_fred_update=fred_log.completed_at if fred_log else None,
        last_treasury_update=treasury_log.completed_at if treasury_log else None,
        last_gold_update=gold_log.completed_at if gold_log else None,
        last_gold_price_run=gold_price_log.completed_at if gold_price_log else None,
        last_gold_price_status=gold_price_log.status if gold_price_log else None,
        last_gold_price_failure=gold_price_failure,
        last_gold_price_success=(
            gold_price_success.completed_at if gold_price_success else None
        ),
    )


@router.get("/metrics", response_model=List[MetricResponse])
def list_metrics(
    category: Optional[str] = Query(None, description="Filter by category"),
    db: Session = Depends(get_db)
):
    """List all available metrics"""
    query = db.query(Metric)
    if category:
        query = query.filter_by(category=category)
    return query.all()


@router.get("/countries", response_model=List[CountryResponse])
def list_countries(db: Session = Depends(get_db)):
    """List all countries with data"""
    return db.query(Country).order_by(Country.name).all()


@router.get("/timeseries", response_model=List[TimeSeriesDataPoint])
def get_timeseries(
    metric_codes: str = Query(..., description="Comma-separated metric codes"),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    country_iso: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """Query timeseries data for one or more metrics"""
    codes = [code.strip() for code in metric_codes.split(",")]

    metrics = db.query(Metric).filter(Metric.code.in_(codes)).all()
    if not metrics:
        raise HTTPException(status_code=404, detail=f"No metrics found for codes: {codes}")

    metric_ids = [m.id for m in metrics]

    if not end_date:
        end_date = datetime.utcnow()
    if not start_date:
        start_date = end_date - timedelta(days=730)

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

    return [
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


@router.get("/metric/{metric_code}", response_model=List[TimeSeriesDataPoint])
def get_metric_data(
    metric_code: str,
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    country_iso: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """Get timeseries data for a single metric"""
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
    """Get pipeline execution logs"""
    query = db.query(UpdateLog)
    if pipeline_name:
        query = query.filter_by(pipeline_name=pipeline_name)
    return query.order_by(UpdateLog.completed_at.desc()).limit(limit).all()


@router.get("/stats")
def get_stats(db: Session = Depends(get_db)):
    """Get database statistics"""
    total_metrics = db.query(Metric).count()
    total_countries = db.query(Country).count()
    total_timeseries = db.query(TimeSeries).count()

    date_range = db.query(
        func.min(TimeSeries.date).label("earliest"),
        func.max(TimeSeries.date).label("latest")
    ).first()

    return {
        "metrics": total_metrics,
        "countries": total_countries,
        "timeseries_records": total_timeseries,
        "data_earliest": date_range.earliest,
        "data_latest": date_range.latest,
    }


@router.post("/fetch/fred")
def trigger_fred_fetch(db: Session = Depends(get_db)):
    """Manually trigger a FRED data fetch"""
    try:
        result = run_fred_fetch(db)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/holdings", response_model=HoldingsResponse)
def get_all_holdings(
    country_iso: Optional[str] = Query(None),
    date: Optional[datetime] = Query(None),
    db: Session = Depends(get_db)
):
    """
    Get Treasury holdings data by country.
    If date not provided, returns latest available date.
    """
    metric = db.query(Metric).filter_by(code="TIC_UST_HOLDINGS").first()
    if not metric:
        raise HTTPException(status_code=404, detail="Holdings data not yet loaded")
    
    query = db.query(
        Country.iso_code,
        Country.name,
        TimeSeries.date,
        TimeSeries.value
    ).join(TimeSeries).filter(
        TimeSeries.metric_id == metric.id,
        TimeSeries.country_id != None,
    )
    
    if country_iso:
        query = query.filter(Country.iso_code == country_iso)
    
    if not date:
        # Get latest date
        latest_date = db.query(func.max(TimeSeries.date)).filter(
            TimeSeries.metric_id == metric.id
        ).scalar()
        if latest_date:
            query = query.filter(TimeSeries.date == latest_date)
    else:
        query = query.filter(TimeSeries.date == date)
    
    results = query.order_by(TimeSeries.value.desc()).all()

    if not results:
        raise HTTPException(status_code=404, detail="No holdings data found")

    as_of = results[0][2]
    listed_total = sum(float(r[3]) for r in results)

    # D-0085. The published total for ALL foreign holdings, not the sum of the
    # rows below. Table 5 names twenty countries and folds the rest into "All
    # Other"; Table 3 carries 76, which is 94% of the published total but not
    # 100%. Summing the rows and calling it "Total Foreign Holdings" understated
    # the real figure by $537.8bn.
    grand_total = None
    gt_metric = db.query(Metric).filter_by(code="TIC_GRAND_TOTAL").first()
    if gt_metric is not None:
        gt_row = db.query(TimeSeries).filter(
            TimeSeries.metric_id == gt_metric.id,
            TimeSeries.country_id.is_(None),
            TimeSeries.date == as_of,
        ).first()
        grand_total = float(gt_row.value) if gt_row else None

    # Percentages against the published total where we have it. "Japan holds
    # 11.9% of all foreign-held Treasuries" is a fact about the world; 12.7% of
    # the rows we happen to list is a fact about our query.
    denominator = grand_total or listed_total

    # D-0085. Sixteen reporters suppress their total and publish only a
    # long-term figure. Omitting them leaves Poland, Egypt, Hungary, Romania,
    # Serbia, Ukraine, Lebanon and Greece off the list entirely, which reads as
    # "not a holder" - the F-0097 error in a new place. Included and labelled,
    # never silently mixed with a total.
    lt_only = []
    lt_metric = db.query(Metric).filter_by(code="TIC_UST_LT_HOLDINGS").first()
    if lt_metric is not None and not country_iso:
        have = {r[0] for r in results}
        lt_rows = db.query(Country.iso_code, Country.name, TimeSeries.value).join(
            TimeSeries, TimeSeries.country_id == Country.id
        ).filter(
            TimeSeries.metric_id == lt_metric.id,
            TimeSeries.date == as_of,
        ).all()
        lt_only = [r for r in lt_rows if r[0] not in have]

    # D-0087. Movement and its type, per country. Read in three queries rather
    # than one per country: 60 rows x 3 metrics would be 180 round trips.
    from pipelines.tic_state import classify_movement, describe_movement

    def _by_country(code, dates):
        m = db.query(Metric).filter_by(code=code).first()
        if m is None:
            return {}
        rows = db.query(TimeSeries.country_id, TimeSeries.date, TimeSeries.value).filter(
            TimeSeries.metric_id == m.id,
            TimeSeries.date.in_(dates),
        ).all()
        out = {}
        for cid, dt, val in rows:
            out.setdefault(cid, {})[dt] = float(val)
        return out

    months = [
        d for (d,) in db.query(TimeSeries.date).filter(
            TimeSeries.metric_id == metric.id
        ).distinct().order_by(TimeSeries.date.desc()).limit(4).all()
    ]
    prev_month = months[1] if len(months) > 1 else None

    holdings_hist = _by_country("TIC_UST_HOLDINGS", months)
    nets = _by_country("TIC_UST_NET_SALES", months)
    vals = _by_country("TIC_UST_LT_VALUATION", months)
    ids = {r[0]: r for r in db.query(Country.id, Country.iso_code).all()}
    id_by_iso = {iso: cid for cid, iso in db.query(Country.id, Country.iso_code).all()}

    def movement_for(iso, current):
        cid = id_by_iso.get(iso)
        if cid is None:
            return {}
        prior = holdings_hist.get(cid, {}).get(prev_month) if prev_month else None
        net1 = nets.get(cid, {}).get(as_of)
        val1 = vals.get(cid, {}).get(as_of)
        net3 = sum(v for d, v in (nets.get(cid) or {}).items() if d in months[:3]) \
            if nets.get(cid) else None
        kind = classify_movement(net1, val1)
        return {
            "change_1m_bn": round(current - prior, 2) if prior is not None else None,
            "change_1m_pct": (
                round((current - prior) / prior * 100, 2)
                if prior not in (None, 0) else None
            ),
            "net_1m_bn": round(net1, 2) if net1 is not None else None,
            "valuation_1m_bn": round(val1, 2) if val1 is not None else None,
            "net_3m_bn": round(net3, 2) if net3 is not None else None,
            "movement": kind,
            "movement_note": describe_movement(kind, net1, val1),
        }

    holdings = [
        {
            "country_code": r[0],
            "country_name": r[1],
            "holdings_billions_usd": round(float(r[3]), 2),
            "percent_of_total": round((float(r[3]) / denominator) * 100, 1),
            "long_term_only": False,
            **movement_for(r[0], float(r[3])),
        }
        for r in results
    ] + [
        {
            "country_code": r[0],
            "country_name": r[1],
            "holdings_billions_usd": round(float(r[2]), 2),
            "percent_of_total": round((float(r[2]) / denominator) * 100, 1),
            "long_term_only": True,
        }
        for r in lt_only
    ]
    holdings.sort(key=lambda h: -h["holdings_billions_usd"])

    return {
        "date": as_of.isoformat(),
        "total_billions_usd": round(listed_total, 2),
        "grand_total_billions_usd": round(grand_total, 2) if grand_total else None,
        "coverage_pct": (
            round(listed_total / grand_total * 100, 1) if grand_total else None
        ),
        "country_count": len(results),
        "long_term_only_count": len(lt_only),
        "holdings": holdings,
    }


@router.get("/holdings/cross-asset-stress", response_model=CrossAssetStressResponse)
def get_cross_asset_stress(db: Session = Depends(get_db)):
    """
    Cross-asset stress: countries selling both Treasuries AND gold,
    with optional divergence multiplier when gold spot is rising.
    """
    try:
        result = compute_cross_asset_stress(db)
        # Wrap into expected format
        cross = [r for r in result if r.get("cross_asset_stress") or r.get("divergence_signal")]
        treasury_only = [r for r in result if not r.get("cross_asset_stress") and not r.get("divergence_signal") and r.get("selling_treasuries")]
        gold_only = [r for r in result if not r.get("selling_treasuries") and r.get("selling_gold")]
        spot = result[0] if result else {}
        return {
            "cross_asset_stress": cross,
            "treasury_only_stress": treasury_only,
            "gold_only_stress": gold_only,
            "summary": {
                "cross_asset_stressed": len(cross),
                "treasury_only": len(treasury_only),
                "gold_only": len(gold_only),
                "total_stressed": len(result),
            },
            "spot_gold_rising": spot.get("spot_gold_rising"),
            "spot_gold_price": spot.get("spot_gold_price"),
            "spot_gold_3m_pct": spot.get("spot_gold_3m_pct"),
            "as_of": spot.get("tic_as_of"),
        }
    except Exception as e:
        logger.error(f"Cross-asset stress calculation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/holdings/{country_iso}")
def get_country_holdings(
    country_iso: str,
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    db: Session = Depends(get_db)
):
    """Get historical Treasury holdings for a specific country."""
    metric = db.query(Metric).filter_by(code="TIC_UST_HOLDINGS").first()
    if not metric:
        raise HTTPException(status_code=404, detail="Holdings data not yet loaded")
    
    country = db.query(Country).filter_by(iso_code=country_iso).first()
    if not country:
        raise HTTPException(status_code=404, detail=f"Country {country_iso} not found")
    
    query = db.query(TimeSeries).filter(
        TimeSeries.metric_id == metric.id,
        TimeSeries.country_id == country.id,
    )
    
    if not end_date:
        end_date = datetime.utcnow()
    if not start_date:
        start_date = end_date - timedelta(days=730)
    
    query = query.filter(
        TimeSeries.date >= start_date,
        TimeSeries.date <= end_date,
    )
    
    results = query.order_by(TimeSeries.date.asc()).all()
    
    return {
        "country_code": country_iso,
        "country_name": country.name,
        "data_points": len(results),
        "holdings": [
            {
                "date": r.date.isoformat(),
                "holdings_billions_usd": round(float(r.value), 2),
            }
            for r in results
        ]
    }


@router.get("/stress-score")
def get_stress_score(db: Session = Depends(get_db)):
    """
    Get current macroeconomic stress score.
    Scale: 0-100, where 0 = low stress, 100 = severe stress.
    Based on: yield curve spread, holdings concentration, commodity volatility.
    """
    from pipelines.stress_score_v2 import calculate_stress_score_v2 as calculate_stress_score
    
    try:
        result = calculate_stress_score(db)
        return result
    except Exception as e:
        logger.error(f"Stress score calculation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/fetch/treasury-holdings")
def trigger_treasury_fetch(db: Session = Depends(get_db)):
    """Manually trigger Treasury holdings fetch"""
    from pipelines.treasury_holdings import run_treasury_holdings_fetch
    
    try:
        result = run_treasury_holdings_fetch(db)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/diagnostics/data-age")
def get_data_age(db: Session = Depends(get_db)):
    """Per-country data age, per monitored source (A-0017).

    The watchdog answers "is this source current". This answers "is it current
    FOR THIS COUNTRY", which is a different question with a different answer:
    `money_supply` is correctly `ok` at the source while Canada's newest broad
    money figure is 2008 (`F-0092`).

    Read-only, and it computes no verdict. `A-0017` asked for the distribution
    before inventing four more cutoffs, and this is that measurement.
    """
    from pipelines.data_age_report import per_country_age_report

    try:
        return per_country_age_report(db)
    except Exception as e:
        logger.error(f"Data age report failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/fetch/tic-table3")
def trigger_tic_table3_fetch(db: Session = Depends(get_db)):
    """Per-country Treasury holdings for all 76 reporters (D-0081).

    SLT Table 5 names only the twenty largest. This refuses to write unless it
    first reproduces Table 5 for those twenty.
    """
    from pipelines.tic_table3 import run_tic_table3_fetch

    try:
        return run_tic_table3_fetch(db)
    except Exception as e:
        logger.error(f"TIC Table 3 fetch failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/fetch/gold-reserves-imf")
def trigger_imf_gold_fetch(db: Session = Depends(get_db)):
    """Fetch monthly gold holdings from IMF IRFCL (D-0076).

    The upstream of the World Gold Council CSV that was being downloaded by
    hand.
    """
    from pipelines.imf_gold_reserves import run_imf_gold_fetch

    try:
        return run_imf_gold_fetch(db)
    except Exception as e:
        logger.error(f"IMF gold fetch failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/fetch/money-supply")
def trigger_money_supply_fetch(db: Session = Depends(get_db)):
    """Fetch broad money growth from the World Bank (F-0091).

    There was no route and no scheduled job for this, so the only way to move
    composite dimension 3 was to run a `curl` by hand into `data/` and call the
    pipeline from a shell.
    """
    from pipelines.money_supply_fetcher import run_money_supply_fetch

    try:
        return run_money_supply_fetch(db)
    except Exception as e:
        logger.error(f"Money supply fetch failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/snapshot/composite")
def trigger_composite_snapshot(db: Session = Depends(get_db)):
    """Recompute the composite and store it, as the nightly job does.

    F-0090. The gap this closes: `POST /fetch/treasury-holdings` above invites
    a manual data refresh, and `GET /stress/composite` serves a *stored*
    snapshot (`D-0042`). So a manual fetch moved the data and left the score
    behind, with nothing able to catch it up before 04:45 UTC.

    Not a cosmetic lag. When the `F-0088` TIC fix landed, HOLDINGS read July
    2026 while COMPOSITE read December 2025 - two surfaces disagreeing about
    which month the system is in, the same class of defect as `F-0087`, and
    `D-0074` had just finished putting freshness on screen where a reader
    would see it.

    `?recompute=true` on the GET is not the answer: it computes without
    storing, so it corrects the tab for the one caller who passed the flag
    and leaves the next reader the old snapshot.
    """
    from pipelines.composite_stress import persist_composite_snapshot

    try:
        return persist_composite_snapshot(db)
    except Exception as e:
        logger.error(f"Composite snapshot refresh failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/gold-reserves", response_model=GoldReservesResponse)
def get_gold_reserves(
    country_iso: Optional[str] = Query(None),
    date: Optional[datetime] = Query(None),
    db: Session = Depends(get_db)
):
    """
    Get central bank gold reserves by country.
    Returns each country's most recent available value (dates vary due to
    reporting lags — e.g. some countries show AWAITED for the latest quarter).
    Units: metric tonnes.
    """
    metric = db.query(Metric).filter_by(code="GOLD_RESERVES").first()
    if not metric:
        raise HTTPException(status_code=404, detail="Gold reserves data not yet loaded")

    if date:
        # Specific date requested — single-date query
        results = db.query(
            Country.iso_code,
            Country.name,
            TimeSeries.date,
            TimeSeries.value
        ).join(TimeSeries).filter(
            TimeSeries.metric_id == metric.id,
            TimeSeries.country_id != None,
            TimeSeries.date == date,
            TimeSeries.value > 0,
        )
        if country_iso:
            results = results.filter(Country.iso_code == country_iso)
        results = results.order_by(TimeSeries.value.desc()).all()
    else:
        # Per-country latest: subquery gets max date per country_id
        latest_per_country = db.query(
            TimeSeries.country_id,
            func.max(TimeSeries.date).label("max_date")
        ).filter(
            TimeSeries.metric_id == metric.id,
            TimeSeries.country_id != None,
            TimeSeries.value > 0,
        ).group_by(TimeSeries.country_id).subquery()

        query = db.query(
            Country.iso_code,
            Country.name,
            TimeSeries.date,
            TimeSeries.value
        ).join(
            TimeSeries, TimeSeries.country_id == Country.id
        ).join(
            latest_per_country,
            (TimeSeries.country_id == latest_per_country.c.country_id) &
            (TimeSeries.date == latest_per_country.c.max_date)
        ).filter(
            TimeSeries.metric_id == metric.id,
        )

        if country_iso:
            query = query.filter(Country.iso_code == country_iso)

        results = query.order_by(TimeSeries.value.desc()).all()

    if not results:
        raise HTTPException(status_code=404, detail="No gold reserves data found")

    total_tonnes = sum(float(r[3]) for r in results)

    # D-0087. Movement and its kind. Gold is held in TONNES - a pure quantity -
    # so unlike Treasuries there is no price component to separate out: a change
    # here is always a decision. The "kind" is therefore direction and
    # PERSISTENCE, which is what dimension 2 scores, rather than the
    # transactions-versus-price split the Treasury surfaces need.
    gold_hist = {}
    if metric is not None:
        recent = db.query(
            TimeSeries.country_id, TimeSeries.date, TimeSeries.value
        ).filter(
            TimeSeries.metric_id == metric.id,
            TimeSeries.country_id.isnot(None),
        ).order_by(TimeSeries.date.asc()).all()
        for cid, dt, val in recent:
            gold_hist.setdefault(cid, []).append((dt, float(val)))

    iso_to_id = {iso: cid for cid, iso in db.query(Country.id, Country.iso_code).all()}

    def gold_movement(iso, current):
        series = gold_hist.get(iso_to_id.get(iso)) or []
        if len(series) < 2:
            return {}
        vals = [v for _, v in series]
        prev = vals[-2]
        three = vals[-4] if len(vals) >= 4 else None

        consec = 0
        for i in range(len(vals) - 1, 0, -1):
            if vals[i] < vals[i - 1]:
                consec += 1
            else:
                break

        change_1m = current - prev
        change_3m = current - three if three is not None else None
        pct_3m = (
            round(change_3m / three * 100, 2)
            if three not in (None, 0) and change_3m is not None else None
        )

        if consec >= 2:
            kind, note = "selling", (
                f"Reserves have fallen for {consec} consecutive readings. "
                f"Persistence is what dimension 2 scores, at 4 points each."
            )
        elif change_1m < -0.05:
            kind, note = "selling", "Reserves fell this period."
        elif change_1m > 0.05:
            kind, note = "accumulating", "Reserves rose this period."
        else:
            kind, note = "stable", "No material change in tonnage."

        return {
            "change_1m_tonnes": round(change_1m, 1),
            "change_3m_tonnes": round(change_3m, 1) if change_3m is not None else None,
            "change_3m_pct": pct_3m,
            "consecutive_declines": consec,
            "movement": kind,
            "movement_note": note,
        }

    return {
        "as_of": "per-country latest (varies by reporting lag)",
        "total_metric_tonnes": round(total_tonnes, 1),
        "country_count": len(results),
        "reserves": [
            {
                "country_code": r[0],
                "country_name": r[1],
                # D-0076 moved gold from a quarterly World Gold Council
                # download to the IMF's MONTHLY IRFCL return. This formatted
                # every reading as a quarter, so Germany's August figure
                # displayed as "2026-Q3" - a month of data labelled as three.
                "as_of_date": r[2].strftime("%Y-%m") if r[2] else None,
                "metric_tonnes": round(float(r[3]), 1),
                "percent_of_total": round((float(r[3]) / total_tonnes) * 100, 1),
                **gold_movement(r[0], float(r[3])),
            }
            for r in results
        ]
    }


@router.get("/gold-reserves/{country_iso}")
def get_country_gold_reserves(
    country_iso: str,
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    db: Session = Depends(get_db)
):
    """Get historical gold reserves for a specific country."""
    metric = db.query(Metric).filter_by(code="GOLD_RESERVES").first()
    if not metric:
        raise HTTPException(status_code=404, detail="Gold reserves data not yet loaded")

    country = db.query(Country).filter_by(iso_code=country_iso).first()
    if not country:
        raise HTTPException(status_code=404, detail=f"Country {country_iso} not found")

    if not end_date:
        end_date = datetime.utcnow()
    if not start_date:
        start_date = end_date - timedelta(days=3650)

    results = db.query(TimeSeries).filter(
        TimeSeries.metric_id == metric.id,
        TimeSeries.country_id == country.id,
        TimeSeries.date >= start_date,
        TimeSeries.date <= end_date,
    ).order_by(TimeSeries.date.asc()).all()

    return {
        "country_code": country_iso,
        "country_name": country.name,
        "data_points": len(results),
        "reserves": [
            {
                "date": r.date.isoformat(),
                "metric_tonnes": round(float(r.value), 1),
            }
            for r in results
        ]
    }


@router.post("/fetch/gold-reserves")
def trigger_gold_fetch(db: Session = Depends(get_db)):
    """Manually trigger gold reserves fetch"""
    from pipelines.gold_reserves import run_gold_reserves_fetch
    try:
        result = run_gold_reserves_fetch(db)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/fetch/gold-price")
def trigger_gold_price_fetch(db: Session = Depends(get_db)):
    """Manually trigger the LBMA gold spot fetch (D-0041).

    The scheduled job runs at 02:30 UTC. This exists for the case where the
    series is known stale and waiting for the next window means serving a
    scorer that is wrong in the meantime - which is exactly what F-0004 was.
    """
    from pipelines.gold_price_fetcher import run_gold_price_fetch
    try:
        return run_gold_price_fetch(db)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/fetch/gold-reserve-changes")
def trigger_gold_changes_fetch(db: Session = Depends(get_db)):
    """Manually trigger IFS gold-holdings changes import"""
    from pipelines.gold_reserve_changes import run_gold_reserve_changes_fetch
    try:
        result = run_gold_reserve_changes_fetch(db)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ORDER-03 A2 / F-0018. The prompt is built here, from data already in the
# database. The endpoint takes a country code and nothing else, so it cannot be
# used as a funded pass-through to the model provider.
SOVEREIGN_YIELD_CODES = {
    "JPN": "IRLTLT01JPM156N", "DEU": "IRLTLT01DEM156N", "ITA": "IRLTLT01ITM156N",
    "FRA": "IRLTLT01FRM156N", "ESP": "IRLTLT01ESM156N", "GBR": "IRLTLT01GBM156N",
    "AUS": "IRLTLT01AUM156N", "CAN": "IRLTLT01CAM156N", "NLD": "IRLTLT01NLM156N",
    "NOR": "IRLTLT01NOM156N", "SWE": "IRLTLT01SEM156N", "CHE": "IRLTLT01CHM156N",
    "BEL": "IRLTLT01BEM156N", "KOR": "IRLTLT01KRM156N",
}

_BRIEF_HITS = {}
_BRIEF_MAX_PER_HOUR = 20


def _brief_rate_limit_ok(client_key: str) -> bool:
    """Per-client cap. In-process only - it resets on restart and is not shared
    between machines. That is a documented limit, not a claim of robustness."""
    now = time.time()
    hits = [t for t in _BRIEF_HITS.get(client_key, []) if now - t < 3600]
    if len(hits) >= _BRIEF_MAX_PER_HOUR:
        _BRIEF_HITS[client_key] = hits
        return False
    hits.append(now)
    _BRIEF_HITS[client_key] = hits
    return True


def _gather_brief_context(db: Session, iso: str) -> dict:
    """Read everything the prompt needs. Caller closes the session before the
    outbound HTTP call."""
    country = db.query(Country).filter(Country.iso_code == iso).first()
    if country is None:
        return None

    ctx = {"iso": iso, "name": country.name}

    tic_metric = db.query(Metric).filter_by(code="TIC_UST_HOLDINGS").first()
    tic_rows = []
    if tic_metric:
        tic_rows = db.query(TimeSeries).filter(
            TimeSeries.metric_id == tic_metric.id,
            TimeSeries.country_id == country.id,
        ).order_by(TimeSeries.date.desc()).limit(2).all()
        ctx["tic_months"] = db.query(TimeSeries).filter(
            TimeSeries.metric_id == tic_metric.id,
            TimeSeries.country_id == country.id,
        ).count()
    ctx["tic_latest"] = float(tic_rows[0].value) if tic_rows else None
    ctx["tic_mom_pct"] = None
    if len(tic_rows) == 2 and float(tic_rows[1].value):
        prev = float(tic_rows[1].value)
        ctx["tic_mom_pct"] = (float(tic_rows[0].value) - prev) / prev * 100

    gold_metric = db.query(Metric).filter_by(code="GOLD_RESERVES").first()
    gold_row = None
    if gold_metric:
        gold_row = db.query(TimeSeries).filter(
            TimeSeries.metric_id == gold_metric.id,
            TimeSeries.country_id == country.id,
        ).order_by(TimeSeries.date.desc()).first()
    ctx["gold_tonnes"] = float(gold_row.value) if gold_row else None

    yield_code = SOVEREIGN_YIELD_CODES.get(iso)
    country_yield = get_latest_metric_value(db, yield_code) if yield_code else None
    us10y = get_latest_metric_value(db, "DGS10")
    ctx["spread_bps"] = None
    if country_yield is not None and us10y is not None:
        ctx["spread_bps"] = (country_yield - us10y) * 100

    ctx["cds_5y"] = get_latest_metric_value(db, f"{iso}_CDS_5Y")
    ctx["cds_10y"] = get_latest_metric_value(db, f"{iso}_CDS_10Y")
    ctx["cds_term_spread"] = None
    if ctx["cds_5y"] is not None and ctx["cds_10y"] is not None:
        ctx["cds_term_spread"] = ctx["cds_10y"] - ctx["cds_5y"]
    return ctx


def _render_brief_prompt(c: dict) -> str:
    def bps(v):
        return "not available" if v is None else f"{'+' if v > 0 else ''}{v:.0f} basis points"

    tic = "no data"
    if c["tic_latest"] is not None:
        tic = f"${c['tic_latest']:.1f}B current"
        if c["tic_mom_pct"] is not None:
            tic += f", MoM {'+' if c['tic_mom_pct'] > 0 else ''}{c['tic_mom_pct']:.2f}%"
        tic += f", {c.get('tic_months', 0)} months of history"

    gold = "no data" if c["gold_tonnes"] is None else f"{c['gold_tonnes']:.0f} metric tonnes"
    cds5 = "not available" if c["cds_5y"] is None else f"{c['cds_5y']} bps"
    cds10 = "not available" if c["cds_10y"] is None else f"{c['cds_10y']} bps"
    term = "not available"
    if c["cds_term_spread"] is not None:
        term = f"{'+' if c['cds_term_spread'] > 0 else ''}{c['cds_term_spread']} bps"

    return f"""You are a financial analyst writing a concise 200-250 word brief for a sophisticated audience. Analyze {c['name']} ({c['iso']}) based on this data:

TREASURY HOLDINGS: {tic}
GOLD RESERVES: {gold}
SOVEREIGN YIELD SPREAD VS US 10Y: {bps(c['spread_bps'])}

SOVEREIGN CDS:
- 5Y CDS: {cds5}
- 10Y CDS: {cds10}
- Term Structure (10Y - 5Y): {term}

Write three short sections:

SITUATION
What is this country doing with its US Treasury holdings and gold reserves? Include CDS levels if available. 2-3 plain sentences using the real numbers.

WHAT TO WATCH
What trends matter most right now? What would signal a change in posture? 2-3 sentences.

RISK FACTORS
What are the top 2 risks to monitor? Be specific. 2 sentences.

Use plain English. No markdown formatting. No bullet points."""


# ─────────────────────────────────────────────────────────────────────────────
# D-0071 — the analyst brief's providers
#
# One table rather than a branch. Each entry says the four things that differ
# between providers: which setting holds the key, where to post, which model,
# and how to get text back out. Adding a third is a row here, not an `if`.
#
# F-0084 was three places disagreeing about which provider was in use. The way
# to not have that again is to have one place that knows.
#
# Both are small, fast models: the brief is capped at 750 tokens and
# rate-limited per client, and the work is summarising figures
# `_gather_brief_context` already pulled from the database - not reasoning its
# way to them.
# ─────────────────────────────────────────────────────────────────────────────

def _anthropic_request(prompt: str, system: str, key: str, model: str):
    return (
        "https://api.anthropic.com/v1/messages",
        {"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
        {"model": model, "system": system, "max_tokens": 750, "temperature": 0.35,
         "messages": [{"role": "user", "content": prompt}]},
    )


def _anthropic_text(data: dict) -> str:
    # Content blocks, not choices. A refusal or a tool block would otherwise
    # index into something that is not text.
    return "".join(
        block.get("text", "") for block in data.get("content", [])
        if block.get("type") == "text"
    ).strip()


def _openai_style_request(prompt: str, system: str, key: str, model: str):
    return (
        "https://api.x.ai/v1/chat/completions",
        {"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        {"model": model, "temperature": 0.35, "max_tokens": 750,
         "messages": [{"role": "system", "content": system},
                      {"role": "user", "content": prompt}]},
    )


def _openai_style_text(data: dict) -> str:
    return (data.get("choices") or [{}])[0].get("message", {}).get("content", "").strip()


BRIEF_PROVIDERS = {
    "grok": {
        "label": "Grok",
        # D-0072: grok-2-latest was retired and returned 404 "does not exist".
        # Chosen from what the key can actually reach, on latency: the brief
        # is a summarisation of figures already gathered, and a reasoning
        # model spends the budget thinking. Measured against the real prompt:
        #
        #     grok-4.7                       36.3s  3163 chars
        #     grok-4.20-0309-non-reasoning    6.0s  2508 chars
        #     grok-4.3                        7.0s  1730 chars
        #
        # 36s is half the handler's 75s timeout for no benefit on this task.
        "model": "grok-4.20-0309-non-reasoning",
        "setting": "grok_api_key",
        "env": "GROK_API_KEY",
        "build": _openai_style_request,
        "parse": _openai_style_text,
    },
    "anthropic": {
        "label": "Claude Haiku",
        "model": "claude-haiku-4-5-20251001",
        "setting": "anthropic_api_key",
        "env": "ANTHROPIC_API_KEY",
        "build": _anthropic_request,
        "parse": _anthropic_text,
    },
}

# D-0071: the owner's ruling. Grok is the default; Anthropic is selectable.
DEFAULT_BRIEF_PROVIDER = "grok"


def brief_provider_availability() -> list:
    """Which providers this deployment can actually authenticate.

    The UI offers only these. Offering a provider whose key is absent means a
    503 the reader cannot act on, which is `F-0084` made interactive.
    """
    return [
        {
            "id": pid,
            "label": spec["label"],
            "model": spec["model"],
            "available": bool(getattr(settings, spec["setting"], "")),
            "default": pid == DEFAULT_BRIEF_PROVIDER,
        }
        for pid, spec in BRIEF_PROVIDERS.items()
    ]


@router.get("/analyze/providers")
async def analyze_providers():
    """Which brief providers are configured. Behind the same auth as the rest.

    Reports only whether a key is PRESENT - never any part of one.
    """
    return {"providers": brief_provider_availability(),
            "default": DEFAULT_BRIEF_PROVIDER}


@router.post("/analyze/country")
async def analyze_country(payload: dict, request: Request):
    """
    Generate a sovereign analysis brief for one country.
    Expects: { "country": "JPN" }
    Returns: { "text": "..." }

    Note there is deliberately no `db: Session = Depends(...)` here. The pool
    holds 10 connections and this handler awaits an external call for up to 75
    seconds; holding one across that await lets ten concurrent briefs block
    every other endpoint. The session below is opened and closed first.
    """
    provider_id = str(payload.get("provider") or DEFAULT_BRIEF_PROVIDER).strip().lower()
    spec = BRIEF_PROVIDERS.get(provider_id)
    if spec is None:
        raise HTTPException(
            status_code=422,
            detail=f"unknown provider; choose one of {sorted(BRIEF_PROVIDERS)}",
        )
    api_key = getattr(settings, spec["setting"], "")
    if not api_key:
        raise HTTPException(status_code=503, detail=f"{spec['env']} not configured")

    iso = str(payload.get("country", "")).strip().upper()
    if not iso.isalpha() or len(iso) != 3:
        raise HTTPException(
            status_code=422,
            detail="country must be a 3-letter ISO code; free-form prompts are not accepted",
        )

    client_key = request.client.host if request.client else "unknown"
    if not _brief_rate_limit_ok(client_key):
        raise HTTPException(
            status_code=429,
            detail=f"brief limit is {_BRIEF_MAX_PER_HOUR} per hour",
        )

    db = get_session()
    try:
        context = _gather_brief_context(db, iso)
    finally:
        db.close()

    if context is None:
        raise HTTPException(status_code=404, detail=f"unknown country {iso}")

    system_prompt = (
        "You are a brutally honest sovereign risk analyst. "
        "No sugarcoating. Focus on maximal truth and structural realities. "
        "Be direct and specific with numbers and implications."
    )

    url, headers, payload_data = spec["build"](
        _render_brief_prompt(context), system_prompt, api_key, spec["model"],
    )

    try:
        async with httpx.AsyncClient(timeout=75.0) as client:
            response = await client.post(url, json=payload_data, headers=headers)
            response.raise_for_status()
            text = spec["parse"](response.json())
            if not text:
                raise ValueError("no text content in the response")
            return {"text": text, "provider": provider_id, "model": spec["model"]}
    except Exception as e:
        # F-0010: an exception can carry request detail, and the key travels
        # in a header on one of these providers. Type only, never the message.
        # D-0072: the status code too. A 404 for a retired model and a 401
        # for a bad key both surfaced as "analysis failed" with a log line
        # naming only the exception type, which is not enough to tell them
        # apart. The body is still withheld - only the code is added.
        status = getattr(getattr(e, "response", None), "status_code", None)
        logger.error("brief failed for %s via %s: %s%s", iso, provider_id,
                     type(e).__name__, f" (HTTP {status})" if status else "")
        raise HTTPException(status_code=502, detail="analysis failed")


@router.get("/cds/all", response_model=List[CdsAllItem])
async def get_all_cds(db: Session = Depends(get_db)):
    """
    Returns latest 5Y (and same-source/same-as-of 10Y) CDS for countries with data.
    10Y and term structure stay blank unless both tenors share source and as-of.
    """
    cds5y_metrics = db.query(Metric).filter(
        Metric.code.like("%_CDS_5Y")
    ).all()

    results = []

    for metric5y in cds5y_metrics:
        country_code = metric5y.code.replace("_CDS_5Y", "")
        obs5 = latest_cds_observation(db, metric5y.code)
        obs10 = latest_cds_observation(db, f"{country_code}_CDS_10Y")

        # F-0074. The same rule the scorer applies, applied here too, because
        # this endpoint reads the same rows by a different path — and a number
        # on screen is a claim. Without this the CDS tab would keep displaying
        # exactly what the composite had just refused to score: Russia at
        # 13,775bps, and every 10Y frozen at the ISDA running coupon.
        coverage_5y = admit_cds_quote(
            obs5.get("value") if obs5 else None,
            obs5.get("date") if obs5 else None,
        )
        coverage_10y = admit_cds_quote(
            obs10.get("value") if obs10 else None,
            obs10.get("date") if obs10 else None,
        )
        if coverage_5y:
            obs5 = None
        if coverage_10y:
            obs10 = None

        cds5y, cds10y, term_spread = pair_cds_tenors(obs5, obs10)
        if cds5y is None and cds10y is None:
            continue

        as_of = None
        source = None
        if obs5:
            as_of = obs5["date"].isoformat() if obs5.get("date") else None
            source = obs5.get("source")
        elif obs10:
            as_of = obs10["date"].isoformat() if obs10.get("date") else None
            source = obs10.get("source")

        # D-0063: the board's own implied PD and six-month change. Only shown
        # alongside an admitted spread - a PD attached to a quote we refused
        # would be the refused number wearing a percentage sign.
        implied_pd = None
        var_6m = None
        if coverage_5y is None:
            pd_obs = latest_cds_observation(db, f"{country_code}_CDS_PD")
            v6_obs = latest_cds_observation(db, f"{country_code}_CDS_VAR6M")
            implied_pd = pd_obs.get("value") if pd_obs else None
            var_6m = v6_obs.get("value") if v6_obs else None

        results.append({
            "country_iso": country_code,
            # D-0091: the ISO3 the country card is keyed by. None when the
            # token is not in CDS_NAME_BY_ISO; the UI then shows the name
            # unlinked with a visible marker rather than guessing.
            "country_iso3": ISO_BY_CDS_NAME.get(country_code),
            "country_name": cds_country_for_code(metric5y.code),
            "cds_5y": cds5y,
            "implied_pd_pct": float(implied_pd) if implied_pd is not None else None,
            "var_6m_pct": float(var_6m) if var_6m is not None else None,
            "cds_10y": cds10y,
            "cds_term_spread": term_spread,
            "as_of": as_of,
            "source": source,
            # Why a tenor is blank, when it is blank.
            "coverage_5y": coverage_5y,
            "coverage_10y": coverage_10y,
        })

    results.sort(key=lambda x: (x["cds_5y"] or 0), reverse=True)
    return results


@router.get("/cds/coverage")
def cds_coverage(db: Session = Depends(get_db)):
    """
    CDS instrument coverage vs latest TimeSeries points, plus last CDS_MultiTenor log.
    Auth: same Basic Auth as other /api routes (not /api/health).
    """
    return get_cds_coverage(db)


@router.post("/cds/fetch")
def trigger_cds_fetch():
    """Manually run the CDS multi-tenor scrape once. Always close the session."""
    db = None
    try:
        db = get_session()
        return run_cds_fetch(db)
    except Exception as e:
        logger.error(f"CDS fetch failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if db is not None:
            db.close()


@router.get("/stress/composite", response_model=CompositeStressResponse)
def get_composite_stress(recompute: bool = Query(False, description="Bypass the stored snapshot and score from scratch"), db: Session = Depends(get_db)):
    """
    5-dimension composite sovereign stress scorer.
    Scores all countries on: Treasury MoM + consecutive months,
    Gold reserves trend, M2 monetary growth, Sovereign spread vs US 10Y,
    Petrodollar / oil pressure.
    Applies cross-asset (1.5x) and divergence (2.0x) multipliers.
    Returns tiered results: CRISIS / STRESSED / ELEVATED / WATCH.
    """
    try:
        # ORDER-03 D3: serve the stored result. Recomputing ~230 queries on
        # every click of the COMPOSITE tab is work the nightly job already did.
        if not recompute:
            snapshot = latest_composite_snapshot(db)
            if snapshot is not None:
                payload = json.loads(snapshot.payload)
                payload["computed_at"] = snapshot.computed_at.isoformat()
                payload["served_from"] = "snapshot"
                return payload
            # No snapshot yet - the job has not run. Fall through and compute,
            # rather than serving an empty tab and calling it success.

        result = compute_composite_stress(db)
        result["computed_at"] = datetime.utcnow().isoformat()
        result["served_from"] = "recompute"
        return result
    except Exception as e:
        logger.error(f"Composite stress calculation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/holdings/country/{iso_code}")
def get_country_tic_history(
    iso_code: str,
    months: int = Query(24, ge=1, le=120),
    db: Session = Depends(get_db)
):
    """Get TIC holdings history for a specific country (legacy endpoint)."""
    metric = db.query(Metric).filter_by(code="TIC_UST_HOLDINGS").first()
    if not metric:
        raise HTTPException(status_code=404, detail="TIC data not loaded")

    country = db.query(Country).filter_by(iso_code=iso_code).first()
    if not country:
        raise HTTPException(status_code=404, detail=f"Country {iso_code} not found")

    cutoff = datetime.utcnow() - timedelta(days=months * 31)
    rows = db.query(TimeSeries).filter(
        TimeSeries.metric_id == metric.id,
        TimeSeries.country_id == country.id,
        TimeSeries.date >= cutoff,
    ).order_by(TimeSeries.date.asc()).all()

    history = []
    for i, r in enumerate(rows):
        mom = None
        if i > 0:
            prev = float(rows[i-1].value)
            if prev:
                mom = round((float(r.value) - prev) / prev * 100, 2)
        history.append({
            "date": r.date.strftime("%Y-%m"),
            "holdings_bn": round(float(r.value), 2),
            "mom_change_pct": mom,
        })

    latest = float(rows[-1].value) if rows else None
    peak = max((float(r.value) for r in rows), default=None)

    return {
        "country": {"iso": iso_code, "name": country.name, "region": country.region},
        "summary": {
            "latest_holdings_bn": round(latest, 2) if latest else None,
            "peak_holdings_bn": round(peak, 2) if peak else None,
            "drawdown_from_peak_pct": round((latest - peak) / peak * 100, 1) if latest and peak and peak > 0 else None,
            "months": len(rows),
        },
        "history": history,
    }
from fastapi import Query
from typing import Optional

# D-0061: how much CDS history the country panel charts. Ninety days is
# what the board retains in practice and matches the widening window the
# scorer measures over, so the chart and the score describe the same span.
CDS_HISTORY_DAYS = 90


@router.get("/cds", response_model=CdsCountryResponse)
async def get_latest_cds(country: str = Query(..., description="Country ISO code (e.g. TUR, MEX, BRA)"), db: Session = Depends(get_db)):
    """
    Returns the latest 5Y and 10Y CDS values for a country.
    Used by the frontend to enrich Grok analysis prompts.
    """
    # F-0078: CDS metrics encode the country by NAME ("TURKEY_CDS_5Y"), and
    # this endpoint is called with an ISO code by the only thing that calls it
    # — the country panel. It built "TUR_CDS_5Y", which does not exist, so the
    # 5Y CDS tile read "No coverage" for every country, always. The docstring
    # promised ISO codes; the lookup never accepted one.
    #
    # Accept both: the ISO code it is actually sent, and the namespace token
    # anyone reading the metric names would reach for.
    country_upper = country.upper()
    prefix = CDS_NAME_BY_ISO.get(country_upper, country_upper)

    cds5y_code = f"{prefix}_CDS_5Y"
    cds10y_code = f"{prefix}_CDS_10Y"

    obs5 = latest_cds_observation(db, cds5y_code)
    obs10 = latest_cds_observation(db, cds10y_code)

    # F-0074, third reader. This path reads the same rows as the scorer and
    # /cds/all and had no admissibility check of its own.
    coverage_5y = admit_cds_quote(
        obs5.get("value") if obs5 else None,
        obs5.get("date") if obs5 else None,
    )
    coverage_10y = admit_cds_quote(
        obs10.get("value") if obs10 else None,
        obs10.get("date") if obs10 else None,
    )
    if coverage_5y:
        obs5 = None
    if coverage_10y:
        obs10 = None

    cds5y, cds10y, term_spread = pair_cds_tenors(obs5, obs10)

    # D-0061: the 5Y series, so the country panel can chart it alongside
    # holdings and gold. Returned from THIS endpoint rather than having the
    # frontend query /timeseries directly, because the ISO -> metric-name map
    # lives here and a second copy of it in JavaScript is F-0062 again.
    #
    # Only when the latest quote was admitted: charting a history whose most
    # recent point was refused would show a line the tile above it denies.
    history = []
    if coverage_5y is None:
        metric = db.query(Metric).filter(Metric.code == cds5y_code).first()
        if metric:
            cutoff = datetime.utcnow() - timedelta(days=CDS_HISTORY_DAYS)
            rows = db.query(TimeSeries).filter(
                TimeSeries.metric_id == metric.id,
                TimeSeries.country_id == None,
                TimeSeries.date >= cutoff,
            ).order_by(TimeSeries.date.asc()).all()
            history = [
                {"date": r.date.isoformat(), "value": float(r.value)}
                for r in rows
            ]

    if cds5y is None and cds10y is None:
        return {
            "country": country_upper,
            "5Y": None,
            "10Y": None,
            "term_spread": None,
            "coverage": coverage_5y or "no coverage",
            "history": [],
            "message": f"No usable CDS for this country: {coverage_5y or 'no coverage'}",
        }

    as_of = None
    source = None
    if obs5:
        as_of = obs5["date"].isoformat() if obs5.get("date") else None
        source = obs5.get("source")

    return {
        "country": country_upper,
        "5Y": {
            "value": cds5y,
            "unit": "bps",
            "as_of": as_of,
            "source": source,
        } if cds5y is not None else None,
        "10Y": {
            "value": cds10y,
            "unit": "bps",
        } if cds10y is not None else None,
        "term_spread": term_spread,
        "as_of": as_of,
        "source": source,
        "coverage": "quoted",
        "coverage_10y": coverage_10y,
        "history": history,
    }

# ── Treasury auction demand (ORDER auction-demand §6) ────────────────────────
#
# Read-only. z-scores are computed at read time over every stored auction
# (D-0099): ~6,300 rows, and the window for any one auction needs the 26 before
# it whatever filter the caller applied.

from database.models import TreasuryAuction  # noqa: E402
from pipelines import auction_demand  # noqa: E402
from api.schemas import (  # noqa: E402
    AuctionDetailResponse,
    AuctionListResponse,
    AuctionSummaryResponse,
)

_AUCTION_FLOATS = (
    "offering_amt", "total_tendered", "total_accepted", "soma_tendered",
    "soma_accepted", "comp_accepted", "b2c_reported", "b2c_recomputed",
    "primary_dealer_share", "direct_bidder_share", "indirect_bidder_share",
    "bidder_gap", "allocation_pct", "high_yield", "high_discnt_rate",
    "high_investment_rate",
)


def _num(value):
    return None if value is None else float(value)


def _iso(value):
    return value.isoformat() if value is not None else None


def _auction_row(a: TreasuryAuction) -> dict:
    row = {
        "cusip": a.cusip,
        "auction_date": a.auction_date,
        "issue_date": _iso(a.issue_date),
        "maturity_date": _iso(a.maturity_date),
        "security_type": a.security_type,
        "security_term": a.security_term,
        "original_security_term": a.original_security_term,
        "term_group": a.term_group,
        "term": auction_demand.TERM_BY_GROUP.get(a.term_group),
        "reopening": a.reopening,
        "b2c_check": a.b2c_check,
        "identity_check": a.identity_check,
        "shares_check": a.shares_check,
        "null_reasons": json.loads(a.null_reasons or "{}"),
    }
    for field in _AUCTION_FLOATS:
        row[field] = getattr(a, field)
    return row


def _scored_auctions(db: Session):
    """(scored rows oldest-first, data_as_of, {key: model}) for every stored auction."""
    models = db.query(TreasuryAuction).order_by(
        TreasuryAuction.auction_date, TreasuryAuction.cusip
    ).all()
    scored = auction_demand.attach_zscores([_auction_row(a) for a in models])
    for row in scored:
        row["auction_date"] = row["auction_date"].isoformat()
        for field in _AUCTION_FLOATS:
            row[field] = _num(row[field])
    data_as_of = models[-1].auction_date.isoformat() if models else None
    return scored, data_as_of, {(a.cusip, a.auction_date.isoformat()): a for a in models}


@router.get("/auctions", response_model=AuctionListResponse)
async def get_auctions(
    term: Optional[str] = Query(None, description="Panel term label, e.g. 26W"),
    type: Optional[str] = Query(None, description="Bill, Note or Bond"),
    from_: Optional[str] = Query(None, alias="from", description="YYYY-MM-DD"),
    to: Optional[str] = Query(None, description="YYYY-MM-DD"),
    db: Session = Depends(get_db),
):
    """Auction results with demand metrics and null reasons, newest first."""
    if term is not None and term not in auction_demand.CHARTED_TERMS:
        raise HTTPException(
            status_code=400,
            detail=f"term must be one of {', '.join(auction_demand.CHARTED_TERMS)}",
        )
    scored, data_as_of, _ = _scored_auctions(db)
    rows = [
        r for r in reversed(scored)
        if (term is None or r["term"] == term)
        and (type is None or r["security_type"] == type)
        and (from_ is None or r["auction_date"] >= from_)
        and (to is None or r["auction_date"] <= to)
    ]
    return {"data_as_of": data_as_of, "count": len(rows), "auctions": rows}


@router.get("/auctions/summary", response_model=AuctionSummaryResponse)
async def get_auctions_summary(db: Session = Depends(get_db)):
    """The latest auction for each charted term, with both z-scores."""
    scored, data_as_of, _ = _scored_auctions(db)
    latest = {}
    for row in scored:  # oldest first, so the last write per term wins
        if row["term"] is not None:
            latest[row["term"]] = row
    terms = [latest[t] for t in auction_demand.CHARTED_TERMS if t in latest]
    return {
        "data_as_of": data_as_of,
        "window_n": auction_demand.WINDOW_N,
        "min_observations": auction_demand.MIN_OBSERVATIONS,
        "terms": terms,
    }


@router.get("/auctions/{cusip}/{auction_date}", response_model=AuctionDetailResponse)
async def get_auction(cusip: str, auction_date: str, db: Session = Depends(get_db)):
    """One auction, with the bidder breakdown and SOMA (excluded from B2C, §2)."""
    scored, data_as_of, models = _scored_auctions(db)
    a = models.get((cusip, auction_date))
    if a is None:
        raise HTTPException(status_code=404, detail=f"No auction {cusip} on {auction_date}")
    row = next(r for r in scored if r["cusip"] == cusip and r["auction_date"] == auction_date)
    row["bidders"] = {
        name: {
            "tendered": _num(getattr(a, f"{prefix}_tendered")),
            "accepted": _num(getattr(a, f"{prefix}_accepted")),
            "share": _num(getattr(a, f"{prefix}_share")),
        }
        for name, prefix in (("primary_dealer", "primary_dealer"),
                             ("direct", "direct_bidder"),
                             ("indirect", "indirect_bidder"))
    }
    row["soma"] = {
        "tendered": _num(a.soma_tendered),
        "accepted": _num(a.soma_accepted),
        "excluded_from_b2c": True,
    }
    row["comp_tendered"] = _num(a.comp_tendered)
    row["noncomp_accepted"] = _num(a.noncomp_accepted)
    row["fima_noncomp_accepted"] = _num(a.fima_noncomp_accepted)
    return {"data_as_of": data_as_of, "auction": row}
