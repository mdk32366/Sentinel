import logging
import os
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from config import settings
from database.connection import get_session
from pipelines.fred_fetcher import run_fred_fetch
from pipelines.treasury_holdings import run_treasury_holdings_fetch
from pipelines.stress_score_v2 import run_stress_score_calculation
from pipelines.gold_reserves import run_gold_reserves_fetch
from pipelines.cds_fetcher import run_cds_fetch
from pipelines.treasury_direct import run_treasury_direct_fetch
from pipelines.freshness_watchdog import run_freshness_check
from pipelines.gold_price_fetcher import run_gold_price_fetch
from pipelines.composite_stress import persist_composite_snapshot

logger = logging.getLogger(__name__)
# ORDER-01 B5. Set once on the scheduler rather than repeated on every
# add_job: a per-job keyword is a thing the NEXT job can forget, which is how
# only the CDS job ended up with a misfire grace period.
#
#   misfire_grace_time  a job whose fire time was missed (restart, deploy,
#                       machine asleep) still runs if it is under an hour late,
#                       instead of being silently dropped.
#   coalesce            several missed fires collapse into one run rather than
#                       a burst against a public API.
#   max_instances       one run at a time. A 3-minute FRED fetch must never
#                       overlap itself and write the same rows twice.
JOB_DEFAULTS = {
    "misfire_grace_time": 3600,
    "coalesce": True,
    "max_instances": 1,
}

scheduler = BackgroundScheduler(job_defaults=JOB_DEFAULTS)

# After FRED at 2 AM. Env override preserved; config default is also 3.
cds_hour = int(os.getenv("CDS_FETCH_HOUR", "3"))


def scheduled_fred_fetch():
    db = None
    try:
        db = get_session()
        result = run_fred_fetch(db)
        logger.info(f"FRED fetch: {result['status']} - {result['inserted']} inserted, {result['updated']} updated")
    except Exception as e:
        logger.error(f"Scheduled FRED fetch failed: {e}", exc_info=True)
    finally:
        if db is not None:
            db.close()


def scheduled_cds_fetch():
    """Daily CDS scrape — always close the session (import-time lambda leaked it)."""
    db = None
    try:
        db = get_session()
        result = run_cds_fetch(db)
        logger.info(
            f"CDS fetch: {result['status']} source={result.get('source')} "
            f"as-of={result.get('as_of')} - {result['inserted']} inserted, "
            f"{result['updated']} updated (ok={result.get('ok')}/{result.get('attempted')})"
        )
    except Exception as e:
        logger.error(f"Scheduled CDS fetch failed: {e}", exc_info=True)
    finally:
        if db is not None:
            db.close()


def scheduled_treasury_fetch():
    db = None
    try:
        db = get_session()
        result = run_treasury_holdings_fetch(db)
        logger.info(f"Treasury fetch: {result['status']}")
    except Exception as e:
        logger.error(f"Scheduled Treasury fetch failed: {e}", exc_info=True)
    finally:
        if db is not None:
            db.close()


def scheduled_gold_fetch():
    db = None
    try:
        db = get_session()
        result = run_gold_reserves_fetch(db)
        logger.info(f"Gold fetch: {result['status']}")
    except Exception as e:
        logger.error(f"Scheduled gold fetch failed: {e}", exc_info=True)
    finally:
        if db is not None:
            db.close()


def scheduled_stress_score():
    db = None
    try:
        db = get_session()
        result = run_stress_score_calculation(db)
        if result["status"] == "success":
            logger.info(f"Stress score: {result['data']['overall_score']} - {result['data']['interpretation']}")
        else:
            logger.error(f"Stress score failed: {result.get('error')}")
    except Exception as e:
        logger.error(f"Scheduled stress score failed: {e}", exc_info=True)
    finally:
        if db is not None:
            db.close()


def scheduled_treasury_direct_fetch():
    """Same-day par yield curve, straight from Treasury.

    Runs at 21:00 UTC, after Treasury publishes and before FRED's 02:00 run,
    so the curve is current a business day earlier than FRED alone (D-0022).
    FRED overwrites with its revised value overnight; A-0001's contract test
    is what makes that safe.
    """
    db = None
    try:
        db = get_session()
        result = run_treasury_direct_fetch(db)
        logger.info(
            f"Treasury Direct: {result['status']} - {result['inserted']} inserted, "
            f"{result['updated']} updated, latest={result.get('latest_date')}"
        )
        if result.get("anomalies"):
            logger.warning(f"Treasury Direct anomalies: {result['anomalies']}")
    except Exception as e:
        logger.error(f"Scheduled Treasury Direct fetch failed: {e}", exc_info=True)
    finally:
        if db is not None:
            db.close()


def scheduled_composite_snapshot():
    """Score every country once, nightly, and store the result (D-0042).

    Runs at 04:45 UTC, after the 04:30 stress score and after every data
    pipeline has landed. ORDER-03 D3 assumed the 04:30 job already computed
    this; it does not - that job runs a different scorer (F-0047).
    """
    db = None
    try:
        db = get_session()
        result = persist_composite_snapshot(db)
        logger.info(f"Composite snapshot: {result['countries']} countries stored")
    except Exception as e:
        logger.error(f"Scheduled composite snapshot failed: {e}", exc_info=True)
    finally:
        if db is not None:
            db.close()


def scheduled_gold_price_fetch():
    """LBMA gold fix, daily at 02:30 UTC (D-0041).

    Distinct from scheduled_gold_fetch, which is gold RESERVES by country and
    stays manual - the WGC country series is behind an account wall with no
    public API, and Part B did not change that.
    """
    db = None
    try:
        db = get_session()
        result = run_gold_price_fetch(db)
        logger.info(
            f"Gold price: {result['status']} - {result['inserted']} inserted, "
            f"{result['updated']} updated, latest={result.get('latest_date')}"
        )
    except Exception as e:
        logger.error(f"Scheduled gold price fetch failed: {e}", exc_info=True)
    finally:
        if db is not None:
            db.close()


def scheduled_freshness_check():
    """Daily freshness sweep. Reads; the only thing it writes is its own log row."""
    db = None
    try:
        db = get_session()
        report = run_freshness_check(db)
        logger.info(
            f"Freshness: {report['status']} - {report['counts']}"
            if isinstance(report, dict) and "counts" in report
            else f"Freshness: {report}"
        )
    except Exception as e:
        logger.error(f"Scheduled freshness check failed: {e}", exc_info=True)
    finally:
        if db is not None:
            db.close()


def scheduled_startup_fetches():
    """One-shot cold-start FRED → TIC → gold → stress. Must not raise."""
    logger.info("Running startup FRED/TIC/gold/stress fetches in background")
    for name, func in (
        ("FRED", scheduled_fred_fetch),
        ("TIC", scheduled_treasury_fetch),
        ("gold", scheduled_gold_fetch),
        ("stress", scheduled_stress_score),
    ):
        try:
            func()
        except Exception as e:
            logger.error(f"Startup {name} fetch failed: {e}", exc_info=True)


def start_scheduler():
    if not settings.scheduler_enabled:
        logger.info("Scheduler disabled in config")
        return

    scheduler.add_job(
        scheduled_fred_fetch,
        CronTrigger(hour=settings.fred_fetch_hour, minute=0),
        id="fred_fetch", name="FRED Data Fetch", replace_existing=True,
    )
    logger.info(f"Scheduled FRED fetch daily at {settings.fred_fetch_hour}:00")

    scheduler.add_job(
        scheduled_treasury_fetch,
        CronTrigger(day=settings.treasury_fetch_day, hour=3, minute=0),
        id="treasury_fetch", name="Treasury Holdings Fetch", replace_existing=True,
    )
    logger.info(f"Scheduled Treasury fetch on day {settings.treasury_fetch_day} at 03:00")

    scheduler.add_job(
        scheduled_stress_score,
        CronTrigger(hour=4, minute=30),
        id="stress_score", name="Macro Stress Score Calculation", replace_existing=True,
    )
    logger.info("Scheduled stress score daily at 04:30")

    scheduler.add_job(
        scheduled_gold_fetch,
        CronTrigger(day=settings.gold_fetch_day, hour=4, minute=0),
        id="gold_fetch", name="Gold Reserves Fetch", replace_existing=True,
    )
    logger.info(f"Scheduled gold fetch on day {settings.gold_fetch_day} at 04:00")

    scheduler.add_job(
        scheduled_cds_fetch,
        CronTrigger(hour=cds_hour, minute=0),
        id="cds_multi_tenor_job",
        name="CDS Multi-Tenor Fetch",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    logger.info(f"CDS Multi-Tenor pipeline scheduled daily at {cds_hour}:00 UTC")

    scheduler.add_job(
        scheduled_treasury_direct_fetch,
        CronTrigger(day_of_week="mon-fri", hour=21, minute=0),
        id="treasury_direct", name="Treasury Direct Par Yield Curve",
        replace_existing=True,
    )
    logger.info("Scheduled Treasury Direct weekdays at 21:00 UTC")

    scheduler.add_job(
        scheduled_composite_snapshot,
        CronTrigger(hour=4, minute=45),
        id="composite_snapshot", name="Composite Stress Snapshot",
        replace_existing=True,
    )
    logger.info("Scheduled composite snapshot daily at 04:45 UTC")

    scheduler.add_job(
        scheduled_gold_price_fetch,
        CronTrigger(hour=2, minute=30),
        id="gold_price", name="Gold Spot Price (LBMA)",
        replace_existing=True,
    )
    logger.info("Scheduled gold price daily at 02:30 UTC")

    scheduler.add_job(
        scheduled_freshness_check,
        CronTrigger(hour=5, minute=0),
        id="freshness_check", name="Data Freshness Watchdog",
        replace_existing=True,
    )
    logger.info("Scheduled freshness watchdog daily at 05:00 UTC")

    scheduler.start()
    logger.info("Scheduler started")

    # One-shots after ready — do not block FastAPI lifespan before yield (D-0019 / D-0020).
    scheduler.add_job(
        scheduled_startup_fetches,
        id="startup_fetches",
        name="Startup FRED/TIC/gold/stress fetches",
        next_run_time=datetime.now(),
        replace_existing=True,
        misfire_grace_time=3600,
    )
    logger.info("Queued one-shot startup FRED/TIC/gold/stress fetches (non-blocking)")

    scheduler.add_job(
        scheduled_cds_fetch,
        id="startup_cds_fetch",
        name="Startup CDS fetch",
        next_run_time=datetime.now(),
        replace_existing=True,
        misfire_grace_time=3600,
    )
    logger.info("Queued one-shot startup CDS fetch (non-blocking)")


def stop_scheduler():
    scheduler.shutdown()
    logger.info("Scheduler stopped")
