import logging
import secrets
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import sys

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('treasury_monitor.log'),
    ]
)
logger = logging.getLogger(__name__)

from config import settings
from database.connection import init_db, get_session
from pipelines.scheduler import start_scheduler, stop_scheduler
from api.routes import router
from pipelines.fred_fetcher import run_fred_fetch
from pipelines.treasury_holdings import run_treasury_holdings_fetch

# ── Basic Auth ────────────────────────────────────────────────────────────────

security = HTTPBasic()

def require_auth(credentials: HTTPBasicCredentials = Depends(security)):
    """Verify HTTP Basic Auth credentials against env vars."""
    correct_username = secrets.compare_digest(
        credentials.username.encode("utf-8"),
        settings.auth_username.encode("utf-8"),
    )
    correct_password = secrets.compare_digest(
        credentials.password.encode("utf-8"),
        settings.auth_password.encode("utf-8"),
    )
    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Treasury Monitor starting up...")
    try:
        init_db()
        logger.info("Database initialized")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        raise

    logger.info("Running initial FRED fetch...")
    try:
        db = get_session()
        result = run_fred_fetch(db)
        logger.info(f"FRED fetch: {result['status']} - {result['inserted']} inserted, {result['updated']} updated")
        db.close()
    except Exception as e:
        logger.error(f"Initial FRED fetch failed: {e}")

    logger.info("Running initial TIC holdings fetch...")
    try:
        db = get_session()
        result = run_treasury_holdings_fetch(db)
        logger.info(f"TIC holdings fetch: {result['status']}")
        db.close()
    except Exception as e:
        logger.error(f"Initial TIC holdings fetch failed: {e}")

    logger.info("Running initial gold reserves fetch...")
    try:
        from pipelines.gold_reserves import run_gold_reserves_fetch
        db = get_session()
        result = run_gold_reserves_fetch(db)
        logger.info(f"Gold reserves fetch: {result['status']} - {result.get('countries', 0)} countries")
        db.close()
    except Exception as e:
        logger.error(f"Initial gold reserves fetch failed: {e}")

    logger.info("Running initial stress score calculation...")
    try:
        from pipelines.stress_score_v2 import run_stress_score_calculation
        db = get_session()
        result = run_stress_score_calculation(db)
        if result['status'] == 'success':
            logger.info(f"Stress score: {result['data']['overall_score']}")
        db.close()
    except Exception as e:
        logger.error(f"Initial stress score calculation failed: {e}")

    start_scheduler()
    yield

    logger.info("Treasury Monitor shutting down...")
    stop_scheduler()
    logger.info("Shutdown complete")


app = FastAPI(
    title="Treasury Monitor API",
    description="Monitor US Treasury bonds, oil prices, gold holdings, and USD strength indicators",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Apply auth to all API routes
app.include_router(router, dependencies=[Depends(require_auth)])

# Static frontend — protected by browser Basic Auth prompt
app.mount("/", StaticFiles(directory="api/static", html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host=settings.api_host,
        port=settings.api_port,
        log_level=settings.log_level.lower(),
    )
