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

## Auth boundary

`BasicAuthMiddleware` in `main.py` protects everything except the paths in
`OPEN_PATHS`, which contains `/api/health` alone, for the Docker and Fly probes.
`/api/health` therefore returns liveness only and takes no database session.
Pipeline detail lives on `/api/pipeline-status`, behind auth (`D-0035`,
`F-0019`).

## Schema management

`alembic==1.12.1` is pinned in `requirements.txt` and has **never been
initialized** — there is no `alembic.ini` and no `versions/`. Schema comes from
`Base.metadata.create_all()`, which creates missing tables and silently ignores
changed columns. A column type change requires hand-written DDL against
production. See `F-0022`; `D-0032` is the open ruling on whether to initialize
Alembic or drop it and document manual DDL.

## Recovery access — UNANSWERED

KEEL Principle 1 requires the exact backup-list command for this cluster to be
recorded here, together with whether a recovery credential exists in a password
manager separate from any env file.

**Neither has been established for Sentinel.** This is Day-One Step 16 and it is
open. It is also a blocker on ORDER-01 C1, which performs a destructive `UPDATE`
against production `update_logs`.
