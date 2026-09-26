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

logger = logging.getLogger(__name__)
scheduler = BackgroundScheduler()

# After FRED at 2 AM. Env override preserved; config default is also 3.
cds_hour = int(os.getenv("CDS_FETCH_HOUR", "3"))


def scheduled_fred_fetch():
    try:
        db = get_session()
        result = run_fred_fetch(db)
        logger.info(f"FRED fetch: {result['status']} - {result['inserted']} inserted, {result['updated']} updated")
    except Exception as e:
        logger.error(f"Scheduled FRED fetch failed: {e}", exc_info=True)
    finally:
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
    try:
        db = get_session()
        result = run_treasury_holdings_fetch(db)
        logger.info(f"Treasury fetch: {result['status']}")
    except Exception as e:
        logger.error(f"Scheduled Treasury fetch failed: {e}", exc_info=True)
    finally:
        db.close()


def scheduled_gold_fetch():
    try:
        db = get_session()
        result = run_gold_reserves_fetch(db)
        logger.info(f"Gold fetch: {result['status']}")
    except Exception as e:
        logger.error(f"Scheduled gold fetch failed: {e}", exc_info=True)
    finally:
        db.close()


def scheduled_stress_score():
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
