# Architecture — Sentinel

> What am I looking at? Created 2026-09-26 to satisfy Day-One Step 8. Only what
> has been verified against the running system is recorded here. Where something
> has not been established, it says so rather than guessing.

## What Sentinel is

A FastAPI application that ingests sovereign macro data — US Treasury yields,
oil, the dollar index, TIC holdings by country, central bank gold reserves and
gold spot, CDS spreads, money supply — and scores countries for sovereign
stress. A React single-page UI is served from the same origin.

## Deployment

- Fly.io app `sentinel-holy-rain-4562`, region `sjc`, 1 shared CPU / 1 GB.
- Deploy on merge to `master` via `.github/workflows/fly-deploy.yml`. The
  `deploy` job carries `needs: test`, so a failing suite blocks the deploy.
- **CI runs three of the five test modules** — `test_frontend_auth`,
  `test_lifespan_cold_start`, `test_cds_coverage`. `test_dgs30_d0016` and
  `test_gold_reserve_changes` are never invoked by the gate. See `F-0006`.
- `fly.toml` declares **no `[mounts]`**. `data/` lives inside the container
  image, so anything written there at runtime does not survive a deploy, and
  anything not committed to git is absent from the image entirely.
- There is **no Node build stage** in the Dockerfile. `api/static/` holds the
  committed bundle and is what production serves, so a change to `ui/src/` not
  followed by `npm run build` and a copy into `api/static/` ships a stale UI
  with no signal. See `F-0027`.

### Platform secrets

Verified present and `Deployed` on 2026-09-26: `FRED_API_KEY`,
`ANTHROPIC_API_KEY`, `AUTH_PASSWORD`, `AUTH_USERNAME`, `DATABASE_URL`.

`GROK_API_KEY` is **not set**. `/api/analyze/country` therefore returns 503 in
production regardless of code. Together with `F-0033`, the analyst brief has
never produced output in production.

`AUTH_PASSWORD` is load-bearing since `F-0009`: `config.py` has no default, so
the application refuses to start without it.

## Local development database

`127.0.0.1:5432/treasury_monitor` is **PostgreSQL 18.3 on x86_64-windows**, a
native Windows install. It is *not* the `docker-compose.yaml` container
(`postgres:15`, a Linux image) and *not* a Fly tunnel (Fly runs Linux). See
`F-0012`.

**This identification is not a guard.** The positive-identity check required by
Day-One Step 12 does not exist. See `A-0006` and `F-0008`.

## Data file locations

Every pipeline resolves data paths through `pipelines/paths.py`:

- `REPO_ROOT` — the repository root, from `parents[1]` of that module
- `DATA_DIR` — `REPO_ROOT / "data"`

No module computes its own root. Three of them used to, one resolved a directory
too shallow, and the result was three months of silently stale gold prices
(`D-0025`, `F-0004`).

Files read at runtime, and therefore required in the image:

| Path | Read by |
|---|---|
| `data/gold_prices.csv` | `gold_price_import.py` |
| `data/gold_reserves.csv` | `gold_reserves.py` / `gold_fetcher.py` |
| `data/money_supply.json` | `money_supply_fetcher.py` |
| `data/incoming/Changes_latest_as_of_Aug2026_IFS.xlsx` | `gold_reserve_changes.py` |

`.dockerignore` deliberately does **not** exclude `data/incoming/` for this
reason.

## Running the Python suite locally

`api/static/` is **generated**, not committed (`D-0049`). `main.py` mounts it
with `StaticFiles` and raises if it is missing, which is correct — an app that
cannot serve its interface should not start quietly — but it means a fresh
clone must build the UI once before the Python tests will import:

```
npm ci --prefix ui
npm run build --prefix ui
mkdir -p api/static && cp -r ui/dist/. api/static/
```

CI does exactly this before running `unittest`, and the Dockerfile's Node stage
does the equivalent inside the image. If `tests.test_lifespan_cold_start` and
`tests.test_frontend_auth` fail to import with
`RuntimeError: Directory 'api/static' does not exist`, this is why.

## Auth boundary

`BasicAuthMiddleware` in `main.py` protects everything except the paths in
`OPEN_PATHS`, which contains `/api/health` alone, for the Docker and Fly probes.
`/api/health` therefore returns liveness only and takes no database session.
Pipeline detail lives on `/api/pipeline-status`, behind auth (`D-0035`,
`F-0019`).

## Schema changes are manual

Ruled 2026-09-29 (`D-0032`): alembic is removed. It was pinned and never
initialized, so nothing is lost — there were no migrations to abandon.

### How schema reaches the database

`Base.metadata.create_all()`, called by `init_db()`. It does exactly two
things worth knowing:

- **Creates missing tables.** Adding a model and deploying is enough; this is
  how `composite_snapshots` arrived (`D-0042`).
- **Ignores everything else.** A changed column type, a widened `varchar`, a
  new column on an existing table, a dropped column — `create_all` sees the
  table exists and returns. **No error, no warning, no log line.**

So additive *tables* are automatic and every other change is hand-written DDL.

### Detecting drift

`create_all()` will not tell you that `models.py` and the database disagree.
This will:

```
python tools/check_schema_drift.py                 # local
python tools/check_schema_drift.py --url "$URL"    # anywhere else
```

Exit code 1 on structural drift — a declared table or column the database does
not have, or the reverse. Type differences are printed as **advisory** and do
not fail: SQLAlchemy types and database introspection do not round-trip
cleanly, and `DATETIME` versus `TIMESTAMP` on every timestamp column is normal
rather than a problem.

**Run it against production during any session that touches schema.** It has
not been run there — `fly ssh console` is required and the Builder cannot
reach it. Until then `A-0010` stays assumed.

### Applying DDL to production

**`psql` is not installed in the image.** Use `python3` with `psycopg2` over
`fly ssh console`:

```
flyctl ssh console -a sentinel-holy-rain-4562
python3 - <<'SQL'
import os, psycopg2
conn = psycopg2.connect(os.environ["DATABASE_URL"])
conn.autocommit = False
cur = conn.cursor()
cur.execute("ALTER TABLE update_logs ALTER COLUMN error_message TYPE varchar(2000)")
conn.commit()
SQL
```

Before any DDL that is not purely additive, Principle 1 applies: say out loud
that a **completed** backup exists, how old it is phrased as exposure, and what
it does not cover. `D-0044` records that the recovery credential required by
Day-One Step 16 does not yet exist, and that is a blocker on destructive work.

### Where migration SQL lives

`docs/ddl/` — one file per change, named `YYYY-MM-DD-description.sql`, with a
comment naming the decision or finding that motivated it. A statement run
against production and not written down is a schema change nobody can
reconstruct.

### The known outstanding change

`update_logs.error_message` is `varchar(500)`. `A-0003` records that a
multi-series FRED failure can overflow it, which makes the `UpdateLog` insert
itself throw and loses the log row entirely. ORDER-01 B4 added truncation at
480 characters so the row survives; widening the column is the other half and
has not been done.

## Recovery access — UNANSWERED

KEEL Principle 1 requires the exact backup-list command for this cluster to be
recorded here, together with whether a recovery credential exists in a password
manager separate from any env file.

**Neither has been established for Sentinel.** This is Day-One Step 16 and it is
open. It is also a blocker on ORDER-01 C1, which performs a destructive `UPDATE`
against production `update_logs`.
