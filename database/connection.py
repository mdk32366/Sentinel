from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool
from config import settings
from database.models import Base
import logging

logger = logging.getLogger(__name__)

# Create engine with connection pooling
engine = create_engine(
    settings.database_url,
    poolclass=QueuePool,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,  # Verify connections before using
    echo=False,  # Set to True for SQL logging
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    """Initialize database tables"""
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables created/verified")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise


def get_db() -> Session:
    """Get database session (for FastAPI dependency injection)"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_session() -> Session:
    """Get a database session for scripts/pipelines"""
    return SessionLocal()
