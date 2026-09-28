# Findings — Sentinel

> How do we know? Every claim names the artefact it came from and carries its
> sample size. If you cannot name the artefact, you are recording a belief.

---

### F-0001 — Treasury yields are current to their upstream source; the pipeline has zero lag

**Claim.** On 2026-09-26 the database held `DGS10` through 2026-09-24 and FRED's
API also ended 2026-09-24. The apparent three-day staleness was FRED's
one-business-day publication lag, observed on a Saturday.

**Artifact.** FRED API call for `DGS10` from `observation_start=2026-09-22`
returned three observations: 09-22 `4.96`, 09-23 `5.11`, 09-24 `5.18`. Database
`MAX(date)` returned 2026-09-24 for all four `DGS` series.

**Sample size.** One query, one series, one moment. The one-day lag is inferred
from a single observation plus FRED's stated next-release date, not measured.

### F-0002 — The scheduler fires reliably; the misfire hypothesis was wrong

**Claim.** Ten consecutive nightly FRED runs started within 250ms of 02:00 UTC,
each completing in 2–3 minutes. No misfires, no overruns, no skips.

**Artifact.** `update_logs` rows 624–683, `started_at` / `completed_at`.

**Note against the Planner.** The leading hypothesis was a silent APScheduler
misfire, argued from the genuine absence of `misfire_grace_time`. Fluent, and
wrong. Reading the code produced a plausible mechanism; reading the logs
produced the answer.

### F-0003 — FRED returns intermittent 502s affecting one random series per run

**Claim.** Five of ten runs returned `partial`, each losing exactly one series
to a 502. Different series each time: DFII10, IRLTLT01AUM156N, DGS10, DGS2,
DGS30. Self-healing via the 1825-day window.

**Artifact.** Same rows. Blast radius confirmed arithmetically: successful runs
update ~11,700 rows; runs losing a daily series ~10,450 (delta ~1,250 ≈ five
years of business days); the run losing a monthly series updated 11,628 (delta
~76 ≈ five years of months).

**Sample size.** 10 runs. A 50% partial rate measured over ten nights, not
established as steady state.

### F-0004 — The gold price importer reads a shadow copy; the data has been on disk since August

**Claim.** `pipelines/experimental/gold_price_import.py:23` computes
`Path(__file__).parent.parent / "data" / "gold_prices.csv"`. From
`pipelines/experimental/` that resolves to `pipelines/data/`, not the repository
root. The module was written one directory shallower and the path followed it
when it moved.

**Artifact.** Snapshot `378352f`: `data/gold_prices.csv` ends `8/31/2026`;
`pipelines/data/gold_prices.csv` ends `7/31/2026`;
`data/gold_prices.csv.bak-2026-08-31` ends `7/31/2026`; database
`GOLD_SPOT_USD` latest `2026-07-01`. The importer applies `date.replace(day=1)`,
so `7/31/2026` stores as `2026-07-01` — the database is exactly in sync with the
file it actually reads.

**Consequence, direction stated.** Divergence is scored on selling gold into a
*rising* price. A frozen price understates rising-price detection, so the bias
is toward **under-scoring** divergence: countries look calmer than they are.
The magnitude is unknown until the re-score in ORDER-02 A7.

**Why it survived.** Nothing errored. The `partial` branch never fired because
the file it looked for was present. Right shape, right provenance, right date,
plausible number — Principle 11 exactly.

### F-0005 — `pipelines/data/` is a second canonical copy created to satisfy a broken path

**Claim.** `pipelines/data/` is untracked and holds `gold_prices.csv` and
`money_supply.json`. It exists because the miscomputed path needed something to
find. From its creation, the human updated one tree and the pipeline read
another.

**Artifact.** `git status` shows `?? pipelines/data/`. Both files are present
and readable.

**Latent, not yet active, in money supply.** `money_supply_fetcher.py:27` has
the identical defect, but the two JSON copies are currently identical — 1,380
rows, 1996–2025. It diverges the first time the root copy is refreshed.

### F-0006 — Two tests exist that cannot block a deploy

**Claim.** `fly-deploy.yml` runs `test_frontend_auth`,
`test_lifespan_cold_start` and `test_cds_coverage`. `test_dgs30_d0016` and
`test_gold_reserve_changes` are named in neither the workflow nor any other
runner.

**Artifact.** `.github/workflows/fly-deploy.yml`, the `Run frontend auth,
cold-start, and CDS coverage tests` step, against `ls tests/`.

**Why it matters.** A red X nobody must obey is decoration. A test nobody runs
is a step past that — it looks like coverage and provides none. Both tests cite
decision numbers, which makes them read as deliberate.

### F-0007 — `App.jsx` plots Fed Funds against the wrong dates

**Claim.** `yieldData` (~line 806) zips series by array index, not date.
`FEDFUNDS` is monthly (~60 points over five years) mapped onto the daily
`DGS10` axis (~1,250 points), so the line covers ~5% of the chart against
incorrect dates and is null thereafter. `DGS2` drifts wherever the two series
have differing missing days.

**Artifact.** `ui/src/App.jsx` lines ~806–811 at `378352f`.

**Status.** Open, deferred to the V2 frontend decomposition. Adding a 7Y line
would inherit it.

### F-0008 — The test suite poses no truncation risk today, and the guard that would keep it that way does not exist

**Claim.** The three DB-touching tests each build their own
`sqlite:///:memory:` engine. No test calls `drop_all` or truncates. There is
no positive-identity guard anywhere in `tests/`, and no `conftest.py`.

**Artifact.** `create_engine("sqlite:///:memory:")` at
`test_cds_coverage.py:26`, `test_dgs30_d0016.py:23`,
`test_gold_reserve_changes.py:195`. `grep -riE "canary|disposable|refuse"
tests/` returns nothing.

**The exposure.** `database/connection.py` instantiates a pooled engine against
`settings.database_url` at import time, and `test_frontend_auth` imports
`main`. Nothing writes through it today. One fixture that does, and the
configuration is identical to the one that truncated production twice.

### F-0009 — `config.py` carries a working password as a source default

**Claim.** `config.py:20` carried a hard-coded `auth_password` default in a
public repository. A missing `AUTH_PASSWORD` secret did not fail startup; it
fell back to that published credential.

**Artifact.** `config.py:20` at `378352f`. **The value is deliberately not
reproduced here** — see the amendment below for why.

**Amendment 2026-09-28 — this entry published the credential it was reporting.**
As first written, the claim quoted the literal default string. `docs/findings.md`
is tracked and this repository is public (`D-0026` is unruled, so it has not
gone private), which means the register republished the exact secret that
removing it from `config.py` was meant to retire. The quote has been redacted,
but **redaction now does not unpublish it**: the register was committed in PR
#11 and merged to `master`, so the string is in git history and in every clone
and fork taken since 2026-09-26.

**Consequence.** If the Fly `AUTH_PASSWORD` secret still holds that value, the
dashboard password is public and has been for two days. Its digest is visible
via `flyctl secrets list` but the value is not, so this cannot be settled by
reading — it has to be rotated. `AUTH_PASSWORD` joins the rotation list in
ORDER-01 C1 alongside `FRED_API_KEY`, `ANTHROPIC_API_KEY` and `GROK_API_KEY`,
and it should be treated as compromised rather than merely suspect.

**The general lesson.** A findings register names artefacts, and an artefact
that *is* a secret cannot be named by value. `config.py:20 at 378352f` locates
it exactly and reveals nothing. Principle 4 says never in a file, never
committed, never pasted — and a document whose whole purpose is to be
committed is the last place the exception should have been made.

### F-0010 — The FRED API key is in production logs and served over HTTP

**Claim.** `fetch_fred_series` passes the key as a query parameter;
`raise_for_status()` embeds the URL in the exception; the text is written to
`update_logs.error_message`; `/api/pipeline-logs` serves it.

**Artifact.** Five of ten sampled `update_logs` rows contain `api_key=` and the
live key, retrieved over HTTP from the running application.
`treasury_monitor.log` holds it eight more times.

### F-0011 — A planning claim of absence was made from a stale copy and was wrong

**Claim.** The Planner stated neither `DGS7` nor `DGS30` was tracked. `DGS30`
was live, from decision D-0016. The claim came from a project-attached copy of
`fred_fetcher.py` predating the deployed version.

**Artifact.** `SELECT code FROM metrics WHERE code LIKE 'DGS%'` returned DGS2,
DGS5, DGS10, DGS30. Independently corroborated by a sentence in the repository
README naming DGS30 as pulled and displayed.

**Why recorded.** A Step C6 false absence, produced in the session that wrote
the orders acting on it. The general defect — the Planner's copy behind the
working copy — is the one the V2 refactoring plan opened with on 2026-06-30,
unresolved until the snapshot on 2026-09-26.

---

### F-0017 — `.dockerignore` excludes five patterns; `.env` is not one of them

**Claim.** `.dockerignore` contains exactly `fly.toml`, `.git/`, `__pycache__/`,
`.envrc`, `.venv/`. The Dockerfile does `COPY . .`. Any `.env` present at build
time is baked into the production image. `node_modules/`, `venv/` (the
convention actually used; only `.venv/` is listed), `ui/`, `data/incoming/` and
`*.log` are likewise included in the build context.

**Artifact.** `.dockerignore` and `Dockerfile` at `378352f`.

**Status.** UNVERIFIED IN PRODUCTION. `cat /app/.env` in a running container
settles it — see `A-0007`. Recorded as a finding about the configuration, which
is certain; the consequence is an assumption until checked.

**Second consequence.** An unbounded build context is the twenty-gigabyte
seven-hour rebuild already recorded in KEEL Principle 3's blood line.
`node_modules/` has never been excluded.

### F-0018 — `/api/analyze/country` forwards a client-supplied prompt with the server's key

**Claim.** `routes.py:500` reads `payload["prompt"]` and posts it verbatim to
`https://api.x.ai/v1/chat/completions` with `settings.grok_api_key`,
`max_tokens: 750`, no rate limit and no content constraint. The prompt is
assembled in `App.jsx`, so the server never sees what it is paying for until it
has paid.

**Artifact.** `api/routes.py:500–548`.

**Second defect, same handler.** `db: Session = Depends(get_db)` is injected
and never used, while the handler awaits an HTTP call with `timeout=75.0`.
`connection.py` sets `pool_size=10`, so ten concurrent briefs exhaust the pool
and block every other endpoint.

**Third, minor.** The docstring says "using Grok (replaces Claude)"; the
project's architecture notes still describe this as a Claude integration.

### F-0019 — `/api/health` is unauthenticated

**Claim.** `main.py:64` declares `OPEN_PATHS = {"/api/health"}` and
`BasicAuthMiddleware.dispatch` returns early for it. Every other path,
including all of `/api/*` and the SPA, requires Basic auth.

**Artifact.** `main.py:64–77`.

**Why recorded.** The exemption is correct — the probes need it. It is recorded
because it is invisible from `routes.py`, where `/health` looks like every
other endpoint, and because ORDER-01 B6 was written against that appearance and
would have published freshness data on it. See `D-0033`.

**Correction to an earlier finding.** `F-0010` stated the FRED key in
`update_logs` was "served by `/api/pipeline-logs`". Accurate, but that endpoint
*is* behind auth. The exposure is to anyone holding the shared password — which,
given `F-0009`, may be a published default. Narrower than first stated, not
closed.

### F-0020 — `pipelines/experimental/` holds 1,938 lines of production code, imported inside function bodies

**Claim.** Five modules totalling 1,938 lines — 21% of the project's Python —
live in a directory named `experimental` and are load-bearing:
`composite_stress.py` (769, serves `/stress/composite`), `gold_fetcher.py`
(462, serves `/holdings/cross-asset-stress` and is the real WGC importer),
`tic_fetcher.py` (406), `money_supply_fetcher.py` (142),
`gold_price_import.py` (159).

**Artifact.** `wc -l pipelines/experimental/*.py`; imports at
`api/routes.py:249`, `api/routes.py:622`, `pipelines/gold_reserves.py:54` —
all **inside function bodies**, not at module level.

**Why it matters beyond naming.** Function-level imports hide the dependency
from any static read of the file header, which is how the directory stayed
"experimental" while becoming production. The extra directory level is also the
direct cause of `F-0004`.

### F-0021 — Root `scheduler.py` is dead code

**Claim.** `./scheduler.py` (120 lines) is imported by nothing. `main.py`,
`api/routes.py`, `tests/test_cds_coverage.py` and
`tests/test_lifespan_cold_start.py` all import `pipelines.scheduler` (171
lines).

**Artifact.** `grep -rn "from scheduler import\|^import scheduler"
--include=*.py .` returns nothing.

**Consequence already realised.** This is the copy the Planner reviewed across
three sessions, producing the misfire hypothesis in `F-0002`. A second
canonical copy cost real diagnostic time before anyone noticed it was dead.

### F-0022 — Alembic is pinned and has never been initialized

**Claim.** `requirements.txt` pins `alembic==1.12.1`. There is no
`alembic.ini` and no `versions/` directory anywhere in the tree. Schema is
created by `Base.metadata.create_all()` in `database/connection.py:25`, which
creates missing tables and silently ignores changed columns.

**Artifact.** `requirements.txt`; `find . -name alembic.ini -o -name versions`
returns nothing.

**Concrete consequence.** The `error_message varchar(500)` overflow behind
`A-0003` cannot be fixed by editing `models.py`. It requires hand-written DDL
against production, and nothing in the system says so.

### F-0023 — The composite scorer issues roughly 400 queries per HTTP request

**Claim.** `compute_composite_stress` loops
`for country in db.query(Country).filter(Country.iso_code != "USA").all()` at
`composite_stress.py:441`. Inside the loop: TIC history (445), gold history
(486), M2 row (521), plus each dimension helper re-resolving its metric by code
— `db.query(Metric).filter_by(code=...).first()` at 127, 216, 279, 739 — once
per country per dimension. `/stress/composite` recomputes on every tab click
with no caching.

**Artifact.** `grep -c "db.query" pipelines/experimental/composite_stress.py`
returns 22; the loop at line 441.

**Sample size.** Query count estimated from code structure and country count,
**not measured**. ORDER-03 D2 requires the measured before/after.

### F-0024 — Six of twenty-four endpoints declare a response model

**Claim.** `api/routes.py` defines 24 routes; 6 carry `response_model`.
`api/schemas.py` is 92 lines, mostly unused. The remaining 18 assemble raw
dicts inline.

**Artifact.** `grep -c "@router" api/routes.py` → 24;
`grep -c "response_model" api/routes.py` → 6.

**Consequence.** `/docs` documents almost nothing, and `App.jsx` is the only
specification of the API contract. A field rename produces an empty tile, not
an error.

### F-0025 — `App.jsx` grew 15% while flagged as the top structural priority

**Claim.** The June 2026 V2 plan recorded `App.jsx` at 2,248 lines and named
decomposing it the highest-leverage structural fix. At `378352f` it is **2,583
lines**, with 23 `fetch()` calls, 53 `useState`, 14 `useEffect`, and 15
components in one file.

**Artifact.** `wc -l ui/src/App.jsx`; the V2 plan, section 2.3.

**Why recorded as a finding rather than a task.** The number is evidence about
sequencing, not about the file. A structural fix that is scheduled and not done
gets more expensive at a measurable rate. See `D-0028`.

### F-0026 — Deployed Python version does not match the recorded decision

**Claim.** `Dockerfile` uses `python:3.11-slim`; `.github/workflows/fly-deploy.yml`
sets `python-version: '3.11'`. The project's recorded decision chose Python
3.13 with 3.13-pinned wheels.

**Artifact.** `Dockerfile:1`, `fly-deploy.yml` setup-python step.

**Status.** Nothing is broken. The environment the tests pass in is not the one
the decision describes, which means one of the two is wrong and nobody knows
which.

### F-0027 — No frontend build stage; the bundle is committed

**Claim.** The Dockerfile has a Python builder stage and no Node stage.
`api/static/index.html` is committed (dated 2026-09-01) and reaches the image
via `COPY . .`. `.gitignore` ignores a bare `dist/` but not `api/static/`.

**Artifact.** `Dockerfile`; `ls api/static/`; `.gitignore:17`.

**Consequence.** A deploy that forgets `npm run build` ships a stale UI against
a new API with no signal of any kind. Flagged as Phase 0 in the June plan;
still open.

### F-0028 — The application writes an unbounded log file inside the container

**Claim.** `main.py:17` attaches `logging.FileHandler('treasury_monitor.log')`.
The file grows until the machine restarts, is never read, and is the file that
holds the FRED API key eight times.

**Artifact.** `main.py:12–19`; the snapshot exclusion note recording eight
occurrences of the key.

### F-0029 — CORS remains wildcard-plus-credentials

**Claim.** `main.py:57–60` sets `allow_origins=["*"]` with
`allow_credentials=True` — an invalid combination browsers reject for
credentialed requests. Flagged in the June plan, unchanged.

**Artifact.** `main.py:57–60`.

**Why it survived.** Everything is same-origin behind middleware, so the
invalid config has no observable effect — which is precisely why it will sit
there indefinitely.

---

### F-0012 — `127.0.0.1:5432` is a native Windows PostgreSQL, not the Docker container and not a tunnel

**Claim.** The local `DATABASE_URL` target is PostgreSQL 18.3 on
`x86_64-windows`, a separate database from production.

**Artifact.** `SELECT version()` returned `PostgreSQL 18.3 on x86_64-windows,
compiled by msvc-19.44.35`, 2026-09-26. `docker-compose.yaml` declares
`postgres:15`, a Linux image, so this is not that container; Fly runs Linux, so
it is not a tunnel to production. Row counts: timeseries 37,923 - metrics 79 -
countries 45 - update_logs 18. Production `update_logs` runs to id 683
(`F-0003`), so the two are demonstrably different databases.

**Sample size.** One query at one moment. This identifies the database; it is
**not** the positive-identity guard required by Step 12, which does not exist.
See `A-0006`.

**Note against the Planner.** The V2 order inferred "local Docker" from
`docker-compose.yaml` matching `.env`. The inference reached the right
conclusion — local, not production — by reading a file rather than the running
server, and the file it read describes a container that is not what is running.

### F-0013 — The freshness watchdog names four pipelines that do not exist, and its gold threshold fires on healthy data

**Claim.** In `freshness_watchdog.py` as delivered, four of ten `CHECKS` groups
reference `pipeline_name` values that no pipeline writes, so `_last_success`
can never resolve them. Separately, `gold_price` carries `max_age_days: 45`
against a series that is 56 days old when fully current.

**Artifact.** `CHECKS` expects `GoldPrice` / `TIC` / `Treasury` / `MoneySupply`
/ `CDS`. A `grep` over `pipelines/` and `SELECT DISTINCT pipeline_name FROM
update_logs` both return the same seven values: `Broad_Money_Growth`, `FRED`,
`Gold_Reserve_Changes`, `Gold_Reserves`, `Gold_Spot_Price`, `Stress_Score`,
`TIC_Holdings`. Age arithmetic:
2026-08-01 to 2026-09-26 is 56 days; to the next publication (~2026-10-05) is
65.

**Sample size.** All ten `CHECKS` groups inspected; all seven distinct
`pipeline_name` values in the database enumerated.

**Consequence.** Four sources would report permanently "never succeeded" and
gold would sit CRITICAL while entirely correct. A watchdog that is wrong about
40% of its inputs is decoration within a week — Principle 9.

**Correction, 2026-09-26.** This entry originally also claimed that *no*
pipeline writes a CDS log row. That was wrong. `pipelines/cds_fetcher.py:443`
writes `pipeline_name=CDS_PIPELINE_NAME`, and line 223 defines that constant as
`"CDS_MultiTenor"`. The claim came from a `grep` for `pipeline_name="..."` as a
string literal, which cannot see a name bound to a constant, and from a local
database where the CDS pipeline has simply never run. The headline stands - the
four names in `CHECKS` were wrong, `CDS` among them, because the real name is
`CDS_MultiTenor` - but the supporting claim of total absence was a false
absence produced by an incomplete method. Principle 8: the artefact was real
and what it implied was not.

**Status.** Closed by the revised `freshness_watchdog.py` issued 07:15, which
uses `Gold_Spot_Price`, `TIC_Holdings`, `Broad_Money_Growth`, `CDS_MultiTenor`
and `Gold_Reserve_Changes`, and raises the gold threshold from 45 to 75 days.
The module is still not in the tree.

### F-0014 — The documented gold refresh command has never done anything

**Claim.** `pipelines/experimental/gold_price_import.py` has no
`if __name__ == "__main__"` block, so `python -m
pipelines.experimental.gold_price_import` imports the module, runs no import,
and exits 0.

**Artifact.** `grep -n "__main__"` returns nothing; the command produced no
output and exit code 0 on 2026-09-26. The refresh had to be driven by calling
`run_gold_price_import(db)` directly.

**Why it matters.** This is a second, independent reason the gold price was
frozen. Even with the path defect in `F-0004` repaired, the refresh command
named in both ORDER-02 V1 and V2 would have silently done nothing — and
exiting zero is exactly what makes it invisible.

### F-0015 — No September gold data exists in any file on disk

**Claim.** ORDER-02 A5 cannot be satisfied. Its PROOF (`GOLD_SPOT_USD` latest
is `2026-09-01`) is unachievable from current sources.

**Artifact.** `..._Sep2026.xlsx`, sheet `Monthly_Avg`: 584 data rows, last row
`2026-08-31 = 4409.89`. The older `..._since_1978.xlsx`: 583 rows, last row
`2026-07-31 = 4073.92`. The workbook is named for its publication month, not
its last data month. WGC publishes month-end, so September will not exist until
early October.

**Sample size.** Both gold price workbooks on disk, all sheets enumerated.

### F-0016 — Measured blast radius of the three-month gold freeze: two countries understated by 33%, no tier changed

**Claim.** Re-scoring with July gold versus August gold changes two composite
scores and reassigns no country's tier.

**Artifact.** `compute_composite_stress(db)` run twice on 2026-09-26, the
"before" state produced by deleting the `2026-08-01` row inside an uncommitted
transaction and rolling it back. 29 countries scored. RUS 104.8 -> 139.7;
TUR 126.0 -> 168.0. Both x1.3333, consistent with the divergence multiplier
moving 1.5 -> 2.0. Both were already `crisis` and remained `crisis`.

**Sample size.** One scoring run per state, 29 countries, one date.

**Direction.** Confirms the prediction in `F-0004`: the freeze **understated**
divergence. Both affected countries looked calmer than the data supports. The
tier boundaries absorbed it this time, which is luck rather than a safety
property — the same 33% understatement at a different point in the
distribution moves a country between tiers.

### F-0033 — `/api/analyze/country` has never executed; `settings` was never imported

**Claim.** The endpoint `F-0018` describes as an open, funded LLM proxy could
not have been used as one. `api/routes.py` never imported `settings`, and the
handler's first statement is `if not settings.grok_api_key:`. Every call raised
`NameError` and returned 500 before reaching `api.x.ai`.

**Artifact.** `git show HEAD:api/routes.py | grep -n "settings\."` returns
exactly two hits, lines 507 and 531, both inside this handler. The same file's
import block contains no `from config import settings` and no wildcard import.
Reproduced 2026-09-26 against a `TestClient`: `NameError: name 'settings' is
not defined`, raised from `routes.py:634`.

**Sample size.** One handler, one reproduction, plus a full read of the import
block at `HEAD`.

**What this corrects.** `F-0018`'s mechanism is right and its severity is
wrong. Nobody could spend the Grok key through this endpoint, because the
endpoint was dead. It was a **latent** exposure: adding one import line would
have armed it silently, with no other change and no review of the handler.

**What it also resolves.** `D-0026` asks whether the AI analyst briefs are
persisted to the database, because that decides the go-private observable in
`A-0004`. They are not, and never have been — the handler returns its text to
the caller and writes nothing, and it has never produced text at all. The brief
feature has never worked in production.

**Status.** Closed by this session: the import was added and the handler
rewritten under `D-0031`. The endpoint now works *and* is constrained.

### F-0034 — `A-0009` holds: nothing consumes `/api/health` beyond liveness

**Claim.** `/api/health` was returning `database`, `scheduler`,
`last_fred_update`, `last_treasury_update` and `last_gold_update` to
unauthenticated callers, but no consumer read any of it.

**Artifact.** `grep -noE "health\??\.[a-z_]+" ui/src/App.jsx` returns a single
hit: `health.status` at line 1758. The two other mentions, at lines 2496-2497,
are ADMIN checklist *strings* instructing a human to check the endpoint, not
code reading the fields. `fly.toml` and the Dockerfile `HEALTHCHECK` test only
the status code.

**Sample size.** All consumers enumerated: one frontend, one Fly check, one
Docker healthcheck, one test.

**Consequence.** The detail could be removed without breaking anything, which
is what made `D-0035` cheap. Recorded because the assumption was worth checking
rather than asserting: the fields looked load-bearing and were not.


### F-0030 — MERGED INTO `F-0013`

Addendum B V2 assigned this number to the freshness watchdog's wrong pipeline
names. Recorded here as `F-0013`. Do not reuse this number.

### F-0031 — MERGED INTO `F-0014`

Addendum B V2 assigned this number to `gold_price_import.py` having no
`__main__` block. Recorded here as `F-0014`. Do not reuse this number.

### F-0032 — MERGED INTO `F-0012`

Addendum B V2 assigned this number to the identity of `127.0.0.1:5432`.
Recorded here as `F-0012`. Do not reuse this number.

---

**Merge note, 2026-09-26.** Addendum B V2 carries its own `F-0030`, `F-0031`
and `F-0032` — the freshness watchdog's wrong pipeline names, the missing
`__main__` block, and the identity of `127.0.0.1:5432`. Those are the same
three findings already recorded here as `F-0013`, `F-0014` and `F-0012`, found
independently by the Builder session against the running system rather than
against the snapshot.

The Builder entries are retained and the Addendum B versions are not appended,
because the retained ones carry the first-hand artefacts — including the
correction to `F-0013`, which Addendum B does not have. Nothing is lost: the
numbers `F-0030`–`F-0032` in Addendum B V2 resolve to `F-0013`, `F-0014` and
`F-0012` here.

### F-0035 — ORDER-01 A4 cannot be calibrated against the local database

**Claim.** The watchdog's first run reported `US Treasury yield curve` as
CRITICAL at 23 days against a 5-day limit, which trips ORDER-01 A4's stopping
mechanism. The cause is a stale local database, not a wrong threshold.

**Artifact.** Local `update_logs`, 2026-09-26: the last successful `FRED` run
was 2026-09-06 09:00, and the run before it was `partial`. Local `DGS10`,
`DGS5` and `DGS2` all end 2026-09-03; `DGS30` is absent from this database
entirely. Production, per `F-0001`, held `DGS10` through 2026-09-24 with FRED
matching, and per `F-0003` was running nightly through 2026-09-26.

**Sample size.** One watchdog run against one database.

**Why it matters.** A4's stated expectation — "Treasury yields OK" — was
written for production. Run here it reports a real staleness in a dev copy
whose scheduler has not run for three weeks. The order's warning still stands
and is the reason nothing was tuned: **the thresholds are not established as
wrong by this run, and adjusting them on this evidence would destroy the only
calibration evidence available.** A4 must be re-run against production before
any threshold is touched.

**Confirmed correct by the same run:** `Gold spot price` reads **OK** at 56
days against the new 75-day limit — the fix in `F-0004` and the threshold
change from 45 to 75 both validated in one observation. Under the old 45-day
limit this same healthy series would have read CRITICAL, which is `D-0024`'s
argument demonstrated rather than asserted.

### F-0036 — The watchdog's config self-check reports a false absence for a pipeline that has never run

**Claim.** The revised `freshness_watchdog.py` validates the pipeline names in
`CHECKS` against the distinct `pipeline_name` values present in `update_logs`.
A correctly-named pipeline that has simply never run is therefore reported as a
configuration error, and it sets the whole report's status to `config_error`.

**Artifact.** Run of 2026-09-26 against the local database:
`FRESHNESS CONFIG ERROR - CHECKS names 1 pipeline(s) absent from update_logs:
CDS_MultiTenor`. The name is correct: `pipelines/cds_fetcher.py:223` defines
`CDS_PIPELINE_NAME = "CDS_MultiTenor"` and line 443 writes it. The CDS pipeline
has never run on this database, so no row carries that name.

**Sample size.** One run, one affected check. `TreasuryDirect` was handled
correctly and separately, as `Configured pipelines not yet run`.

**Consequence.** `update_logs` cannot distinguish "this name is wrong" from
"this pipeline has not run yet" — they produce identical evidence. The check
should validate names against the constants the pipelines actually declare, and
treat a never-run pipeline the way it already treats `TreasuryDirect`. Until it
does, a fresh database or a newly added pipeline yields `config_error` on an
otherwise correct configuration, and a status nobody can trust is the one
people learn to scroll past - Principle 9.

**Note.** This is the same false-absence shape as the Builder's own error in
`F-0013`, made for the same reason: the evidence that a name is absent looks
identical whether the name is wrong or the code path has never executed.

**Status.** **Closed 2026-09-28**, in the same change that installed the module
(PR #11). `validate_pipeline_names` now compares the names in `CHECKS` against
`declared_pipeline_names()`, a static scan of every `pipeline_name="..."`
literal and every `*PIPELINE_NAME = "..."` constant in the package. A name that
is declared but absent from `update_logs` is reported as `pending`; only a name
nothing declares is a `config_error`. The `NOT_YET_RUNNING` allowlist is
retired, since declaration now answers the question the allowlist was
suppressing.

Verified by tripping it: the correct configuration reports no unknown names;
reintroducing the original `GoldPrice` typo reports `['GoldPrice']`; removing it
clears. A failure-red, and the fixture distinguishes a working check from a
broken one.

**The fix contained the same bug once.** The first version of the constant
pattern required a prefix before `PIPELINE_NAME`, so `treasury_direct.py`'s bare
`PIPELINE_NAME = "TreasuryDirect"` did not match and was reported as an unknown
name — a false absence produced while fixing a false absence. Caught because the
trip test named a pipeline that should have been `pending`.

### F-0037 — The 2026-09-26 snapshot was taken from a stale master; ORDER-03 reviewed an incomplete tree

**Claim.** The local repository was one merged pull request behind `origin`
throughout the session. The snapshot handed to the Planner at 06:16, and
therefore the whole of ORDER-03's codebase review, was taken against a tree
missing PR #10.

**Artifact.** Local `master` sat at `378352f` (PR #9). `git fetch` on
2026-09-26 at 07:45 returned `378352f..792c1f7`, bringing PR #10, merged
2026-09-01T20:27Z: *"Fix sovereign CDS 5Y ingest: conventional spread from WGB,
not the 500 coupon."* It changed 13 files and 818 lines, including
`pipelines/cds_fetcher.py` (659 lines), `api/routes.py`, `ui/src/App.jsx`, the
CI workflow, and a new `tests/test_cds_parser.py` with 15 tests that the
Builder's own test runs never executed.

**Sample size.** One fetch, one missed merge, covering 25 days.

**Consequence.** Every "there is no X" in ORDER-03 was evaluated against a tree
that was 818 lines short. Nothing in the order proved wrong as a result — the
overlap was three files and all conflicts resolved cleanly — but that is luck,
not method. The CI test command had also changed on `master`, so the Builder's
statement in `F-0006` about which tests the gate runs was correct for the stale
copy and already out of date: the gate now runs four modules, not three, and
still omits `test_dgs30_d0016` and `test_gold_reserve_changes`.

**Why it is recorded.** This is the Planner's characteristic failure — reasoning
from a copy that went stale — committed by the Builder, which is supposed to be
the one player that can see the live tree. The Builder had `git status` and
`git log` available all day and never ran `git fetch`, so a clean working tree
and a matching `git log` read as "current" when they only meant "unchanged
locally". `git status` reports divergence from `origin/master` only after a
fetch; without one, being 25 days behind looks identical to being up to date.

**Closing it.** `git fetch` before taking any snapshot for the Planner, and
before branching. Nothing in this repository enforces that, which makes it the
owner's seam in exactly the sense the doctrine describes.

### F-0038 — `treasury_direct.py` and `freshness_watchdog.py` are deployed and unreferenced

**Claim.** Both modules shipped to production in the 2026-09-26 deploy and
nothing imports, schedules or calls either one. `DGS7` exists in the repository
only as a lookup-table entry. Recorded 2026-09-28.

**Artifact.** Against `master` at the merge of PR #11:

- A search for `treasury_direct`, `freshness_watchdog`, `TreasuryDirect`,
  `run_treasury_direct_fetch`, `run_freshness_check` and `get_freshness_report`
  across every `.py` in the project, excluding the two modules themselves,
  returns **no** matches.
- `pipelines/scheduler.py` registers seven jobs — `fred_fetch`,
  `treasury_fetch`, `stress_score`, `gold_fetch`, `cds_multi_tenor_job`,
  `startup_fetches`, `startup_cds_fetch`. Neither module appears.
- `FRED_METRICS` holds 37 codes. `DGS7` is not among them (ORDER-01 B4).
- No `GET /api/freshness` route exists (ORDER-01 B6, as amended by ORDER-03 A0).
- The database holds `DGS2`, `DGS5`, `DGS10` and `DGS30` at ~1,250 points each
  through 2026-09-24. **There is no `DGS7` metric row at all** (ORDER-01 B3).
- `treasury_direct.py:79` maps the `7 yr` column to `DGS7`. That line is the
  entire presence of the seven-year in the system.
- The watchdog says so itself, on its own first run:
  `Configured pipelines declared but not yet run: CDS_MultiTenor, TreasuryDirect`.

**Sample size.** One full-tree search, one scheduler read, one database query.

**Why this is deliberate, and why it is still a finding.** ORDER-01 sequences A5
as first contact with `home.treasury.gov` and stops for a ruling, and B1
requires the FRED-versus-Treasury contract test to pass **before** any dual
write, because `D-0022` is only valid if the two sources agree to 0.01. Adding
`DGS7` to `FRED_METRICS` or registering the 21:00 job ahead of that test would
begin the dual write that the test exists to validate. Stopping was correct.

What is *not* correct is that the stop left two modules in production with no
marker. Code that is present, imports cleanly and is named after a working
feature reads as done. The next person to open `pipelines/` sees a Treasury
Direct pipeline and a freshness watchdog and has no reason to think the yield
curve still comes from one source on a one-day lag, or that nothing is watching
freshness. That is the shape of `F-0004` again — right structure, right names,
nothing running — and it survived for the same reason: nothing goes red.

**Direction.** The risk is a false sense of coverage, not a wrong number. No
output is affected today precisely because nothing calls either module.

**Status.** **CLOSED 2026-09-28.** ORDER-01 Part B finished the work rather
than removing the modules. `treasury_direct` is registered weekdays at 21:00
UTC and `freshness_check` daily at 05:00 UTC (`D-0040`'s test asserts both);
the B1 contract test that gates the dual write passes over 920 value pairs;
`GET /api/freshness` exists behind auth; and the watchdog has been tripped and
watched (`B7`). Neither module is unreferenced any longer.

**Update 2026-09-28.** The seven-year now exists as real data, but this finding
is **not** closed by that. `DGS7` was added to `FRED_METRICS` and backfilled to
1,246 points covering 2021-09-29 to 2026-09-24 (`D-0036`), which removes the
"`DGS7` exists only as a lookup-table entry" half of the claim. Everything else
stands unchanged: `treasury_direct.py` and `freshness_watchdog.py` are still
imported by nothing, still registered nowhere, and there is still no
`/api/freshness` route. The seven-year arrived through the FRED pipeline, not
through the module named after it.

### F-0039 — API responses carry no cache headers, so a browser may serve stale data indefinitely

**Claim.** Every `/api/*` response was returned with no `Cache-Control`, no
`ETag`, no `Last-Modified` and no `Expires`. A browser is then permitted to
cache heuristically and replay a stored response without revalidating, so the
dashboard can display data older than the database holds, with nothing to
indicate it.

**Artifact.** 2026-09-28, production. `curl -D -` against
`/api/timeseries?metric_codes=DGS7&...` returned exactly two response headers:
`HTTP/1.1 200 OK` and `date:`. No caching directive of any kind. By contrast
`GET /` returned `last-modified` and `etag`, because `StaticFiles` sets them —
so the HTML revalidated while the data behind it did not.

**How it surfaced.** The owner reported the MARKETS stat cards showing data to
2026-09-23. Measured at the same moment: the production database held `DGS7`
and `DGS10` through **2026-09-24**; FRED's own API ended at **2026-09-24**;
the scheduler reported `running` with a successful FRED run that day updating
11,698 rows; and replaying the page's exact request and its exact `latest`
computation returned 2026-09-24 for all five tenors. Every layer was current
except the one in the browser.

**Sample size.** One header inspection across three endpoints, one reported
observation. **The browser cache itself was not inspected** — the missing
headers are the mechanism that permits the symptom, and they are a defect on
their own terms, but this entry does not claim to have watched a cache hit.

**Why it is Principle 11.** Nothing errored. The number on the card had the
right shape, the right units and a plausible value — it was simply a day old,
and a yield that moved 5.05 to 5.10 is not a number anyone can eyeball as
wrong. The system had no way to go red, because from its own point of view
nothing had gone wrong: the database was correct, the pipeline was correct,
and the API was correct. Only the copy in the browser was stale, and that is
the one layer none of the guards look at.

**Status.** Closed by `D-0038`.

### F-0040 — The Step 12 guard was bypassable by the very command that was meant to run it

**Claim.** `python -m unittest discover -s tests` imports the test modules as
top-level names rather than as members of the `tests` package, so
`tests/__init__.py` does not execute, `SENTINEL_TEST_RUN` is never set, and the
`D-0039` guard is inert for the whole run.

**Artifact.** 2026-09-28. With `-s tests` alone: 2 failures, and the failing
test names print as `test_disposable_guard.TestDisposableGuard...` with no
`tests.` prefix — the package was never imported. `os.environ.get(
"SENTINEL_TEST_RUN")` returned `None`. With `-t . -s tests`: 55 tests, OK.

**Sample size.** Two invocations of the same suite, same machine, same moment.

**How it was caught.** By the guard's own test asserting that the guard was
armed — not by reading the code. The first version of ORDER-01 A5's fix used
`discover -s tests`, which would have shipped a Step 12 guard that never fired
while every test passed and the gate stayed green. A guard proved only by
reading it is not proved.

**Why it is recorded.** This is the third false-absence in this project's
register with the same shape (`F-0013`, `F-0036`), and the first to be caught
by a mechanism rather than by noticing. The defence that worked was a test
asserting its own preconditions.

### F-0041 — FRED and Treasury Direct agree exactly across 184 overlapping business days

**Claim.** For every date and tenor present in both sources in 2026, the values
are identical — not within 0.01, but equal.

**Artifact.** 2026-09-28, read-only. `parse_curve_csv(fetch_curve_csv())` gave
185 rows covering 2026-01-02 to 2026-09-25. Compared against the local database
for `DGS2`, `DGS5`, `DGS7`, `DGS10`, `DGS30` over the 184 overlapping business
days: **920 value pairs, 0 differing by more than 0.01, maximum absolute
difference 0.0000 for every tenor.**

**Sample size.** 920 pairs, 184 days, 5 tenors, one fetch.

**What it does and does not establish.** It is strong evidence for `A-0001`,
and therefore for `D-0022`'s dual-write design. **It is not the B1 contract
test.** B1 requires the check to exist in the suite and run in the gate; this
was a one-off script and proves only that the two sources agreed at the moment
it ran. `A-0001` stays ASSUMED until the test exists.

### F-0042 — The Treasury CSV is ordered newest-first, and ORDER-01's A8 command reads the oldest row

**Claim.** `parse_curve_csv` preserves the source ordering, which is
**descending**. `r[-1]` is therefore the oldest row, not the newest.

**Artifact.** 2026-09-28: 185 rows, `dates[0]` = 2026-09-25, `dates[-1]` =
2026-01-02, ordering confirmed descending. ORDER-01 A8's command prints
`r[-1]['date']` and its PROOF reads *"the last row is pasted back with a `DGS7`
value"* — satisfied by `2026-01-02`, nine months stale. B3's PROOF then says
*"`latest_date` matches what A8 reported"*, which would compare a backfill's
newest date against January.

**Sample size.** One fetch, 185 rows.

**Why it matters.** The command succeeds, prints a well-formed row with a
plausible date and a real `DGS7` value, and is wrong about which row it is.
Principle 11 in a PROOF line rather than in the code. The actual newest row is
2026-09-25: `DGS7` 5.06, `DGS10` 5.17, `DGS30` 5.49.

**Consequence for the design.** Treasury carries 2026-09-25 while FRED ends at
2026-09-24, so the same-day premise of ORDER-01 holds — Treasury is one
business day ahead, which is the entire point of the pipeline.

### F-0043 — FRED has no live gold spot series, and `GOLDPMGBD228NLBM` does not exist

**Claim.** There is no FRED series carrying gold spot in USD per troy ounce
with a current observation. The series some 2026 sources still cite was not
restored; those sources are stale.

**Artifact.** 2026-09-28. `/fred/series/search?search_text=gold+price&limit=40`
returned 30 hits; 11 were Daily or Monthly and updated within 60 days, and
**every one is an index** — `NASDAQQGLDI`, `GVZCLS` (volatility),
`WPU159402`, `PCU2122221222` and other PPI series. The single hit with units
"Dollars per Fine Ounce" is `A04018GB00LONA286NNBR`, annual, last updated
2012-08-16. Direct lookups of `GOLDPMGBD228NLBM` and `GOLDAMGBD228NLBM` both
returned `400 — "The series does not exist."`

**Sample size.** One search of 40, two direct series lookups.

**Resolves.** ORDER-02 Part A's open question. The 2022-01-31 ICE Benchmark
deletion stands.

### F-0044 — LBMA serves the same series the manual CSV carries, daily and without authentication

**Claim.** `https://prices.lbma.org.uk/json/gold_pm.json` is live, requires no
credentials, and its monthly mean reproduces the existing `GOLD_SPOT_USD`
history exactly.

**Artifact.** 2026-09-28: HTTP 200, `application/json`, 915 KB, 14,691 daily
entries of the form `{"d": "2026-09-25", "v": [4261.05, 3216.67, 3737.79]}` —
USD, GBP, EUR. 702 months of history against the WGC CSV's 584.

The join check, for the 13 most recent overlapping months:

| Month | WGC CSV | LBMA PM monthly mean | Diff |
|---|---|---|---|
| 2025-08 | 3363.00 | 3362.99 | 0.00% |
| 2026-05 | 4587.50 | 4587.52 | 0.00% |
| 2026-07 | 4073.90 | 4073.92 | 0.00% |
| 2026-08 | 4409.90 | 4409.89 | 0.00% |

**Worst discrepancy across all 13 months: 0.00%.**

**Sample size.** 13 overlapping months compared, all matching to two decimal
places.

**What this means.** They are not two sources that happen to agree — they are
the same series. WGC sources from ICE Benchmark Administration, which
administers the LBMA Gold Price. The CSV is a monthly mean of these daily
fixes, rounded to one decimal. There is no splice risk, which is the condition
ORDER-02 B2's stopping mechanism exists to detect.

**What it does not cover.** Gold *reserves* by country, which stay manual
either way — the WGC country series is behind the same account wall with no
public API. And the frequency question in `A-0005` becomes live: the existing
series is monthly and normalised to day-1 on write, while this source is daily.

### F-0045 — The scheduler test measured nothing, because job defaults are applied at start-up

**Claim.** APScheduler 3.x applies `job_defaults` when a pending job is really
added during `scheduler.start()`. A test harness that stubs `start()` leaves
every job *pending* with `misfire_grace_time`, `coalesce` and `max_instances`
unset — so a test reading those attributes reports them absent for a correctly
configured scheduler.

**Artifact.** 2026-09-28, apscheduler 3.10.4. With `start()` stubbed:
`AttributeError: 'apscheduler.job.Job' object has no attribute
'max_instances'`, while `dir(job)` lists all three as slots. Registering
against `start(paused=True)` instead: 10 tests pass, every job reporting
`misfire_grace_time=3600`, `coalesce=True`, `max_instances=1`.

**Sample size.** One scheduler, ten jobs, two harness designs.

**Why it is recorded.** The first harness would have failed loudly here, which
is the lucky case. The dangerous version is the inverse: a harness that stubs
too much and reports *success* for configuration that was never applied. The
fix was to use the real registration path with execution paused, rather than a
fake registration path — proving the thing rather than a model of it.

### F-0046 — The gold plausibility range rejects genuine 1970s prices

**Claim.** `PLAUSIBLE_RANGE = (100.0, 20000.0)` in `gold_price_fetcher.py`
rejects the earliest LBMA observations, which are real.

**Artifact.** The 2026-09-28 run logged `LBMA 1973-11-26 out of plausible
range: 90.25` and `1973-11-27: 92`, among 1,329 rows skipped out of 13,362
parsed.

**Sample size.** One full fetch of the LBMA series back to 1968.

**Why it is not being changed.** The range exists to reject a decimal-point
error or a currency mix-up, not to model gold's history, and the write window
is 400 days so nothing before 2025 is ever written. The skip is correct for
every row this pipeline will store. It is recorded because the log line reads
like a data problem and is not — the next person to see it should find this
entry rather than widen the range.

**What would change it.** Backfilling `GOLD_SPOT_USD` before 1975, which would
need a lower bound and a reason.

### F-0047 — ORDER-03 D3's premise is wrong: the 04:30 job computes a different scorer

**Claim.** D3 says *"The 04:30 scheduled job already computes this. The endpoint
ignores it."* It does not. Nothing scheduled has ever computed the composite
score.

**Artifact.** `scheduled_stress_score` calls `run_stress_score_calculation`
from `stress_score_v2.py`, which calls `calculate_stress_score` — a different
scorer answering a different question. A search for `compute_composite_stress`
across the project returns exactly three hits: its definition, its import in
`api/routes.py`, and its single call site at `routes.py:834`.

**Sample size.** One full-tree search, one scheduler read.

**Consequence.** D3 was written as "read what the job already wrote", and the
work is actually "write it in the first place". `D-0042` adds the job at 04:45
UTC rather than reusing 04:30.

**Why it is recorded.** Third order-level premise found wrong against the live
tree, after `F-0042` (A8 reading the oldest row) and B5's two already-done
items. The pattern is consistent: the orders are accurate about the code they
were shown and wrong wherever the working copy had moved — which is `F-0037`
seen from the other side.

### F-0048 — The composite scorer's query count is dominated by per-country history, not metric lookups

**Claim.** ORDER-03 D2 attributes ~400 queries per request largely to each
dimension helper re-resolving its metric by code. Hoisting every one of those
into a single cached map removes 65 queries, not most of them.

**Artifact.** Measured on 29 countries, 2026-09-28, counting
`before_cursor_execute`: **297 queries before, 232 after**, wall time 0.16s to
0.15s. Nine `db.query(Metric).filter_by(code=...)` call sites were replaced.
The remaining ~230 are the per-country TIC, gold and M2 history reads — eight
per country — which is a query-shape problem, not a lookup-caching one.

**Sample size.** One request per variant, same database, same moment.

**Consequence.** D2 is done and is worth having, but it is not what makes the
endpoint fast; `D-0042`'s persistence is. Recorded because the order's estimate
would otherwise look achieved when the measurement says otherwise.

**Verified unchanged.** D2 must not alter what the scorer computes. Comparing
tier and score assignments across all 29 countries before and after: **0
changes**. `metrics.code` has no duplicates, so the dict-versus-`.first()`
difference cannot bite.
