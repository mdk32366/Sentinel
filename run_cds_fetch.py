#!/usr/bin/env python3
"""
Standalone runner for the Multi-Tenor CDS pipeline (5Y + 10Y).
Usage: python run_cds_fetch.py
"""

from database.connection import get_session
from pipelines.cds_fetcher import run_cds_fetch

if __name__ == "__main__":
    print("=== Sentinel CDS Multi-Tenor Fetch ===")
    db = get_session()
    try:
        result = run_cds_fetch(db)
        print(result)
    except Exception as e:
        print(f"Error: {e}")
    finally:
        db.close()
    print("=== Complete ===")