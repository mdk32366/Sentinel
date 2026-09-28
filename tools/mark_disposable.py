"""Mark a database as disposable by giving it the canary table.

Deliberately a separate script that a human runs, and deliberately not called
by the application or by any test fixture. A canary that the system can create
for itself identifies nothing.

    python tools/mark_disposable.py            # uses settings.database_url
    python tools/mark_disposable.py --show     # report status, change nothing

Never run this against a database whose data you would miss.
"""
import argparse
import sys

from sqlalchemy import create_engine, text

from config import settings
from database.connection import CANARY_MARKER, CANARY_TABLE


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--show", action="store_true", help="report only")
    args = parser.parse_args()

    engine = create_engine(settings.database_url)
    with engine.connect() as conn:
        target = conn.execute(text("SELECT current_database()")).scalar()
        rows = conn.execute(text("SELECT count(*) FROM timeseries")).scalar()

        print(f"database   : {target}")
        print(f"timeseries : {rows} rows")

        existing = None
        try:
            existing = conn.execute(
                text(f"SELECT marker FROM {CANARY_TABLE} LIMIT 1")
            ).scalar()
        except Exception:
            pass
        print(f"canary     : {existing!r}")

        if args.show:
            return 0
        if existing == CANARY_MARKER:
            print("already marked disposable; nothing to do")
            return 0

        print()
        print(f"About to mark {target!r} ({rows} rows) as DISPOSABLE.")
        print("A test suite is then free to truncate it. Say so explicitly:")
        typed = input("type the database name to confirm: ").strip()
        if typed != target:
            print("names do not match - aborted, nothing written")
            return 1

        conn.execute(text(f"CREATE TABLE IF NOT EXISTS {CANARY_TABLE} "
                          "(marker varchar(64) primary key)"))
        conn.execute(text(f"DELETE FROM {CANARY_TABLE}"))
        conn.execute(text(f"INSERT INTO {CANARY_TABLE} (marker) VALUES (:m)"),
                     {"m": CANARY_MARKER})
        conn.commit()
        print(f"marked: {CANARY_TABLE}.marker = {CANARY_MARKER}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
