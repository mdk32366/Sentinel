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
from database.connection import init_db
from pipelines.scheduler import start_scheduler, stop_scheduler
from api.routes import router

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

    # Heavy FRED/TIC/gold/stress work is a one-shot APScheduler job inside
    # start_scheduler(); do not block /api/health on it (D-0019 / AT-0012).
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
