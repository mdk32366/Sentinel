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
- **CI discovers every test module.** `python -m unittest discover -t . -s
  tests -p "test_*.py"` — 19 modules, 159 tests. `F-0006` recorded the
  previous state, a hand-maintained list that ran three of five and left two
  outside the gate reading as coverage. The `-t .` is load-bearing: without
  it discovery imports the test modules as top-level names, `tests/__init__.py`
  never runs, and the Step 12 database guard is never armed.
- CI also runs the frontend gate before the Python one: `npm run lint`,
  `npm test` (211 tests), then a build into `api/static/`.
- `fly.toml` declares **no `[mounts]`**. `data/` lives inside the container
  image, so anything written there at runtime does not survive a deploy, and
  anything not committed to git is absent from the image entirely.
- The Dockerfile has a **Node stage** (`FROM node:22-slim AS ui`) that runs
  `npm ci && npm run build`, and `COPY --from=ui /ui/dist/ /app/api/static/`
  lands it where `main.py` mounts it. `api/static/` is no longer committed, so
  shipping a stale bundle is impossible rather than merely detectable.
  `F-0027` records what this replaced.

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

## Frontend structure

`ORDER-03` Part F, completed over `D-0054` and `D-0055`. `App.jsx` was 2,398
lines with no tests; it is now **166** and the tree is:

```
ui/src/
  App.jsx              shell: which tab is open, what is selected
  lib/                 pure functions, unit-tested, no React
    api.js             the ONLY module that knows the base URL (F-0052)
    series.js          pivotByDate, seriesByCode, priorObservation
    usaSeries.js       byMetric, yearAgo, yoyPercent, yoySeries
    countrySeries.js   ticSeries, goldSeries, reservesSeries, momChange
    fiscal.js          the breaking-point arithmetic and its constants (A-0012)
    format.js          formatValue, tierColor, spreadBasisPoints
    yieldSeries.js     the date-keyed yield join (F-0007)
    rateScenarios.js   the four modelled rate paths
    constants.js       METRICS, TABS, RANGES, the FRED code maps
  hooks/               everything that talks to the API
    useApiResource     one JSON resource, with reload() (F-0063)
    useAsyncAction     a keyed write, per-key progress and outcome
    useMarketSeries    the ticker's latest and ~30d-prior values
    useChartSeries     the MARKETS chart rows (F-0065)
    useCountryDetail   the four requests behind the country panel
    useCountryNarrative  the analyst brief for one country
    useUSASeries       every USA series for the selected window
  pages/               one per tab, nine of them
  components/          shared presentation
    country/           the country panel's pieces
    usa/               the USA dashboard's pieces
```

**The invariant.** No page and no component calls `apiFetch`, reaches for
`window.fetch`, or spells an absolute API host. `ui/src/architecture.test.js`
enforces all three — the first two because `F-0063` was one defect in five
hand-copied fetch blocks and was fixable in one place only because there was
one place; the third because `F-0052` was a base URL that resolved only when
the app was served from localhost.

**Test shape.** 211 frontend tests in three layers: `lib/` and `hooks/` unit
tests, component render tests asserting the claims each component makes about
its numbers, and `pages.dom.test.jsx` mounting every tab with `fetch` stubbed.
The last layer is deliberately shallow — it proves a tab mounts, which is the
property a refactor threatens, and it caught `F-0069`.

**What is not covered.** Nothing asserts that the HOLDINGS table sorts
correctly or that a COMPOSITE tier is right. The scorers behind those numbers
are Python and are covered there; the join between the two is not covered
anywhere.
