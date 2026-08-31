import logging
import secrets
from fastapi import FastAPI, status
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import PlainTextResponse
from contextlib import asynccontextmanager
import base64
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

# Static frontend + API: HTTP Basic Auth so the browser prompts on GET /
# /api/health stays open for Docker/Fly probes.
OPEN_PATHS = {"/api/health"}

class BasicAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if request.url.path in OPEN_PATHS:
            return await call_next(request)
        header = request.headers.get("authorization", "")
        if not _credentials_ok(header):
            return PlainTextResponse(
                "Unauthorized",
                status_code=status.HTTP_401_UNAUTHORIZED,
                headers={"WWW-Authenticate": "Basic"},
            )
        return await call_next(request)


def _credentials_ok(header: str) -> bool:
    if not header.lower().startswith("basic "):
        return False
    try:
        decoded = base64.b64decode(header.split(" ", 1)[1]).decode("utf-8")
        username, password = decoded.split(":", 1)
    except Exception:
        return False
    user_ok = secrets.compare_digest(
        username.encode("utf-8"),
        settings.auth_username.encode("utf-8"),
    )
    pass_ok = secrets.compare_digest(
        password.encode("utf-8"),
        settings.auth_password.encode("utf-8"),
    )
    return bool(user_ok and pass_ok)


app.add_middleware(BasicAuthMiddleware)
app.include_router(router)
app.mount("/", StaticFiles(directory="api/static", html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host=settings.api_host,
        port=settings.api_port,
        log_level=settings.log_level.lower(),
    )
