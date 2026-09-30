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

**Status.** **CLOSED 2026-09-28.** `yieldData` now joins the series on their
dates instead of zipping them by array index off `DGS10`. Measured against
realistic shapes (1,250 daily points, 60 monthly): the old code put **0 of 60**
Fed Funds values on a real `FEDFUNDS` date and confined the line to the
leftmost 4.7% of the axis; the new code puts every point on its own date
across the full range. Every `<Line>` already carried `connectNulls`, so the
monthly series draws continuously through its real points against a daily axis.

Verified by demonstration rather than by a test, because the frontend has no
test harness — see `F-0053`.

*Original status, retained:* Open, deferred to the V2 frontend decomposition. Adding a 7Y line
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
`treasury_monitor.log` held it eight more times; that file was deleted on
2026-09-28 (ORDER-01 A3) and had never been committed.

**Re-measured 2026-09-28.** `/api/pipeline-logs?limit=200` returns **21** live
occurrences of the key, **zero** redacted. The `_redact()` added in ORDER-01 B4
applies to rows written from now on; every existing row is untouched until the
scrub in ORDER-01 C1.

**Status.** Open. Rotation deferred to 2026-10-02 by `D-0044`, which records
that this composes with `F-0009`: the password gating this endpoint is in
public git history, so the key is effectively readable without credentials
until then. Rotation, not the scrub, is what closes it.

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

**Correction 2026-09-28 — the premise is unsupported.** This entry asserts
"the project's recorded decision chose Python 3.13 with 3.13-pinned wheels",
and its Artifact line cites only `Dockerfile:1` and the workflow — **it never
cites the decision**. Checked today:

- No entry in `docs/decisions.md` mentions Python 3.13, or any Python version.
- `requirements.txt` contains no 3.13-pinned wheels and no version markers.

So there is no recorded decision for the deployment to disagree with. The claim
appears to have come from the same planning session that produced Addendum B,
against a copy of the project the Builder cannot find.

**What is actually true, measured.** Local development runs **Python 3.13.14**;
the Dockerfile and CI both run **3.11**. That is a dev-versus-deploy
difference, not a decision-versus-deploy one — and the important half already
holds: **CI matches production**, so the gate runs in the environment that
ships. The residual risk is that a 3.13-only behaviour passes locally and is
first seen in CI, which is the right place to see it.

**Left as a recommendation rather than a change.** Aligning the local venv to
3.11 would remove the last mismatch, but recreating a developer's virtualenv is
the owner's call, not a Builder's.

### F-0027 — No frontend build stage; the bundle is committed

**Claim.** The Dockerfile has a Python builder stage and no Node stage.
`api/static/index.html` is committed (dated 2026-09-01) and reaches the image
via `COPY . .`. `.gitignore` ignores a bare `dist/` but not `api/static/`.

**Artifact.** `Dockerfile`; `ls api/static/`; `.gitignore:17`.

**Consequence.** A deploy that forgets `npm run build` ships a stale UI against
a new API with no signal of any kind. Flagged as Phase 0 in the June plan;
still open.


**Partially closed 2026-09-28 by `D-0048`.** The harm this finding describes is
that a forgotten rebuild ships a stale UI *with no signal*. There is a signal
now: `api/static/BUILD_MANIFEST.json` records the `ui/src` digest the committed
bundle was built from, and `tests/test_ui_bundle_freshness.py` fails the gate
when the source has moved since. Proved by tripping it — an unbuilt edit fails
with both digests and the commands to fix it; reverting clears it.

**CLOSED 2026-09-29 by `D-0049`.** A `node:22-slim` stage builds the UI inside
the image, `api/static/` is no longer committed, and the manifest guard is
retired. A stale bundle is now impossible rather than detectable.

Verified by local `docker build` before anything touched the deploy path, then
proved from source: a marker added to `ui/src` **without** a local
`npm run build` — the local `dist/` still held the previous bundle — appeared
in the bundle inside the rebuilt image.
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

### F-0049 — Two of E2's endpoints cannot be modelled from the data available locally

**Claim.** `response_model` was declared on `/holdings` and `/gold-reserves`,
where every field has been observed populated. It was **not** declared on
`/holdings/cross-asset-stress`, `/stress/composite`, `/cds` or `/cds/all`,
because the types behind their nullable fields cannot be read from this
database.

**Artifact.** 2026-09-28, local. `/api/cds/all` returns `[]` — the CDS pipeline
has never run here (`F-0013`'s correction). `/api/cds?country=DEU` returns a
*no-data variant*: `{country, 5Y: null, 10Y: null, term_spread: null,
message}`, a different shape from the populated one. In
`cross_asset_stress`, `region`, `treseg_trend_pct` and `treseg_latest_bn` are
`null` on every one of the 5 rows present.

**Sample size.** All 36 `/holdings` rows and all 39 `/gold-reserves` rows carry
no nulls in any field — those are safe. The others were inspected row by row.

**Why not guess.** A field that is `null` in every local row has no observable
type. Declaring `Optional[str]` for `region` when production holds something
else turns an endpoint that works into a 500 — trading a silent wrong value for
a loud outage, on a guess. `/cds` additionally returns two different shapes
depending on whether data exists, so a single model would reject one of them.

**Consequence.** E2 is partially delivered. The four unmodelled endpoints keep
the defect the order describes: `App.jsx` remains their only specification and
a renamed field empties a tile silently.

**How to close it properly.** Capture one populated response per endpoint from
**production**, where CDS and `region` have values, and model from that. That
is a twenty-minute job with production read access and is not guesswork; it
simply cannot be done from here.

**CLOSED 2026-09-28.** Done exactly that way. All four endpoints now carry a
`response_model` built from production shapes, with every field's nullability
read from live rows rather than inferred:

| Field | Basis for `Optional` |
|---|---|
| `cds_10y`, `cds_term_spread` | null in 20 of 21 production rows |
| `tic_mom_pct` | null in 24 of 49 |
| `spread_bps`, `spread_widening_bps` | null in 35 of 49 |
| `treseg_trend_pct`, `treseg_latest_bn` | null in 39 of 49 |
| `m2_growth_pct`, `m2_year` | null in 22 of 49 |
| `region` | null in 49/49 **and** `Country.region = Column(String(100))` |
| `oil_signal` | null in 49/49 **and** `composite_stress.py:194/198` returns `None` or a string |

The last two were typed from the schema and the code, not from the nulls -
which is the difference between reading and guessing.

`/api/cds` needed one model covering **two** production shapes: with data it
carries tenor objects, without it carries `message` and nulls. A model that
rejected the second would have turned "no CDS for this country" into a 500.

All six payloads were validated against the live application before anything
was declared, and the payloads are captured as fixtures so it stays proved -
`tests/test_production_payload_contracts.py`, which also asserts the fixtures
still exercise the nullable paths, so an all-populated recapture cannot quietly
turn it into a test of nothing.

OpenAPI schemas: 9 before ORDER-03 Part E, 18 now. Every endpoint `App.jsx`
consumes is modelled.

### F-0050 — `TIC_Holdings` reported success for nine months while importing a frozen year

**Claim.** The TIC pipeline has run successfully and changed nothing since
2025-12-01. Its configured source is a **calendar-year file** that covers
January to December 2025 and will never advance, so every run faithfully
re-imports the same year and reports `success`.

**Artifact.** Production `/api/pipeline-logs?pipeline_name=TIC_Holdings`,
2026-09-28: the ten most recent runs are all `status=success`,
`records_inserted=0`, `records_updated=10009` — identical every time.
`/api/holdings` returns `date: 2025-12-01` with 36 countries.
`https://ticdata.treasury.gov/Publish/mfhhis01.txt` fetches live, 99,490 bytes,
and its header row reads `Dec Nov Oct ... Jan` over `2025 2025 ... 2025`.

**Sample size.** Ten consecutive production runs; one live fetch of the source.

**What is NOT established.** Whether Treasury publishes 2026 MFH data at some
other URL. `mfhhis02` through `mfhhis07` return 404; `mfh.txt` exists but
covers January 2022 to January 2023 and `parse_tic_mfh` returns zero countries
against it, because that file is space-delimited where the parser expects
tabs. **Four guessed URLs finding nothing is not proof the data does not
exist** — that is the false-absence shape already recorded three times in this
register (`F-0013`, `F-0036`, `F-0040`), and this entry will not repeat it. The
upstream question is open and belongs to whoever can read the TIC release
schedule.

**Why it survived.** Every layer worked. The fetch returned 200, the parser
returned 36 countries, the writer updated 10,009 rows, the log said `success`.
The only thing wrong was that the answer had not changed in nine months, and
nothing in the pipeline compared the data's age to anything. This is `F-0004`
again with a different source: right shape, right provenance, plausible
numbers, frozen.

**Consequence, direction stated.** TIC holdings feed the composite scorer's
first dimension. Every tier assignment since December 2025 has been computed
against nine-month-old holdings. Unlike the gold case the direction is not
uniform — a country that has since sold will look unchanged, and one that has
bought will too — so this understates *movement* in both directions rather than
biasing the level.

**Status.** Half closed by `D-0045`: the pipeline now fails loudly instead of
reporting success. The data is still nine months old, and the upstream URL
question is open.

### F-0051 — Alembic is unused in every observable sense

**Claim.** `alembic==1.12.1` is pinned and there is no trace of it anywhere
else in the project.

**Artifact.** 2026-09-28. A case-insensitive search for `alembic` across all
`.py`, `.yml`, `.toml` and the Dockerfile returns **nothing** outside
`requirements.txt`. `alembic.ini`, `alembic/` and `migrations/` do not exist.
Schema comes from `Base.metadata.create_all()`.

**Sample size.** Whole tree.

**Evidence bearing on `D-0032`, recorded as facts rather than a recommendation:**

- `create_all()` handles **additive** change correctly, demonstrated today:
  `composite_snapshots` was added for `D-0042` and appeared without ceremony.
- It silently ignores **changed columns**, which is the real gap. The known
  live case is `update_logs.error_message varchar(500)` (`A-0003`), which
  needs hand-written DDL against production and would not be picked up by
  editing `models.py`.
- Local schema currently matches `models.py` exactly. The single difference is
  the `canary` table, which is present in the database and deliberately
  **absent** from `models.py` — the application must never be able to create
  its own disposability marker (`D-0039`). That is correct and should not be
  "fixed".

**Status.** Open, and it is a ruling rather than a task — see `D-0032`.

### F-0052 — The app could only be developed from the literal hostname `localhost`

**Claim.** `App.jsx:5` chose its API base by comparing the hostname to a
string:

```js
const API = window.location.hostname === "localhost"
  ? "http://localhost:8000/api" : "/api";
```

Loaded from `127.0.0.1`, a LAN address, or any preview host, this fell through
to same-origin `/api` — correct in production, wrong against a Vite dev server
on a different port.

**Artifact.** The line as committed at `378352f` and unchanged until
2026-09-28. 22 `fetch(\`${API}...\`)` call sites depended on it.

**Sample size.** One expression; every request the frontend makes.

**Failure shape.** Every call 404s or hits the dev server instead of the API,
with nothing naming the cause. The app appears broken rather than
misconfigured, which is why "it only works on localhost" reads as a quirk
rather than a defect.

**Status.** Closed by `D-0047`.

### F-0053 — The frontend has no test harness, so `F-0007` is proved by demonstration

**Claim.** There is no JavaScript test runner in this project — no vitest, no
jest, no test script beyond `lint`. Nothing in `ui/` can be asserted in the
gate.

**Artifact.** `ui/package.json` scripts are `dev`, `build`, `lint`, `preview`.
The CI workflow runs `python -m unittest discover` and nothing else.

**Consequence.** Every backend guard proved this week runs in CI. The two
frontend fixes shipped today — `D-0047` and the `F-0007` date join — are
verified by a build plus a demonstration, and **nothing stops either
regressing**. `App.jsx` is 2,583 lines with no test covering any of it.

**The demonstration, recorded because it is the only evidence there is.**
Both implementations were run against realistic shapes — 1,250 daily `DGS10`
points and 60 monthly `FEDFUNDS` points over the same five years:

| | Fed Funds span | Last point, across x-axis | Points on a real FEDFUNDS date |
|---|---|---|---|
| index zip (old) | 2021-09-01 → 2021-11-26 | 4.7% | **0 of 60** |
| date join (new) | full range | 96.8% | **all of them** |

**CLOSED 2026-09-29.** `vitest` is installed, `npm test` runs in CI before the
Python suite, and there are **18 frontend tests** covering the two modules
pulled out of `App.jsx`:

- `buildYieldSeries` — 8 cases, including the `F-0007` defect stated directly:
  a monthly series must not be shifted onto early daily dates, the join is a
  union rather than a left join off `DGS10`, and two series with different
  missing days stay aligned. These fail against the old index-zip.
- `resolveBase` — 10 cases, including that `127.0.0.1`, a LAN address and a
  `.local` host all resolve correctly, which is `F-0052` stated as a test.

**Found while writing them:** importing `lib/api.js` outside a browser threw,
because `API_BASE` is computed at module load and there was no `location`. It
now falls back to same-origin, so the module is importable anywhere. That is a
real fragility nothing would have surfaced without a test runner.

**Extended 2026-09-29 for `D-0054`.** `ui/src/pages.dom.test.jsx` adds twelve
render tests under jsdom: every tab mounts with `fetch` stubbed and renders
something, plus two checks that ABOUT still carries its static content
including the retired-tab note from `D-0051`.

These are not behaviour tests, and they are not meant to be. They assert the
one property a mechanical refactor actually threatens — that each tab still
*mounts* — and they were written to pass **before** the decomposition so they
could be a net for it rather than a description of the result.

**Still true:** `App.jsx` is now 240 lines, but the ~2,150 lines that moved into
`pages/` and `components/` have render coverage only. Nothing asserts that any
tab shows the right numbers.

### F-0054 — `.gitignore` swallowed the frontend's API module, and the merge said nothing

**Claim.** `ui/src/lib/api.js` was created, imported by `App.jsx`, built into
the bundle, reviewed and **merged — without ever being added to the
repository**. `App.jsx` on `master` imported a file that was not there.

**Artifact.** `git check-ignore -v ui/src/lib/api.js` →
`.gitignore:21: lib/`. That entry sits in a block of Python build directories
(`eggs/`, `dist/`, `parts/`, `sdist/`, `var/`, `wheels/`) and is **unanchored**,
so it matches `lib/` at any depth — including `ui/src/lib/`.
`git show HEAD:ui/src/lib/api.js` failed while `git show HEAD:ui/src/App.jsx`
contained `import { apiFetch } from "./lib/api";`.

**Sample size.** One file, one merge — PR #23.

**Why nothing caught it.** `git add ui/` skips ignored files **silently**, by
design. The local build kept working because the file was on disk. The bundle
kept working because Vite had already inlined it. Production kept working
because it serves the prebuilt bundle. CI kept passing because it runs Python
and never builds the UI (`F-0053`). Every signal available said fine.

**What it would have cost.** A fresh clone cannot build the frontend:
`npm run build` fails on a missing import. That is the state `master` was in
between PR #23 merging and this entry.

**How it was caught.** By `D-0048`'s bundle-freshness guard, on its **first CI
run**, one commit later. The guard hashes `ui/src` and compares against a
manifest; CI computed a different digest because the file it hashes locally
does not exist in the checkout. It was written to catch a forgotten rebuild and
caught a missing file instead — the check was placed where it could see
something real, and saw something nobody was looking for.

**Fixed.** `lib/` and `lib64/` are anchored to `/lib/` and `/lib64/`, so they
still exclude the Python build directories they were written for and no longer
match anything nested. `ui/src/lib/api.js` is tracked. Verified by recomputing
the digest from the **git index** rather than the working tree — that is what
CI checks out, and it now matches the manifest exactly.

**The general lesson.** An ignore rule written for one language matched a
directory in another, and the only thing that reports it is a tool asked
directly. `git status` is silent about ignored files, which is what makes this
class of loss invisible rather than merely easy.

### F-0055 — Eight of eleven stat cards labelled a one-to-three-day move as "vs 30d"

**Claim.** The change shown under every ticker was computed against the
**previous observation**, not the observation thirty days earlier, while the
card read `vs 30d`.

**Artifact.** `App.jsx`, before this change:

```js
month30[code] = withVal[Math.max(0, withVal.length - 2)][code];
```

and `StatCard` rendering `{Math.abs(change).toFixed(2)}{...} vs 30d`.

Measured against production on 2026-09-29, comparing each series' last two
observations:

| Series | latest | "month30" | actual gap |
|---|---|---|---|
| DGS30 / DGS10 / DGS7 / DGS5 / DGS2 | 2026-09-28 | 2026-09-25 | **3 days** |
| DFII10 / DCOILWTICO / DTWEXBGS | 2026-09-25 | 2026-09-24 | **1 day** |
| FEDFUNDS / CPIAUCSL / M2SL | 2026-08-01 | 2026-07-01 | 31 days |

**Sample size.** All eleven tickers, one production fetch.

**Why it survived.** For the three monthly series the previous observation *is*
roughly thirty days back, so the label was right where anyone would have
checked it first. On the eight daily series the number was correctly computed,
correctly formatted, correctly signed — and described a different period than
it claimed. Nothing could go red, because nothing was wrong except the word.
Principle 11 in a label.

**Direction.** It understates. A 3-day move looks like a month of movement, so
a genuinely fast-moving series reads as calm over the month, and a month of
drift is invisible entirely.

**Fixed by `D-0050`:** the lookup is by date, and the card reports the gap it
actually found rather than asserting thirty.

### F-0056 — `npm run lint` reports eight errors and nothing runs it

**Claim.** The frontend has an ESLint configuration and a `lint` script. It
reports **8 errors**, and no gate invokes it.

**Artifact.** `npm run lint` on `master` at 2026-09-29: `8 problems (8 errors,
0 warnings)`, all `react-hooks/set-state-in-effect` in `App.jsx`. The CI
workflow runs `npm test` and `unittest discover`; `lint` appears nowhere.

**Sample size.** One run, before and after this change — the count is identical,
so none of the eight is newly introduced.

**Consequence.** Principle 9's second form again: a check that exists, has an
answer, and cannot change what anyone does. It has presumably been failing for
as long as the rule has been enabled.

**Why it is not simply added to CI here.** Adding it would block every deploy
on eight pre-existing errors in a 2,500-line file, and `set-state-in-effect`
violations are not cosmetic — fixing them properly means restructuring the
effects, which is `F-0053`-shaped work against code that still has almost no
coverage. Turning it on is a decision about how much breakage to accept at
once, and that is the owner's call rather than a Builder's.

**Status.** **CLOSED 2026-09-29.** The six `no-unused-vars` are gone — three
stray imports, an unused catch binding, a leftover constant, and two dead
components (`StressTable`, plus `StressScoreTab` under `D-0051`). The two
`set-state-in-effect` sites carry an explicit `eslint-disable-next-line` with
the reasoning recorded above them rather than a silent suppression. `npm run
lint` now runs in CI ahead of the tests and starts clean, so it catches the
next stray symbol instead of accumulating.

**Worth noting about the directives.** The first attempt put
`eslint-disable-next-line` above a further comment line, so it applied to the
comment and not the code. ESLint reported them as *unused directives* — a check
on the check — and both real errors were still live. The comment order matters,
and only lint itself said so.

### F-0057 — The US gold tile priced 261.5 million ounces at a hardcoded, months-old spot

**Claim.** `USADashboard` valued US gold holdings using
`const SPOT_GOLD = 4587;` — a constant — while `GOLD_SPOT_USD` is a live daily
series on the same API the component already queries.

**Artifact.** `App.jsx` before this change: `SPOT_GOLD = 4587 // $/oz
approximate`, used as
``sub: `$${((US_GOLD_TROY_OZ * SPOT_GOLD)/1e12).toFixed(2)}T at spot` ``.
Production `GOLD_SPOT_USD` on 2026-09-25 was **4261.05**. 4587 is the May 2026
monthly average.

**Sample size.** One constant, one tile.

**Consequence.** 261.5 million troy ounces at 4587 is $1.199T; at the live
4261 it is $1.114T. The tile overstated US gold holdings by roughly **$85
billion**, presented as "at spot" — a phrase that asserts currency.

**Why lint could not see it.** `SPOT_GOLD` was *used*, so `no-unused-vars` was
silent. It was found by reading the code around an unrelated unused constant
three lines above it.

**The pattern, for the fourth time.** A frozen value standing in for live data
that the system already has: `F-0004` (shadow CSV), `F-0050` (frozen calendar
year), `F-0055` (previous row labelled as thirty days), this. Each one produced
a plausible number with correct formatting and nothing red.

**Fixed.** The tile reads `GOLD_SPOT_USD` and prints the price it used —
"$1.11T at $4261/oz" rather than "at spot". **No fallback constant:** if the
series is unavailable the tile says so. A default here would be the defect
restored quietly.

### F-0058 — The tested tier helpers were the dead copy

**Claim.** `tierColor` and `tierLabel` were extracted from `App.jsx` into
`lib/format.js` on 2026-09-29 and given tests. Nothing called them. The
component that actually renders tiers carried its own inline ternary — and that
one handled **six** tiers, including `EXITED` and `EXITED+GOLD_SELL`, which the
extracted four-tier version did not.

**Artifact.** `npm run lint` reporting `'tierColor' is defined but never used`
and `'tierLabel' is defined but never used` at `App.jsx:7`, against
`format.test.js` asserting behaviour for both. The live implementation was at
`App.jsx:1235`.

**Sample size.** Two functions, one component.

**Why it matters more than an unused import.** The tests passed, so the
register could have recorded tier rendering as covered. It was not: the six-tier
path a user sees had no test, and the four-tier path that had tests was
unreachable. A false sense of coverage is worse than none, because it stops
anyone looking.

**How it was caught.** By `no-unused-vars` — a rule nothing ran (`F-0056`) —
while triaging whether those eight errors were worth fixing. The cheapest check
in the project found the most misleading defect of the day.

**Fixed.** The helpers handle all six tiers, the live component calls them, and
the two previously-uncovered tiers have tests.

### F-0059 — Production carries no canary, so the Step 12 guard would refuse it

**Claim.** The positive-identity guard in `D-0039` would stop a test run
against production — verified against production itself rather than reasoned
about.

**Artifact.** 2026-09-29, over `fly ssh console`:
`SELECT to_regclass('public.canary')` returned **None**. The same session
reported 64,336 `timeseries` rows and 701 `update_logs` rows against the local
database's ~40,000 and 18 — the separation recorded in `F-0012`, now measured
on both sides rather than inferred from one.

**Sample size.** One query against the live cluster.

**Why it was worth doing.** `tests/test_disposable_guard.py` says outright that
pointing the suite at production cannot be rehearsed in CI, because it would
need production credentials in a test environment — the precise thing the guard
exists to survive. What that test cannot do, a read-only query can: confirm the
guard's trigger condition is genuinely true of production. The canary is
absent, so `assert_disposable` raises, so the suite refuses.

**What it still does not prove.** That the refusal happens *through a tunnel*.
It proves the input the guard reads is the one that makes it refuse — and since
the guard never reads an address, there is no tunnel-specific path left to
test. That was the design point of `D-0039`.

### F-0060 — The extraction script swallowed App's definition, and the error surfaced 50 lines away

**Claim.** The first run of the Part F extractor moved `GoldReservesTab` into
`pages/` **along with the opening line of `App` itself**, because its
"next top-level declaration" boundary regex matched `function X` and
`export function X` but not `export default function X`.

**Artifact.** `App` is declared at `App.jsx:1590`, between `GoldReservesTab`
(1468) and `CDSCoverageBanner` (1809). After extraction,
`grep -c "export default function App" ui/src/pages/GoldReservesTab.jsx`
returned **1**. The build failed with
`[builtin:vite-transform] Unexpected token ╭─[ src/App.jsx:54:7 ]`, pointing at
a `.catch()` fifty lines from the actual cause.

**Sample size.** One run, one boundary form missed out of three.

**Why it is worth recording.** The failure mode of a mechanical refactor is not
usually a wrong result — it is a result that is *structurally* broken in a way
the error message does not describe. A parse error at line 54 of a file whose
real problem was at line 1590 is the generic shape of this, and reading the
error rather than the diff would have sent anyone hunting in the wrong place.

**Recovered by rolling back rather than patching forward.**
`git checkout -- ui/src/App.jsx` and moving the generated directories aside
cost nothing, because the extraction was scripted and repeatable. Patching the
damaged output would have left the boundary bug in place for the next run.

**Fixed.** The regex accepts `export default`, and `extract()` now asserts that
`export default function App` is still present in what remains before writing
`App.jsx` — so the same class of miss fails at the extractor with a sentence
naming the cause, instead of in the build.

### F-0061 — A test asserted on a file path, and the refactor broke it

**Claim.** `tests/test_dgs30_d0016.py` verified `D-0016`'s requirement that 30Y
is named on the About tab by reading `ui/src/App.jsx`. Moving `AboutTab` into
`pages/` broke it, although the requirement it protects was never violated.

**Artifact.**
`AssertionError: '30Y/10Y/5Y/2Y Treasury yields' not found in <App.jsx source>`,
after `D-0054`. The string was present the whole time, in
`ui/src/pages/AboutTab.jsx`.

**Sample size.** One test, one move.

**What it says about the test rather than the refactor.** The requirement is
"30Y is named in About". The test encoded "30Y is named in `App.jsx`", which
was true only while About happened to live there. A test coupled to a location
fails on reorganisation and passes on a regression that moves the content
somewhere else — the wrong way round.

**Fixed** by searching whichever About sources exist rather than naming one, so
the next move does not break it either. The assertion is unchanged.

**Worth noting it did its job anyway:** the Python suite caught a frontend
reorganisation that lint, the build, and 74 frontend tests all passed.

### F-0062 — A constant was extracted and the call sites were not switched to it

**Claim.** `SOVEREIGN_YIELD_CODES` moved into `lib/constants.js` under
`D-0054`, and `App.jsx` went on carrying its own inline copy of the same
fourteen FRED codes — twice, in two different formattings. Separately, the
`/timeseries` date-keyed join existed twice in `App.jsx`, character for
character.

**Artifact.** At `f225885`,
`git show HEAD:ui/src/App.jsx | grep -c 'IRLTLT01[A-Z][A-Z]M156N'` → **5**.

**Sample size.** Three copies of one list; two copies of one join.

**Why it matters more than the duplication.** The three copies agreed. Nothing
in the build, the lint or the tests would have said so if they stopped
agreeing, and the failure mode of a drifted copy is a ticker that quietly
stops carrying Korea.

**Fixed.** `pivotByDate` is in `lib/series.js` with six tests, including the
day-truncation case — a join that kept the time component produces two rows
for one day, each holding one code and a hole where the other belongs, which
is `F-0007`'s shape.

The guard is a property of the codebase rather than of a named file
(`F-0061`): `lib/constants.test.js` scans everything under `ui/src` and fails
if any file but `constants.js` spells one of these codes. Moving a component
does not break it; pasting the codes into a new file does.

### F-0063 — Five tabs treated an HTTP error as the resource, and two rendered it as an empty table

**Claim.** Every fetch-on-mount tab did `.then(r => r.json())` with no `r.ok`
check. A 500 carrying a JSON error body parses cleanly, so the body was
installed as the data and `loading` went false.

What the tab then showed depended on whether it happened to look for an error
key. COMPOSITE checked `data.error`. CROSS-ASSET checked `data.detail`.
**HOLDINGS and GOLD checked neither**, so they fell through to
`data.holdings || []` and rendered an empty table — reading as "no country
holds US Treasuries" rather than as a server fault.

**Artifact.** A throwaway hook replicating the inline shape verbatim, run
against the new assertions:

```
AssertionError: expected { detail: 'relation does not exist' } to be null
```

**Sample size.** Five call sites; two with no error branch at all.

**Why it is the worst shape of the three.** A spinner that never resolves is
visibly broken. A blank page is visibly broken. A populated-looking page
showing zero rows is a fault wearing the costume of a finding — and on this
application, "no country holds US Treasuries" is not an absurd reading, it is
the event the whole thing exists to detect.

**Fixed.** `useApiResource` reports `loading`, `error` and `data` separately,
checks `response.ok`, carries the status on the error, and cancels on unmount.
`LoadFailure` renders a failure as a failure. A caller that ignores `error`
now gets a blank page rather than a confident empty one.

**And the other direction is tested too.** An empty-but-successful response
still reads as empty. Zero rows is a fact about the world and must not be
dressed up as a fault either.

**One deliberate exception, recorded rather than hidden.** CDS still fails
soft into its empty state. It is the only source with no automatic pipeline,
so "nothing here yet" is its ordinary condition and the banner already says
how to fix it.

### F-0064 — The same panel showed a different spread depending on which tab opened it

**Claim.** `CountryDetail` reads `latestAll[SOVEREIGN_YIELD_CODES[iso]]` and
`latestAll["DGS10"]`. Three call sites passed three different things: COUNTRY
the flat `{code: value}` map, HOLDINGS the `{latest, prior}` wrapper which it
unwrapped itself, and **GOLD a hardcoded `{}`**.

**Artifact.** `ui/src/pages/GoldReservesTab.jsx:58` at `f225885`:

```jsx
<CountryDetail iso={selected.country_code} onClose={...} latestAll={{}} />
```

Opening Japan from GOLD showed `Spread vs US 10Y —`. The same country from
COUNTRY showed `-315bps`. The regression test goes red on that line:

```
Unable to find an element with the text: -315bps
```

**Sample size.** One prop, three call sites, three shapes.

**Why the dash is the problem.** A country FRED genuinely has no yield series
for — China, for instance — correctly shows a dash. So did every country
opened from GOLD. The two cases were indistinguishable on screen, and the
wrong one was silent.

**Fixed.** The prop has one shape at every call site: the flat map. A test
pins each of the three cases — a real spread, a genuinely-uncovered country,
and the wrapper shape, which still yields a blank tile and is therefore worth
a test of its own.

### F-0065 — A hook whose correctness rested on its caller's memoisation

**Claim.** `useChartSeries` first listed `[activeMetrics, range, normalized]`
as its dependencies. A new array is never `===` the previous one, so a caller
passing a literal re-armed the effect on every render, which set state, which
rendered.

**Artifact.** The first run of the hook's own tests:

```
Worker exited unexpectedly with exit code 134
```

**Sample size.** One hook, one dependency list.

**Why it never showed in production.** `App.jsx` holds both values in
`useState`, so their identities are stable and the loop never fired. The hook
was correct for exactly one caller, and nothing said so.

**Fixed.** The dependency is the joined code string and the day count — two
primitives and a boolean. A test renders it with fresh literals every render
and asserts exactly one request.

### F-0066 — A country re-entering a Treasury position rendered as "+Infinity%"

**Claim.** The MoM change on the country panel divided by the earlier
observation with no zero guard, and the tile prints `${v.toFixed(2)}%`.

**Artifact.**

```
inline version yields: Infinity -> rendered as: +Infinity%
```

**Sample size.** One call site. Reachable whenever a country holding zero
Treasuries buys any.

**Why it is worth more than its size.** The panel already has a
COMPLETED TREASURY LIQUIDATION banner for the way *into* zero. The way out —
a country resuming purchases — is the same event in reverse, and it rendered
as a glitch.

**Fixed.** `momChange` returns null on a zero base, and the tile shows a dash.

### F-0067 — The M2 chart and the M2 tile beside it used different methods for the same number

**Claim.** The M2 stat card found its year-ago observation **by date**, within
a 340–400 day window. The M2 growth chart directly beneath it indexed back
twelve rows — `m2Data[i - 12]` — which is right only while the series is
exactly monthly with no gaps.

**Sample size.** One quantity, two methods, one screen.

**Why it is the third instance.** `F-0007` was an index zip on the yield
table. `F-0055` was `points.at(-2)` labelled "vs 30d". This is the same
mistake in a third place: a date-keyed question answered by position.

**Fixed.** Both come from `usaSeries.yoySeries` / `yoyPercent`, which share
one date window. A test drops a month out of the middle of the series and
asserts the last growth figure is unchanged — the index version shifted to a
thirteen-month comparison from that point on and said nothing.

### F-0068 — The fiscal thresholds were annotated with numbers twice their actual value

**Claim.** `USADashboard` computed its warning and crisis yields correctly and
annotated them wrongly:

```js
const BREAK = breakingPointRate(); // ~5.5%
const CRISIS = crisisRate();       // ~8.5%
```

The actual values are **11.25%** and **19.42%**.

**Artifact.** `(0.25 × 4.9 − 0.55) / 6.0 × 100 = 11.25`;
`(0.35 × 4.9 − 0.55) / 6.0 × 100 = 19.42`. Verified as assertions in
`lib/fiscal.test.js`.

**Sample size.** Two comments.

**What was and was not wrong.** The code was right and the screen was right —
the page has always printed 11.3% and 19.4%. Only the comments were wrong, by
roughly a factor of two, on the panel that states the application's central
thesis. A reader checking the reasonableness of the model against its own
annotation would have concluded the code was broken.

**Fixed.** The constants and the arithmetic are in `lib/fiscal.js`, and the
test asserts the rough figures rather than a comment claiming them. If a
constant changes, the assertion moves with it.

### F-0069 — A default parameter evaluated before the guard meant to prevent it

**Claim.** `yearAgo(series, index = series.length - 1)` throws on an absent
series, because a default parameter is evaluated before the function body and
therefore before `if (!series?.length) return null`.

**Artifact.**

```
TypeError: Cannot read properties of undefined (reading 'length')
 ❯ yearAgo src/lib/usaSeries.js:47:48
 ❯ USADashboard src/pages/USADashboard.jsx:63:17
```

**Sample size.** One signature. Reachable whenever the CPI pipeline has not
run, since the dashboard calls it for `CPIAUCSL` unconditionally.

**Caught by the net, not by review.** The tab render tests from `D-0054` are
the reason this is a note rather than a white screen on the COUNTRY tab. They
prove only that each tab mounts — which is exactly what this broke.

**Fixed.** The guard comes first and the default is computed inside the body.

### F-0070 — A second Vite config inside src/, never loaded, describing a build that does not happen

**Claim.** `ui/src/vite.config.js` sat beside `App.jsx` and was never read.
Vite resolves its config from the project root — `ui/` — so
`ui/vite.config.js` is the live one and this was inert.

**Artifact.** It declares `outDir: '../api/static'`, which from `ui/src/`
resolves to `ui/api/static`. That directory does not exist. The real build
writes `ui/dist/`:

```
ui/dist/assets/index-BD1XHaL1.js
ui/api does not exist
```

It also declares a dev proxy forwarding `/api` to `http://localhost:8000`.
The live config has no `proxy` key at all — `grep -c proxy ui/vite.config.js`
→ **0**.

**Sample size.** One file, present since `8a0a163`.

**Why an unused file is worth a finding.** Both of its claims are things a
developer would rely on without checking. Its comment says the output path
"avoids CORS issues" and means `fly deploy` needs "no manual copy step" —
while the Dockerfile and CI both perform exactly that manual copy, and the
app resolves its base URL through `lib/api.js` rather than through a proxy.
It is a confident description of an architecture the project does not have,
sitting in the directory where someone would look for one.

This is `F-0037` in miniature: work proceeding from a document that was true
once and is not checked against the tree.

**Fixed.** Deleted. `ui/src/architecture.test.js` now fails if any file
outside `lib/api.js` spells an absolute API host, which is what surfaced it —
the guard was written for `F-0052` and caught this instead.

### F-0071 — Every date on every chart displayed a day early, west of UTC

**Claim.** `formatDate` did `new Date(d).toLocaleDateString(...)`. ECMAScript
defines a bare `YYYY-MM-DD` as **UTC midnight**, and `toLocaleDateString`
renders it in the viewer's zone — so anywhere west of UTC, every date on every
axis, tooltip and footer was one day early.

`pivotByDate` strips the time from the API's `2026-08-01T00:00:00`, which is
correct for a date-keyed join, and that is what leaves `formatDate` holding a
bare date.

**Artifact.** Reported by the owner as *"My latest data is July 31"* for Fed
Funds. Production held `2026-08-01`. End to end:

```
API gives:      2026-08-01T00:00:00
pivotByDate ->  2026-08-01
formatDate  ->  Jul 31, 26
```

Across zones:

```
America/Los_Angeles    getDate() = 31   renders as Jul 31, 26
UTC                    getDate() = 1    renders as Aug 1, 26
```

**Sample size.** One function, 15 call sites, five files. Every date the UI
shows.

**Why it read as much worse than one day.** On a daily series, one day early
is a rounding annoyance. On a **monthly** series it crosses a month boundary:
FRED dates a monthly average to the first of the month, so August's fed funds
figure rendered as "Jul 31" — a one-month-old number looking two months old,
and a healthy pipeline looking stalled.

**The part worth more than the fix.** *The bug does not exist at UTC, and CI
runs at UTC.* Old code and new code are byte-identical in behaviour there, so
no assertion could have distinguished them on the machine that gates merges.
A guard written without noticing that would have been green forever while the
defect sat in production — `F-0006`'s shape, in a dimension nobody was
looking at.

**Fixed.** `asLocalDate` takes the calendar day from the string rather than
from a timezone conversion. Every date in this application is a calendar
date — the day an observation is attributed to — not an instant.

`vite.config.js` now pins the suite to `TZ=America/New_York`, and
`format.test.js` asserts that pin is in force before relying on it: if the
timezone ever stops taking effect, one test says so rather than five quietly
becoming decoration. Reverting the parse turns all five red:

```
AssertionError: expected 6 to be 7
AssertionError: 2026-08-01: expected 31 to be 1
```

**Not fixed here.** Only display. Nothing stored, scored or compared used
`formatDate`, and `priorObservation`, `yearAgo` and `pivotByDate` all compare
date strings or `Date.parse` results symmetrically, so no arithmetic shifted.

### F-0072 — The Fed Funds card was 25bp wrong, not merely a month stale

**Claim.** The MARKETS Fed Funds card read `FEDFUNDS`, FRED's monthly average.
On 2026-09-29 it displayed **3.63%**. The effective federal funds rate was
**3.88%**, and the Fed's target range was **3.75–4.00%**.

**Artifact.** Production database:

```
2026-08-01 3.63000000
2026-07-01 3.63000000
2026-06-01 3.63000000
```

Live FRED, queried the same day:

```
DFF        latest 2026-09-25  value 3.88
EFFR       latest 2026-09-28  value 3.88
DFEDTARU   latest 2026-09-29  value 4
DFEDTARL   latest 2026-09-29  value 3.75
FEDFUNDS   latest 2026-08-01  value 3.63
```

**Sample size.** One card, one day, one 25bp gap. The gap opens whenever the
Fed moves and closes the following month, so its size is a function of when
you look rather than of anything being broken.

**Why `A-0013` understated it.** That assumption was written the same day and
called this a disclosure problem — the grid does not distinguish monthly cards
from daily ones, so a monthly card reads as a stale daily one. True, and not
the whole thing. A reader who fully understood that `FEDFUNDS` is last
month's average would *still* be reading 3.63% on a board where the fiscal
calculator converts yields into an interest bill and the scenario panel argues
about the Fed's next move. Disclosure fixes the misreading. It does not fix
the number.

**Found by the owner asking twice.** The first question — *"my latest data is
July 31"* — was answered by `F-0071`, a genuine display defect, and by the
observation that `FEDFUNDS` is monthly by construction. Both were true, and
together they were a complete-sounding answer that stopped one question short.
The second question, *"isn't there a daily fed funds ticker?"*, is the one
that produced this. There is; it is `DFF`; it was never ingested.

**The shape worth remembering.** Two correct explanations can compose into a
wrong conclusion. "The display was off by one day" and "the series is monthly
by design" are both accurate, and together they account for the symptom
entirely — which is exactly what made it easy to stop there rather than ask
whether the right series was being shown at all.

**Fixed** by `D-0057`. Guarded by a test asserting every card's code is
fetched by some pipeline.

### F-0073 — The unique index on `timeseries` has never constrained a macro series

**Claim.** `ix_metric_country_date` is a UNIQUE index on
`(metric_id, country_id, date)`. Postgres treats NULLs as **distinct** in a
unique index, and every macro series stores `country_id IS NULL`. So the index
exists, reads as correct, and has never rejected a duplicate for any of them.

**Artifact.**

```
ix_metric_country_date | CREATE UNIQUE INDEX ix_metric_country_date
  ON public.timeseries USING btree (metric_id, country_id, date)
```

Against that index, in the same database:

```
DFF              groups=1174   excess=1174
DTWEXBGS         groups=5      excess=5
DGS10            groups=4      excess=4
DGS2             groups=3      excess=3
DGS5             groups=3      excess=3
DFII10           groups=1      excess=1
```

67,332 rows, **1,190 exact duplicates**. Every DFF row has
`country_id IS NULL` — 2,996 of 2,996.

**Sample size.** Six metrics. Five of them — 16 rows — predate anything done
today and accumulated through ordinary nightly pipeline runs.

**How it was found, and the part I own.** Backfilling `DFF` for `D-0057` I ran
a check-then-insert loop against production concurrently with the scheduled
FRED run, and **created 1,174 of those duplicates myself**. The pre-existing
16 are what the same race produces at nightly cadence; my bulk insert
reproduced a year of it in one run. I would not have looked at this index
today without that.

**Why it is `P6`, not a schema nit.** *A guard that stands aside is not a
guard.* This one is worse than absent: `pipelines/fred_fetcher.py` does
check-then-insert with no `ON CONFLICT`, which is a race by construction, and
the reason nobody has fixed that is presumably the unique index sitting there
looking like it has the problem covered. An absent constraint invites the
question. A present, non-binding one closes it.

**Currently harmless to display, which is its own hazard.** `pivotByDate`
keys by date, so the MARKETS ticker and chart collapse duplicates and show the
right numbers. `byMetric` keeps both points, but the values are identical, so
the USA charts draw the same line and `latestValue` is still correct. Nothing
on screen is wrong today. The damage is that row counts are inflated, any
future aggregate over `timeseries` is wrong, and the broken constraint stays
invisible.

**Not fixed.** `docs/ddl/2026-09-29-timeseries-unique-nulls-not-distinct.sql`
holds the two statements — deduplicate, then recreate the index with
`NULLS NOT DISTINCT` (production is Postgres 16.14, which supports it).
Verified first that no duplicate group holds more than one distinct value, so
the deletion discards nothing; and everything here is re-fetchable from FRED,
so the worst case is a pipeline re-run.

The `DELETE` was **refused by this session's safety classifier** as a bulk
delete against production, and is left for the owner to run rather than
worked around.

**Remaining half.** Converting the fetcher to an upsert. With the index in
place the race becomes a loud `IntegrityError` caught per-metric and reported
as `partial`, instead of silent duplication — which is the right failure mode,
but it is a failure mode, not a fix.

**Half closed 2026-09-29.** The owner authorised the deletion only, and it
ran:

```
groups with more than one distinct value: 0
before=67332 deleted=1190 after=66142
duplicate groups remaining: 0
```

Every affected metric now has one row per date:

```
DFF        rows=1822   distinct_dates=1822   latest=2026-09-25
DFII10     rows=1314   distinct_dates=1314   latest=2026-09-25
DGS10      rows=1315   distinct_dates=1315   latest=2026-09-28
DGS2       rows=1315   distinct_dates=1315   latest=2026-09-28
DGS5       rows=1315   distinct_dates=1315   latest=2026-09-28
DTWEXBGS   rows=1315   distinct_dates=1315   latest=2026-09-25
```

**The finding stays open, and this is the important part.** The data is clean;
the *constraint* is not fixed. `ix_metric_country_date` still treats two NULL
`country_id`s as different countries, and `fred_fetcher.py` still does
check-then-insert with no `ON CONFLICT`. Nothing prevents the duplicates
returning at the rate that produced the original 16 — a handful per month,
quietly, exactly as before.

A cleanup without the constraint is a reset, not a repair. Recording it as
closed on the strength of `deleted=1190` would be the shape `F-0006` warned
about: a number that looks like a result standing in for a guarantee nobody
has.

Statement 2 of the DDL file — recreating the index with `NULLS NOT DISTINCT`
— remains unapplied and unauthorised, and the file's STATUS block says so at
the top so the next reader does not assume the whole file ran.

**Proximate cause identified 2026-09-29, and it was mine.** `update_logs`
shows the FRED pipeline running on **every application startup** — six runs
matching six deploys within one hour:

```
success  ins=0      upd=14768  17:41:24
success  ins=0      upd=14768  17:27:10
success  ins=1822   upd=12946  17:18:58   <- DFF, backfilled by the deploy itself
success  ins=0      upd=12946  17:07:12
success  ins=0      upd=12946  16:57:58
success  ins=0      upd=12946  16:45:56
```

`main.py`'s lifespan calls `start_scheduler()`, which queues a one-shot FRED
job (`D-0019`). So the deploy of `D-0057` fetched `DFF` by itself at 17:18:58,
inserting all 1,822 rows. The manual backfill I ran landed inside that
two-minute window, checked for rows the pipeline had not yet committed, and
inserted 1,174 duplicates.

**The backfill was not merely racy — it was unnecessary.** The deploy already
does it. A step taken because it seemed obviously required, without checking
whether the system already performed it, and the check was one query away.

This does not change the finding: the index has never constrained these rows
and the 16 pre-existing duplicates arrived without any help from me. It does
mean the loud version of this defect had an avoidable trigger, and that
`D-0058` needs **no manual backfill at all** — deploying it is the backfill.

**CLOSED 2026-09-29.** The owner authorised statement 2 and it ran, after the
preconditions were checked in the same session: 0 pipeline runs in flight,
0 duplicate groups. `DROP` and `CREATE` executed in one transaction, so there
was no window in which the table had no unique index.

```
CREATE UNIQUE INDEX ix_metric_country_date ON public.timeseries
  USING btree (metric_id, country_id, date) NULLS NOT DISTINCT
```

**Verified to bind, not assumed.** The entire finding was that a constraint
can exist and reject nothing, so the index was made to reject something before
it was believed — a duplicate of a country-less `DFF` row, attempted inside a
transaction that was rolled back either way:

```
RESULT: rejected -> IntegrityError
        duplicate key value violates unique constraint "ix_metric_country_date"
COUNTRY-SCOPED: still rejected -> IntegrityError
rows after rollbacks: 66400
```

The second line matters as much as the first: the rows the old index *did*
protect are still protected. A fix that quietly traded one gap for another
would have looked identical from the first assertion alone.

**And a fresh database cannot drift back.** `database/models.py` now declares
`postgresql_nulls_not_distinct=True`, so `create_all()` emits the same index
on any new deployment, and `tests/test_timeseries_uniqueness.py` asserts the
compiled Postgres DDL contains `NULLS NOT DISTINCT`.

**Stated rather than left to be discovered:** SQLite shares Postgres' default
NULL semantics and ignores the dialect kwarg, so the in-memory databases this
suite runs against do **not** enforce this. A test that inserted a duplicate
into SQLite and passed would prove the opposite of what it claimed, which is
why the assertion is on the emitted DDL and the runtime behaviour was checked
against production directly.

**One consequence to watch.** `pipelines/fred_fetcher.py` still does
check-then-insert with no `ON CONFLICT`. With the constraint binding, two
overlapping FRED runs no longer duplicate silently — they raise
`IntegrityError`, the per-metric handler catches it, that metric's batch rolls
back and the run is logged `partial`. That is the correct direction (loud
rather than silent, no data loss, since the other run wrote the rows) but it
is a failure mode rather than a fix. Converting the insert to an upsert is the
remaining work and is **not** done.

**Remaining half closed 2026-09-29 by `D-0059`.** `fred_fetcher.py` now writes
through `ON CONFLICT DO UPDATE` on Postgres, so two overlapping runs converge
on the same row instead of racing to insert it. The `partial`-on-IntegrityError
failure mode described above no longer applies.

`F-0073` is fully closed: the duplicates are gone, the constraint binds, the
model declares it so a fresh database inherits it, and the writer no longer
depends on a check that was true a moment ago.

### F-0074 — The CDS dimension scored months-old placeholders, and one number that is not a spread

**Claim.** `get_cds_score` read the latest stored CDS value with no regard for
its age or its plausibility. Three consequences, all live in production on
2026-09-29:

**1. Every 10Y series was the ISDA running coupon.**

```
distinct 10Y values ever recorded:
  value=     500.0  rows=111
  value=      77.2  rows=7
```

Germany, Japan, Switzerland and the United States all at 500bps. Germany's
real 10Y CDS is around 10bps. Frozen since 2026-07-16.

**2. Saudi Arabia's composite score was entirely a placeholder.**
`SAUDI_ARABIA_CDS_5Y` held seven rows of `500.0`, also frozen at 2026-07-16.
It scored 10 points — **100% of Saudi Arabia's composite score of 10.0**. The
country appeared on the COMPOSITE tab solely because a missing-data sentinel
was read as a spread.

**3. Russia's 13,775bps is not a running spread.**

```
RUSSIA_CDS_5Y: every distinct value ever recorded
     156.9  n=7   2026-07-10 .. 2026-07-16
   13775.2  n=23  2026-09-01 .. 2026-09-29
```

Two values in thirty observations, then frozen to one decimal for 23
consecutive days *including weekends*. 13,775bps is 137.75%, which a running
spread cannot be — past 100% of notional a credit is quoted points-upfront.
Russia's CDS triggered and settled at auction after the 2022 default, so
there is no live 5Y running spread to quote. It earned the **maximum 20
points**, inside a CRISIS score of 179.7, and its pairing with the frozen
July 10Y produced a term-structure inversion of −13,698bps that fed both the
score and the CDS tab's *Inverted Curves* tile.

**Sample size.** 21 5Y series, 17 10Y series. The rest of the 5Y board is
entirely sound — Switzerland 7.5, Germany 9.6, Japan 25.3, US 33.8, Brazil
129.6, Turkey 248.1, Egypt 307.3 — which is what makes the two outliers
diagnostic rather than ambiguous.

**The part worth keeping.** `pipelines/cds_fetcher.py` already refuses to
produce any of this. Its docstring says so: the ISDA running coupon
(25/100/500/1000) is not to be mistaken for the spread, and WGB's 5Y board
has no paired 10Y so term structure stays blank. The writer was fixed. The
rows the old writer had left behind were never removed, and **the reader had
no staleness bound**, so a corrected pipeline kept producing wrong scores out
of its own history for two and a half months.

*Fixing the writer does not fix the reader.* That is the generalisable part:
a pipeline fix is only half a data fix, and nothing in this codebase was
checking the other half.

**Fixed.** `admit_cds_quote()` rules on each tenor independently — a quote is
admitted only if it is newer than `MAX_CDS_AGE_DAYS` (10, wide enough to
absorb a long weekend plus an outage) and below `MAX_PLAUSIBLE_CDS_BPS`
(10,000 — 100% of notional). Per-tenor is load-bearing: the 10Y board stopped
in July and the 5Y did not, and judging the pair together would either keep
the dead 10Y or discard the live 5Y.

A refusal returns **why**, not a boolean, and the reason reaches the UI as
`cds_coverage`. A country nobody quotes and a country whose quote was thrown
away both score zero, and the reader has to be able to tell which happened.

**Not done here.** The stale rows are still in the database. They no longer
score and no longer display, which is the urgent half; deleting them is a
separate authorised action.

### F-0075 — A pipeline that reported `partial` on every run, for a permanent reason

**Claim.** Every `CDS_MultiTenor` run logged `partial`, always for the same
cause: `SAUDI_ARABIA_CDS_5Y: not on World Government Bonds 5Y board`. Saudi
Arabia is configured in `CDS_INSTRUMENTS` and has never been on that board, so
`attempted` counted it and `ok` never could.

**Artifact.**

```
CDS_MultiTenor   partial  ins=0     2026-09-29 19:03:10
CDS_MultiTenor   partial  ins=0     2026-09-29 18:10:11
CDS_MultiTenor   partial  ins=1     2026-09-29 17:57:21
CDS_MultiTenor   partial  ins=0     2026-09-29 17:41:24
CDS_MultiTenor   partial  ins=0     2026-09-29 17:27:10
```

**Sample size.** Every run in the log.

**Why it matters.** A status that never changes carries no information. A run
that genuinely lost half the board would report `partial` too, and would be
indistinguishable from this. The pipeline had a health signal and it had been
pinned to "unwell" for so long that it could not report illness.

This is `F-0006`'s shape again — a check whose answer cannot change — arriving
from the opposite direction. There, tests outside the gate read as coverage.
Here, a permanent fault reads as a status.

**Fixed.** `KNOWN_ABSENT_FROM_5Y_BOARD` makes it a recorded exclusion: kept
out of `attempted`, logged once per run at info, and surfaced as `skipped` in
the result so the exclusion is visible rather than merely silent.

**And the exclusion re-checks itself.** If a known-absent name *does* appear
on the board, the run logs a warning saying the exclusion is out of date. An
exclusion nobody re-validates becomes the next stale artefact, which is the
whole subject of `F-0074` sitting directly above this.

### F-0076 — The methodology panel explained four dimensions of a six-dimension model

**Claim.** The COMPOSITE tab's panel is headed `SCORE =` and listed Treasury,
Gold Reserves, Sovereign Spread and Petrodollar. The scorer sums six:

```
raw_score = tic_score + gold_score + monetary_score
          + spread_score + petro_score + cds_score
```

Monetary/M2 (0-35), Sovereign CDS (0-20) and the non-dollar reserve
multiplier (dimension 6) appeared nowhere in the explanation.

**Artifact.** The listed parts cap at 130. The raw maximum is **185**, before
a multiplier of up to 2.0 and a further 1.2x for rebuilding non-dollar
reserves, capped at 150. Turkey scored 178.0 against a panel that could not
account for more than 130.

**Sample size.** One panel, two missing dimensions and one missing multiplier.

**Why CDS is the one that mattered.** It is dimension 7, worth up to 20
points, and for Brazil it is **100% of the composite score** - the country is
ranked because of its CDS spread and nothing else. A reader looking for why
Brazil appeared on the board would have found no dimension in the panel that
could produce it.

This is why the answer to *"is the CDS surface telling any of the sovereign
stress story?"* was yes and invisible at the same time. The signal was
load-bearing; the explanation omitted it.

**Same shape as `F-0068`.** There, comments annotated the fiscal thresholds
with numbers twice their real value. Here, a panel annotated the model with
two-thirds of its dimensions. In both cases the code was right, the screen was
right, and the explanation beside it was wrong - which is the failure mode
that survives testing, because nothing tests prose.

**Fixed.** `ui/src/lib/dimensions.js` is the single list, rendered by the
panel and by the per-country breakdown. `tests/test_composite_dimensions.py`
parses it and cross-checks the keys and caps against
`pipelines/composite_stress.py` **in both directions** - a dimension the
scorer sums and the panel omits fails, and so does a dimension the panel
claims and the scorer does not compute.

Verified to bite by deleting the CDS entry:

```
AssertionError: 'cds_score' not found in {'tic_score': 50, ...}
```

### F-0077 — A shared rule was tested once and called twice

**Claim.** `admit_cds_quote` is deliberately shared by the composite scorer
and by `GET /api/cds/all`, so the two cannot judge the same rows differently
(`F-0074`). They read `as_of` from different places, and only one of the two
types was ever tested.

**Artifact.** Live, immediately after deploying `D-0060`:

```
TypeError: unsupported operand type(s) for -:
'datetime.datetime' and 'datetime.date'
  File "/app/api/routes.py", line 790, in get_all_cds
  File "/app/pipelines/cds_fetcher.py", line 108, in admit_cds_quote
```

The scorer reads `TimeSeries.date` — a `datetime`. `/cds/all` reads
`latest_cds_observation` — a `date`. Eleven tests covered the rule and every
one of them passed a `datetime`.

**Sample size.** One function, two callers, one input type tested.

**The lesson, stated so it generalises.** Sharing a rule between two callers
is what makes `F-0074`'s guarantee real — one rule, one verdict. But the
sharing is exactly what makes per-rule testing insufficient: a rule with two
callers needs a case **per caller**, not per rule. The tests were thorough
about the rule's logic (staleness boundary, plausibility ceiling, distinct
refusal reasons) and silent about its interface.

**Fixed.** `as_of` accepts a `date` or a `datetime`, normalising a bare date
to midnight. That is correct rather than a workaround: these are calendar
dates — the day a quote is attributed to — and the comparison is in whole
days. The same reasoning as `F-0071`.

Four new tests push both types through every verdict and assert the two agree.

**What went right, and it is worth recording.** The CDS tab rendered
**"Could not load CDS data — 500 Internal Server Error"**, not an empty
table, because `F-0063` had made an HTTP error stop being a resource earlier
the same day. Before that change this defect would have rendered as a blank
CDS table, which reads as *no country has a CDS spread* — on a tab whose
entire subject is sovereign default risk.

The guard was built for a defect that already existed and caught a different
one that did not exist yet.

### F-0078 — The country panel's CDS tile was never once correct

**Claim.** `GET /api/cds?country=` built its metric code as
`f"{country.upper()}_CDS_5Y"`. CDS metrics encode the country by **name** —
`TURKEY_CDS_5Y`. The endpoint's own docstring says the parameter is a
*"Country ISO code (e.g. TUR, MEX, BRA)"*. Both cannot be true.

**Artifact.** Against production, before the fix:

```
/cds?country=TUR      -> 5Y=None  No CDS data available for this country
/cds?country=BRA      -> 5Y=None  No CDS data available for this country
/cds?country=EGY      -> 5Y=None  No CDS data available for this country
/cds?country=TURKEY   -> 5Y=248.08
/cds?country=BRAZIL   -> 5Y=129.57
```

`CountryDetail` is the only caller and passes an ISO code.

**Sample size.** Every country, every time. The 5Y CDS tile on the country
panel has **never displayed a value**.

**Why it went unnoticed for so long.** "No coverage" is a legitimate answer
for most countries — 21 of 105 are on the board at all — so a tile that always
said it looked exactly like a tile that was working. **A wrong answer that is
also a plausible answer does not get reported.** That is the same property
that let `F-0074`'s placeholders survive: a number is checked, an absence is
not.

**Fixed.** The lookup resolves an ISO code through `CDS_NAME_BY_ISO` and falls
back to the raw token, so both forms work. `tests/test_cds_country_lookup.py`
checks the map against the fetcher's instrument list in **both** directions —
a mapping to a token nothing stores, and a country on the board no ISO can
reach — plus that no ISO key doubles as a namespace token, which would resolve
by accident and mask a missing entry.

This was also the **third** reader of CDS rows with no admissibility check;
it now applies the same `admit_cds_quote` as the scorer and `/cds/all`.

### F-0079 — Two of the six scored dimensions cannot fire

**Claim.** Measured across all 48 scored countries:

| dimension | countries scoring | total points | max |
|---|---|---|---|
| Treasury | 44 | 1015.9 | 50 |
| Gold Reserves | 4 | 70.7 | 40 |
| Monetary / M2 | 6 | 70.0 | 35 |
| **Sovereign Spread** | **0** | **0.0** | 20 |
| **Petrodollar** | **0** | **0.0** | 20 |
| Sovereign CDS | 4 | 25.0 | 20 |

**Sovereign Spread is structurally dead, not merely quiet.** It scores a
country more than 50bps **above** the US 10Y. It has sovereign yield data for
exactly the fourteen countries in `SOVEREIGN_YIELD_CODES` — all developed
markets — and every one of them is **below** the US:

```
AUS   -22.5bps    FRA  -124.0bps
GBR   -25.1bps    ITA  -125.4bps
NOR   -95.4bps    BEL  -148.0bps
KOR   -95.4bps    CAN  -156.5bps
```

The dimension can only fire for emerging markets, and it holds no yield data
for any of them. Twenty points that cannot be scored by anyone.

**Sample size.** 48 countries, 14 with a computed spread, 0 scoring.

**Petrodollar is conditional rather than structural** — it needs Brent falling
alongside TIC selling, and Brent currently is not. It can fire; the spread
dimension cannot.

**Why this matters beyond the two dimensions.** Treasury contributes **1,015.9
of roughly 1,182 total points — 86%**. The model presents itself as
six-dimensional and is, in practice, one dimension plus decoration. The
methodology panel now lists all six honestly (`F-0076`), which makes this
visible rather than fixing it.

**Not fixed.** Retiring or repairing a scoring dimension is a modelling
decision, recorded in `A-0014` for a ruling.

### F-0080 — Implied PD is the spread rescaled, and the source's own PD column proves Russia is not a spread

**Claim.** The WGB board publishes an implied 5-year probability of default
beside every spread. Across all 30 names it is the spread times a constant —
about 1/60:

```
country          5Y bps      PD%     PD/bps
Sweden             7.36     0.12    0.01630
Germany            9.64     0.16    0.01660
Mexico            91.03     1.52    0.01670
Brazil           124.90     2.08    0.01665
South Africa     130.86     2.18    0.01666
Turkey           245.17     4.09    0.01668
Egypt            307.29     5.12    0.01666
Russia         13775.17   100.00    0.00726
```

**Two conclusions, and the second is the interesting one.**

**PD is not independent information.** It is a rescaling, so scoring it would
double-count the CDS level band exactly. It is carried and displayed because
*"a 2.18% chance of default"* means something to a reader and *"130.86bps"*
does not — readability, not signal. `tests/test_cds_board_columns.py` asserts
the ratio holds and asserts `composite_stress.py` never reads the PD series.

**Russia breaks the ratio because the source clamps its own column at
100.00%.** 13,775.17 × 0.01666 would be 229%, which is not a probability, so
the board caps it. The source's own model refuses to interpret the number as a
spread — which is independent corroboration of `F-0074`'s refusal, arrived at
from the opposite direction and without any assumption of mine.

**Sample size.** 30 names on the live board; the stored fixture corroborates
the same ratio at 0.01652–0.01717.

**What it changes.** Nothing scores differently. It settles what PD is for, so
the next person to see a probability column does not wire it into the model as
a second opinion.

### F-0082 — The composite response model silently dropped eleven fields, including the whole CDS dimension

**Claim.** FastAPI's `response_model` is a **filter**, not a completeness
check. Any key the model does not declare is removed from the response, with
no error anywhere. `CompositeCountry` declared 33 fields;
`compute_composite_stress` produced 44.

**Artifact.**

```
scorer produces: 44 | model declares: 33

STRIPPED BY THE RESPONSE MODEL:
    active_signals = ['EXITED: Zero US Treasuries - 535t gold', ...]
    as_of = '2025-12'
    brent_3m_pct = 60.5
    brent_price = 114.89
    cds_10y = None
    cds_5y = 248.1
    cds_coverage = 'quoted'
    cds_coverage_10y = 'no coverage'
    cds_score = 5
    cds_term_spread = None
    cds_widening_pct = -50.4
```

**Sample size.** One model, eleven fields, three UI surfaces.

**What it actually broke.** Reported by the owner as *"I'm not seeing any CDS
data on the composite stress UI surface"* and *"Activity gets the lion's share
of the real estate and there's not many comments there"*. Both are the same
defect:

* The COMPOSITE table's **CDS 5Y** column, the CDS tab's **CDS Share** column
  and the country panel's **StressContribution** breakdown all read
  `cds_5y` / `cds_score`. The API removed both on the way out. All three
  rendered a dash for every country.
* The **Activity** column renders `active_signals`. Also removed. It was the
  widest column on the table and empty in every row.

**So `D-0060` was never visible in production.** The tie-in work — CDS shown
as a share of the score, on three surfaces — shipped, passed its tests, and
displayed nothing.

**Why the tests did not catch it, which is the part worth keeping.** Every
frontend test stubs `fetch` and supplies the response shape itself. A stub
written from the scorer's output proves the component renders *that* shape; it
proves nothing about whether the server sends it. **The stub was defining the
contract instead of the server.**

That is a general hazard of component tests against a stubbed API, and it is
invisible from inside the frontend: the tests are green, the component is
correct, and the screen is empty.

**Fixed.** The eleven fields are declared.
`tests/test_composite_response_contract.py` parses the scorer's
`results.append({...})` keys and compares them to the model's fields **in both
directions** — a produced-but-undeclared field is silently dropped, and a
declared-but-never-produced field renders as a default, which reads as a real
value rather than an absent one.

The check is static, so it needs no database and — the point — **cannot be
satisfied by a stub**.

### F-0081 — The COMPOSITE table described a model that had been retired underneath it

**Claim.** Four decisions changed the scoring model in one session —
`D-0062`, `D-0065`, `D-0066`, `D-0067` — and the COMPOSITE table's column
tooltips went on describing the old one.

**Artifact.** In `CompositeTab.jsx` after all four:

* The **CDS 5Y** tip: *">100bps = 5 pts; >250bps = 10 pts; >500bps = 15 pts"*.
  The ladder was 200/350/600.
* The **Spread** tip: *">50bps = 5 pts; >100bps = 10 pts; >200bps = 15 pts"*
  for a dimension `D-0066` had retired from scoring entirely.
* The **Country** tip: *"scored across all seven stress dimensions"*. Five.
* A **CDS Term** column, with a tooltip explaining the inverted-curve bonus,
  for a tenor `D-0062` had established the source does not publish.

**Sample size.** Four tooltips and one entire column, on the tab that explains
the model.

**Same shape as `F-0068` and `F-0076`, for the third time.** The code was
right, the screen's numbers were right, and the prose beside them was wrong.
Nothing tests prose — so the fix is not to correct the prose but to stop it
being prose.

**Fixed.** The CDS ladder is `CDS_BANDS` in `ui/src/lib/dimensions.js` and the
tooltip is generated from it. `tests/test_composite_dimensions.py`
cross-checks those bands against `CDS_ELEVATED_BPS`, `CDS_SIGNIFICANT_BPS` and
`CDS_DISTRESS_BPS` in the scorer, and separately asserts that the specific
stale strings are absent from the file. Verified to bite:

```
AssertionError: Lists differ: [200.0, 250.0, 600.0] != [200.0, 350.0, 600.0]
```

The Spread tip now says it is measured and not scored, and says why.

### F-0083 — "Data as of 2025-12" was true, and told the reader nothing

**Claim.** The COMPOSITE tab's footer read `Data as of 2025-12`. That data was
**302 days old**, and the sentence gave no way to know it. TIC is normally one
to two months behind, so a December date on a monthly series reads as ordinary.

**Artifact.** The pipeline had been saying so, loudly, in a place the reader
never looks:

```
TIC source at https://ticdata.treasury.gov/Publish/mfhhis01.txt is stale:
newest row 2025-12-01 is 302 days old, limit is 100. The fetch and parse
both succeeded - the upstream file is frozen, or the URL now points at a
historical year rather than the current release. See F-0050.
```

Every TIC run since has reported `failed`. The guard works. The screen did not
carry what the guard knew.

**Why it matters more than a footer usually would.** Treasury contributes
**1,015.9 of roughly 1,182 composite points — 86%** (`F-0079`). The dominant
dimension of this application is computed from ten-month-old holdings, and the
only surface that mentioned it printed a date a reader would find unremarkable.

**The source, confirmed.** `mfhhis01.txt` fetches cleanly — 200, 99KB — and
its header rows are:

```
        Dec    Nov    Oct    Sep    Aug    Jul    Jun    May    Apr    Mar    Feb    Jan
Country 2025   2025   2025   2025   2025   2025   2025   2025   2025   2025   2025   2025
```

It is the **complete calendar-year 2025 file**, exactly as `F-0050`'s error
message hypothesised. `mfhhis02.txt` through `mfhhis12.txt` are all 404.
`mfh.txt` exists and is older still, covering Jan 2022 to Jan 2023. No
`_2026` variant responds.

**I could not locate the current release.** That is stated as a limit rather
than a conclusion: the URL patterns derivable from the configured one all
either 404 or return historical files, and Treasury's TIC landing page is not
something this session could enumerate. Whether a 2026 file exists elsewhere
is open.

**Fixed, partially.** `lib/freshness.js` computes an age and the footer
carries it: *"Data as of 2025-12 (302 days old — the TIC source has not
published since then; Treasury scores are computed from it)"*, in
failure-red. `TIC_TOLERANCE_DAYS` is 100, deliberately the same number as
`MAX_SOURCE_AGE_DAYS` in the pipeline, so the screen and the log cannot
disagree about what "too old" means. An ordinary two-month lag stays grey —
colouring a normal cadence red trains the reader to ignore the colour.

**A DST bug, caught by its own test.** The first `ageInDays` subtracted two
local `Date`s and floored. December to September crosses a clock change, so
the difference is 302 days *minus an hour* and the floor returned **301**. Both
endpoints are now `Date.UTC` midnights differenced in whole days. Calendar
arithmetic on local `Date`s is off by one whenever the span crosses a
transition — the same hazard as `F-0071`, one layer up.

**Not fixed.** The data. A footer that admits the problem is not a fix for the
problem, and the Treasury dimension is still running on December 2025.

### F-0084 — The analyst brief credited one provider, called another, and could authenticate neither

**Claim.** Three things disagreed about the analyst brief, and nothing
compared them:

| | said |
|---|---|
| the UI footer | *"Generated by Claude Haiku"* |
| `api/routes.py` | `POST https://api.x.ai/v1/chat/completions`, `grok-2-latest` |
| the deployment | `ANTHROPIC_API_KEY` set, `GROK_API_KEY` absent |

**Artifact.** The handler opened with:

```python
if not settings.grok_api_key:
    raise HTTPException(status_code=503, detail="GROK_API_KEY not configured")
```

and `flyctl secrets list` returns `FRED_API_KEY`, `ANTHROPIC_API_KEY`,
`AUTH_PASSWORD`, `AUTH_USERNAME`, `DATABASE_URL`. No Grok key.

**Sample size.** Every brief request ever made against production. Reported by
the owner attempting one for Germany.

**Why it survived.** `architecture.md` already recorded that `GROK_API_KEY`
was unset and that the brief therefore 503s — the fact was *written down* and
treated as a known limitation rather than as a mismatch to resolve. Meanwhile
the key that would have worked was sitting deployed, and the UI had been
naming that provider in its footer the whole time.

A documented defect is not a fixed one, and documenting it removed the
pressure to look at the adjacent line where the answer was.

**Fixed** by `D-0069`. `tests/test_analyst_brief_wiring.py` now compares all
three: the endpoint called, the key guarded on, and the model the UI credits —
parsing the footer's *"Generated by X"* and asserting every word of it appears
in `BRIEF_MODEL`. A UI that credits a provider the code does not call fails.

**Extended 2026-09-29 — the same date, on two more tabs.** Reported as
*"Holdings data says Dec 2025"*. HOLDINGS and CROSS-ASSET print the same
TIC-derived date, each formatting it inline and each equally silent about its
age. The HOLDINGS stat tile showed `Dec 2025` with nothing beside it.

All three now use one `DataAsOf` component. Three copies of a freshness rule
is how two of them end up disagreeing (`F-0062`, `F-0081`), and the rule here
is not obvious: an ordinary one-to-two-month TIC lag must stay grey, because
colouring a normal cadence red trains the reader to ignore the colour.

The component knows the age; the tab supplies what being stale *means there* —
"every holding below is that old" on HOLDINGS, "the Treasury side of every
signal here is that old" on CROSS-ASSET.

### F-0085 — The Grok model had been retired, and the error path could not say so

**Claim.** `BRIEF_PROVIDERS["grok"]` named `grok-2-latest`. xAI has retired
it. The key the owner had just deployed authenticated correctly - the failure
was a **404 on the model**, not a 401 on the key.

**Artifact.**

```
status: 404
{"code":"not-found","error":"The model grok-2-latest does not exist or your
team ... does not have access to it."}
```

What the key can actually reach:

```
grok-4.3  grok-4.5  grok-4.6  grok-4.7
grok-4.20-0309-non-reasoning  grok-4.20-0309-reasoning  grok-4.20-multi-agent-0309
```

**Sample size.** One model name, retired between when it was written and now.

**The diagnosis gap, which is the part worth keeping.** `D-0069` deliberately
stopped returning provider detail to the client (`F-0010`) and logged only the
exception *type*. That is right for the client and insufficient for the
operator: a 404 for a retired model and a 401 for a revoked key produced the
same log line and the same "analysis failed". Hiding detail from the caller
does not require hiding it from the log, and conflating the two turned a
one-line fix into an investigation.

**Fixed.** The status code is logged - never the body. And the replacement was
chosen on measurement rather than on version number:

```
grok-4.7                       36.3s  3163 chars
grok-4.20-0309-non-reasoning    6.0s  2508 chars
grok-4.3                        7.0s  1730 chars
```

36 seconds is half the handler's 75-second timeout, spent reasoning about a
summarisation of figures `_gather_brief_context` had already gathered. The
non-reasoning variant returns comparable output in a sixth of the time. The
measurement is recorded beside the choice, because a model name with no note
is a value someone will change without knowing what it cost to pick.

### F-0086 — The composite colgroup had one more column than the table

**Claim.** `CompositeTab` declared **15** `<col>` elements for **14** columns.
`D-0062` removed the CDS Term column and left its `<col>` behind.

**Artifact.**

```
header columns: 14   body cells: 14   <col> entries: 15
fixed widths: 108 78 70 50 54 36 36 54 36 54 62 42 62 86  (sum 828) + 1 auto
```

**What it did.** A browser maps `<col>` elements to columns in order and
discards the surplus. Every column from CDS 5Y rightwards inherited the width
meant for its neighbour, **Activity took Score's 86px**, and the unsized
column written to absorb the remainder was thrown away. With the specified
widths summing to 828px against a full-width table, the browser then inflated
every column proportionally to make up the difference.

Reported as *"nearly the entire right half of the list is open real estate"* —
which is what proportional inflation of thirteen numeric columns looks like.

**Sample size.** One colgroup, one stale entry, every column after the tenth.

**Why the earlier spacing work did not catch it.** `D-0068` narrowed
Activity's `<td>` from `minWidth: 260` to `170/240`. Under
`table-layout: fixed` the `<col>` governs and a cell's own width is ignored —
so that change did nothing at all, and I reported the column as narrowed
having adjusted a property the layout algorithm was not reading.

Two lessons, and the second is the one that generalises: a removed column is
not removed until its `<col>` goes with it, and **a styling change nothing
verifies is a claim, not a fix**. There is no test here that could have
caught either, because neither jsdom nor a build computes table layout.

**Fixed.** Fourteen `<col>` elements — thirteen sized to their content, and
the prose column unsized so it takes the slack rather than every column
taking a share of it.

### F-0087 - Three different numbers for how stale TIC may be

**Found while** wiring a data-confidence strip onto every tab (`D-0074`) and
having to decide which threshold it should show.

There were three, all live, all describing the same question:

| Where | Value | What it actually governs |
|---|---|---|
| `pipelines/treasury_holdings.py` `MAX_SOURCE_AGE_DAYS` | 100 | the age at which the pipeline **refuses to import the file** |
| `pipelines/freshness_watchdog.py` `tic.max_age_days` | 55 | the age at which the source **has missed its release** |
| `ui/src/lib/freshness.js` `TIC_TOLERANCE_DAYS` | 100 | the age at which the footer **turned red** |

The first two are legitimately different questions and both numbers are
right. The third is the defect: I had copied the pipeline's *rejection*
threshold into the UI and used it to answer the *watchdog's* question. Its
own docstring said the UI and the pipeline "should agree about what too old
means" - the reasoning was sound and it was pointed at the wrong pipeline.

**What it would have looked like.** A TIC date 60 days old renders the
footer in neutral ink reading "60 days old", directly beneath a confidence
strip reading **"1 of 1 source is not current"**. Two components
contradicting each other about a single date on a single screen - worse than
either being wrong on its own, because a reader who sees them disagree can
no longer use either.

**Not currently visible.** TIC is 303 days old, past both numbers, so today
they happen to agree. The window of disagreement is 56-100 days, which TIC
will pass through the moment it starts publishing again - the fix arriving
*before* the data does, rather than after somebody notices the screen
arguing with itself.

**Sample size.** One source, one threshold, a 45-day window of disagreement.

**Fixed.** `freshness()` no longer defaults its tolerance: given none it
reports the age and makes no ruling at all. `TIC_TOLERANCE_DAYS` is deleted.
The thresholds live in the watchdog, one per source, and reach the screen
through `DataConfidence`, which reads `max_age_days` off the report rather
than holding a number. The client now holds no staleness threshold of any
kind.

**A second thing it dragged out.** `freshness()` rendered `"302 days old"`
when it had ruled a date stale and `"302d"` when it had not. Once the ruling
moved out, the terse form became the *normal* one - so the fix for `F-0083`
would have quietly reverted to "(302d)" on the very tab it was written for.
One wording now, always spelled out.

**Guarded.** `freshness.test.js` asserts a tolerance of 37 rules a date
stale and 90 does not, so a smuggled-in default fails the case. The test it
replaces asserted the client constant equalled 100 to match the pipeline -
it pinned the wrong contract, and pinned it accurately.
