"""Sentinel test suite.

Importing this package marks the process as a test run, which arms the
positive-identity guard in database.connection. Any request for a real session
from here on must prove the database is disposable (Day-One Step 12).

unittest imports this package for every entry point - `discover`, or a named
module - so there is no route into the suite that bypasses the mark.
"""
import os

os.environ["SENTINEL_TEST_RUN"] = "1"
