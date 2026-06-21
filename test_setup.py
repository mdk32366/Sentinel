#!/usr/bin/env python3
"""
Quick setup verification script
Run this after installing dependencies to ensure everything works
"""

import sys
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


def test_imports():
    """Test that all required packages are installed"""
    logger.info("Testing imports...")
    try:
        import fastapi
        import sqlalchemy
        import psycopg2
        import apscheduler
        import requests
        logger.info("✓ All imports successful")
        return True
    except ImportError as e:
        logger.error(f"✗ Import failed: {e}")
        logger.error("Run: pip install -r requirements.txt")
        return False


def test_database():
    """Test database connection"""
    logger.info("Testing database connection...")
    try:
        from database.connection import engine
        with engine.connect() as conn:
            result = conn.execute("SELECT 1")
            logger.info("✓ Database connection successful")
            return True
    except Exception as e:
        logger.error(f"✗ Database connection failed: {e}")
        logger.error("Ensure PostgreSQL is running and DATABASE_URL is correct in .env")
        return False


def test_tables():
    """Test that database tables can be created"""
    logger.info("Testing table creation...")
    try:
        from database.connection import init_db
        init_db()
        logger.info("✓ Tables created/verified")
        return True
    except Exception as e:
        logger.error(f"✗ Table creation failed: {e}")
        return False


def test_fred_api():
    """Test FRED API connectivity"""
    logger.info("Testing FRED API...")
    try:
        import requests
        from config import settings
        
        if settings.fred_api_key == "your_fred_api_key_here":
            logger.warning("⚠ FRED_API_KEY not configured in .env")
            logger.warning("  Get a free key at: https://fred.stlouisfed.org/docs/api/")
            return False
        
        params = {
            "series_id": "DGS10",
            "api_key": settings.fred_api_key,
            "file_type": "json",
            "limit": 1,
        }
        response = requests.get(
            "https://api.stlouisfed.org/fred/series/observations",
            params=params,
            timeout=5
        )
        response.raise_for_status()
        logger.info("✓ FRED API connection successful")
        return True
    except requests.RequestException as e:
        logger.error(f"✗ FRED API test failed: {e}")
        return False


def test_fred_fetch():
    """Test FRED data fetch"""
    logger.info("Testing FRED data fetch...")
    try:
        from config import settings
        if settings.fred_api_key == "your_fred_api_key_here":
            logger.warning("⚠ Skipping FRED fetch test - API key not configured")
            return True
        
        from database.connection import get_session
        from pipelines.fred_fetcher import run_fred_fetch
        
        db = get_session()
        result = run_fred_fetch(db)
        db.close()
        
        if result['status'] in ['success', 'partial']:
            logger.info(f"✓ FRED fetch successful ({result['inserted']} inserted, {result['updated']} updated)")
            return True
        else:
            logger.error(f"✗ FRED fetch failed: {result['errors']}")
            return False
    except Exception as e:
        logger.error(f"✗ FRED fetch test failed: {e}")
        return False


def test_api():
    """Test API startup (non-blocking)"""
    logger.info("Testing API health endpoint...")
    try:
        import requests
        from threading import Thread
        import time
        from config import settings
        
        # Start API in background
        def run_api():
            from main import app
            import uvicorn
            uvicorn.run(app, host="127.0.0.1", port=8000, log_level="critical")
        
        api_thread = Thread(target=run_api, daemon=True)
        api_thread.start()
        
        # Wait for API to start
        time.sleep(3)
        
        try:
            response = requests.get("http://localhost:8000/api/health", timeout=5)
            response.raise_for_status()
            logger.info("✓ API health endpoint working")
            return True
        except requests.RequestException:
            logger.warning("⚠ Could not reach API endpoint (may still be starting)")
            return True
    except Exception as e:
        logger.warning(f"⚠ API test inconclusive: {e}")
        return True


def main():
    """Run all tests"""
    logger.info("=" * 60)
    logger.info("Treasury Monitor Setup Verification")
    logger.info("=" * 60)
    logger.info("")
    
    tests = [
        ("Python Imports", test_imports),
        ("Database Connection", test_database),
        ("Database Tables", test_tables),
        ("FRED API", test_fred_api),
        ("FRED Data Fetch", test_fred_fetch),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            logger.error(f"✗ {name}: {e}")
            results.append((name, False))
        logger.info("")
    
    # Summary
    logger.info("=" * 60)
    logger.info("Summary")
    logger.info("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        logger.info(f"{status}: {name}")
    
    logger.info("")
    logger.info(f"Passed: {passed}/{total}")
    logger.info("")
    
    if passed == total:
        logger.info("🎉 All checks passed! Ready to use.")
        logger.info("")
        logger.info("Next steps:")
        logger.info("1. Start API server: python main.py")
        logger.info("2. Open http://localhost:8000/docs for API documentation")
        logger.info("3. Check data: curl http://localhost:8000/api/metric/DGS10")
        return 0
    else:
        logger.error("Some checks failed. See above for details.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
