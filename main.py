import logging
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import sys

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('treasury_monitor.log'),
    ]
)
logger = logging.getLogger(__name__)

# Import after logging setup
from config import settings
from database.connection import init_db, get_session
from pipelines.scheduler import start_scheduler, stop_scheduler
from api.routes import router
from pipelines.fred_fetcher import run_fred_fetch
from pipelines.treasury_holdings import run_treasury_holdings_fetch
from pipelines.stress_score import run_stress_score_calculation


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    # Startup
    logger.info("Treasury Monitor starting up...")
    try:
        init_db()
        logger.info("Database initialized")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        raise
    
    # Run initial FRED fetch to populate data
    logger.info("Running initial FRED fetch...")
    try:
        db = get_session()
        result = run_fred_fetch(db)
        logger.info(f"Initial FRED fetch: {result['status']} - {result['inserted']} inserted, {result['updated']} updated")
        db.close()
    except Exception as e:
        logger.error(f"Initial FRED fetch failed: {e}")
    
    # Run initial TIC holdings fetch
    logger.info("Running initial TIC holdings fetch...")
    try:
        db = get_session()
        result = run_treasury_holdings_fetch(db)
        logger.info(f"Initial TIC holdings fetch: {result['status']}")
        db.close()
    except Exception as e:
        logger.error(f"Initial TIC holdings fetch failed: {e}")
    
    # Run initial stress score calculation
    logger.info("Running initial stress score calculation...")
    try:
        db = get_session()
        result = run_stress_score_calculation(db)
        if result['status'] == 'success':
            logger.info(f"Initial stress score: {result['data']['overall_score']}")
        db.close()
    except Exception as e:
        logger.error(f"Initial stress score calculation failed: {e}")
    
    # Start scheduler
    start_scheduler()
    
    yield
    
    # Shutdown
    logger.info("Treasury Monitor shutting down...")
    stop_scheduler()
    logger.info("Shutdown complete")


# Create FastAPI app
app = FastAPI(
    title="Treasury Monitor API",
    description="Monitor US Treasury bonds, oil prices, gold holdings, and USD strength indicators",
    version="1.0.0",
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for local dev
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(router)

# Mount React frontend
app.mount("/", StaticFiles(directory="api/static", html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        app,
        host=settings.api_host,
        port=settings.api_port,
        log_level=settings.log_level.lower(),
    )

