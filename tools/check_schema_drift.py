"""Compare models.py against a live database schema.

D-0032: alembic is dropped and DDL is manual. What alembic would have given us
is not migrations — we were not using them — but *detection*: some way to know
that `models.py` and the database disagree.

`Base.metadata.create_all()` creates missing tables and **silently ignores
changed columns** (`F-0022`). So a column whose type changed in `models.py`
never reaches the database and nothing says so. This is the check that says so.

    python tools/check_schema_drift.py              # against settings.database_url
    python tools/check_schema_drift.py --url URL    # against somewhere else

Exit code 1 on structural drift — a declared table or column the database does
not have, or the reverse.

Type differences are reported but do **not** fail: SQLAlchemy types and
database introspection do not round-trip cleanly across dialects, and a check
that cries wolf on `VARCHAR(500)` versus `String(500)` would be ignored within
a week.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, inspect  # noqa: E402

from database.models import Base  # noqa: E402

# Present in a disposable database by design and deliberately absent from
# models.py, so the application can never create its own disposability marker
# (D-0039). Not drift.
IGNORED_TABLES = frozenset({"canary"})


def declared_schema(metadata=None) -> dict:
    metadata = metadata if metadata is not None else Base.metadata
    return {
        name: {c.name: str(c.type).upper() for c in table.columns}
        for name, table in metadata.tables.items()
    }


def live_schema(inspector) -> dict:
    return {
        name: {c["name"]: str(c["type"]).upper() for c in inspector.get_columns(name)}
        for name in inspector.get_table_names()
    }


def diff_schema(declared: dict, live: dict, ignored=IGNORED_TABLES) -> dict:
    """Pure comparison, so it can be tested without a database."""
    declared_names = set(declared) - set(ignored)
    live_names = set(live) - set(ignored)

    result = {
        "missing_tables": sorted(declared_names - live_names),
        "extra_tables": sorted(live_names - declared_names),
        "missing_columns": {},
        "extra_columns": {},
        "type_differences": {},
    }

    for table in sorted(declared_names & live_names):
        dcols, lcols = declared[table], live[table]
        missing = sorted(set(dcols) - set(lcols))
        extra = sorted(set(lcols) - set(dcols))
        if missing:
            result["missing_columns"][table] = missing
        if extra:
            result["extra_columns"][table] = extra
        differences = [
            (col, dcols[col], lcols[col])
            for col in sorted(set(dcols) & set(lcols))
            if dcols[col] != lcols[col]
        ]
        if differences:
            result["type_differences"][table] = differences

    return result


def has_structural_drift(diff: dict) -> bool:
    """Type differences are advisory; missing or extra structure is not."""
    return bool(
        diff["missing_tables"]
        or diff["extra_tables"]
        or diff["missing_columns"]
        or diff["extra_columns"]
    )


def render(diff: dict) -> str:
    lines = []
    if diff["missing_tables"]:
        lines.append(f"DECLARED BUT ABSENT (tables): {', '.join(diff['missing_tables'])}")
    if diff["extra_tables"]:
        lines.append(f"PRESENT BUT UNDECLARED (tables): {', '.join(diff['extra_tables'])}")
    for table, cols in diff["missing_columns"].items():
        lines.append(f"DECLARED BUT ABSENT  {table}: {', '.join(cols)}")
    for table, cols in diff["extra_columns"].items():
        lines.append(f"PRESENT BUT UNDECLARED  {table}: {', '.join(cols)}")
    for table, items in diff["type_differences"].items():
        for col, declared, live in items:
            lines.append(f"type differs (advisory)  {table}.{col}: models={declared} db={live}")
    return "\n".join(f"  {line}" for line in lines) if lines else "  no drift"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", help="database URL (default: settings.database_url)")
    args = parser.parse_args()

    if args.url:
        url = args.url
    else:
        from config import settings

        url = settings.database_url

    engine = create_engine(url)
    with engine.connect() as conn:
        target = conn.exec_driver_sql("SELECT current_database()").scalar() \
            if engine.dialect.name == "postgresql" else url
    diff = diff_schema(declared_schema(), live_schema(inspect(engine)))

    print(f"schema drift check: {target}")
    print(render(diff))

    if has_structural_drift(diff):
        print("\nSTRUCTURAL DRIFT. create_all() does not fix this - it creates")
        print("missing tables and ignores changed columns. Write the DDL by hand;")
        print("see docs/architecture.md, 'Schema changes are manual'.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
