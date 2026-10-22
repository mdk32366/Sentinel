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
- **Every application startup runs the FRED pipeline.** `main.py`'s lifespan
  calls `start_scheduler()`, which queues a one-shot FRED job (`D-0019`), so a
  deploy re-fetches five years of thirty-nine series — about two minutes and
  ~14,700 row updates. A newly added metric therefore backfills itself on
  deploy and needs no manual step; running one anyway is what produced the
  1,174 duplicates in `F-0073`.
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

`GROK_API_KEY` is **not set**, and since `D-0069` nothing reads it. The
analyst brief calls Anthropic, using the `ANTHROPIC_API_KEY` that has been
deployed all along. Before that it required the Grok key and returned 503 for
every request - together with `F-0033`, the brief had never produced output
in production.

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
    constants.js       METRICS, TABS, RANGES, the FRED code maps,
                       FOREIGN_BOND_METRICS and the two spread strips (D-0111)
  hooks/               everything that talks to the API
    useApiResource     one JSON resource, with reload() (F-0063)
    useAsyncAction     a keyed write, per-key progress and outcome
    useMarketSeries    the ticker's latest and ~30d-prior values;
                       useSeries(codes) is the same for any code list (D-0111)
    useChartSeries     the MARKETS chart rows (F-0065)
    useCountryDetail   the four requests behind the country panel
    useCountryNarrative  the analyst brief for one country
    useUSASeries       every USA series for the selected window
  pages/               one per tab, plus MarketsTab.jsx: the MARKETS layout as
                       a component, rendered by MARKETS and FOREIGN-BONDS (D-0111)
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

## Foreign Bonds (D-0111)

The FOREIGN-BONDS tab (`#/foreign-bonds`, after MARKETS) shows government
bond yields for Germany, the UK, Japan and France at 2/5/7/10/30Y (France
since D-0112). It is display only: nothing here feeds a score.

**Fetchers.** One module per source in `pipelines/`. Each has
`fetch_*() -> bytes`, a pure `parse_*(bytes) -> [(code, date, Decimal)]`
and `run_*(db, backfill=False) -> dict`:

| Module | UpdateLog name | Source | Codes | Cron (UTC, weekdays) | Stale after |
|---|---|---|---|---|---|
| `bundesbank_yields.py` | `Bundesbank_Yields` | Bundesbank SDMX CSV, Svensson fitted | `FB_DE_{02,05,07,10,30}Y` | 18:00 | 4 d |
| `boe_yields.py` | `BoE_Yields` | BoE GLC nominal spot, sheet `4. spot curve` | `FB_GB_…` | 18:30 | 5 d |
| `mof_jgb.py` | `MOF_JGB` | MOF `jgbcm.csv`, Shift-JIS, era dates | `FB_JP_…` | 10:00 | 7 d |
| `bdf_tec.py` (D-0112) | `BdF_TEC` | Banque de France Webstat `observations/exports/csv`, TEC constant-maturity, `Authorization: Apikey $WEBSTAT_API_KEY` | `FB_FR_…` | 10:00 | 4 d |

The shared plumbing is in `foreign_bond_common.py`. Transport: timeout
30 s, 3 attempts, back-off 4 s x 2^(n-1), no retry on a 4xx except 429, and
`fetch_failure` classifies every error (D-0094). Writes go through
`fred_fetcher.upsert_observations` (F-0073), and there is one UpdateLog row
per run. The metrics sit in category `foreign_bond` with `country_id`
NULL. No migration.

**Fail-closed.** A source writes all its rows in one transaction or none.
`SchemaDrift` (missing column, bad date, value outside [-2, 15] %) and a
0-row parse both mean `failed`. A Bundesbank 200 with only a header is
retried, then `failed` (F-0117), and so is a Webstat one. A Webstat 404 or
401 is a rejected key: `failed` at once, naming `WEBSTAT_API_KEY` (F-0118).
With no `WEBSTAT_API_KEY` set, `BdF_TEC` logs a warning and returns
`skipped`, with no request and no write. The first run against an empty
series backfills five years from the archives (F-0116), or, for Webstat,
from a `time_period_start>=date'…'` filter.

**Freshness.** `freshness_watchdog.CHECKS` has `foreign_bonds_de`, `_gb`,
`_jp` and `_fr` (patterns `FB\_DE\_%` etc.). FOREIGN-BONDS no longer reads
`sovereign_yields` (D-0112 amendment 1).

**Country cards (D-0113).** `CountryDetail` for DEU/GBR/JPN/FRA makes one more
request, `useSeries(fbCardCodes(iso))` (empty, so no request, elsewhere), and
`countryBond()` in `constants.js` turns it into the card's 10Y (daily, or the
monthly fallback badged MONTHLY past `FB_MAX_AGE_DAYS`), the curve row and the
2s10s / 10s30s slopes. `country/CountryBondCurve.jsx` renders the row and the
chart through `pages/MarketsChartPanel.jsx`, the panel MarketsTab also uses,
with its own `useChartView` so the card's state is per country and never
MARKETS'. Display only.

**Manual trigger and startup fill.** `POST /api/fetch/foreign-bonds/{source}`
(`api/routes.py`) runs one source now through the same wrapper the cron uses,
`scheduler._scheduled_foreign_bonds`, and answers `{status, inserted,
updated, latest_date}`. A failed run answers `failed` with zero counts, never
a 500. `?backfill=1` forces the five-year read; without it, the backfill
happens only when the series is empty. The sources are the keys of
`scheduler.FOREIGN_BOND_JOBS` (`bundesbank`, `boe`, `mof`, `bdf`): adding a source is
one line there, and an unknown name is a 404. The route sits behind Basic
Auth, and the proof cookie is read-only (403). ADMIN has one button per
source. `scheduled_startup_fetches` runs every `FOREIGN_BOND_JOBS` entry after
FRED/TIC/gold/stress, so a redeploy fills the tab without waiting for the
weekday crons.

**Freshness.** `freshness_watchdog.CHECKS` has `foreign_bonds_de`, `_gb`,
`_jp` and `_fr` (patterns `FB\_DE\_%` etc.). France's daily TEC comes from
the Banque de France Webstat v2.1 API as the `bdf` `FOREIGN_BOND_JOBS` entry
(D-0112): it needs `WEBSTAT_API_KEY`, logs and skips when the key is missing,
and `_fr` goes stale after 4 days. The monthly OECD France 10Y
(`IRLTLT01FRM156N`) is off this tab (D-0112 amendment 1); it is still fetched
by FRED and scored in composite D4.

**UI.** `pages/ForeignBondsTab.jsx` renders `pages/MarketsTab.jsx` with
`foreignBondCells()` in a 5-column grid (20 daily cells; with no daily French
row the FR cells show "—", with no monthly stand-in), DataConfidence on the
four `foreign_bonds_*` sources, the
`foreignBondSpreads` strip, and a footer ending
"Source: Banque de France, updated <date>" (`bdfAttribution`). A spread whose leg is stale is hidden. Data
comes from `useSeries(FOREIGN_BOND_CODES)` through the existing
`/api/timeseries`, with no new endpoint. MARKETS renders through the same
component and is byte-identical to master `be64218`
(`marketsDefault.ac1.dom.test.jsx`).

## Composite dimension 4 on the daily curves (D-0114)

`pipelines/composite_stress.get_dim4_fb` scores dimension 4 for DEU, GBR,
JPN and FRA only. It reads `FB_xx_10Y` (`country_id` NULL) while the series is
inside its `freshness_watchdog.CHECKS` window, falls back to `IRLTLT`, and for
France adds the same-date OAT-Bund percentile term. Every other country still
goes through `get_sovereign_spread`, scoring 0. The freshness limits have one
source (the watchdog), which the scorer, the D-0113 cards and the watchdog all
read. `scripts/d0114_shadow.py` computes the old and new scores side by side
on any `DATABASE_URL`, and writes nothing.


## Foreign Bonds batch 2a (D-0115)

Six more keyless fetchers write `FB_` rows through
`pipelines/foreign_bond_common` (`reject_html`, `make_metrics`):
`boc_valet`, `riksbank_yields`, `rba_f2`, `norges_yields`, `bde_ti13`,
`ecb_yc`. Each is a scheduler job and a manual-trigger source and has a
`freshness_watchdog.CHECKS` entry. The cards read CA/SE/AU/NO/ES through
`countryBond`, as `D-0113` does. The euro-area curves feed only
`components/foreignBonds/EaBenchmarkPanel.jsx` on FOREIGN-BONDS. No scorer
reads any batch 2a code.
