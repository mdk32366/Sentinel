# Decisions — Sentinel

> Why is it like this? Each entry carries the option rejected and what forced
> the call. A decision without its discarded options is a fact, not a decision.
> 
> **Numbering ruled 2026-09-26 (`D-0021`).** Continue from the highest number
> present. `D-0017` and `D-0018` are **VOID — NEVER ISSUED**; do not reuse them.

---

### D-0016 — Ingest and display FRED DGS30; keep stress_score_v2 on DGS10−DGS2
*RECONSTRUCTED FROM COMMIT `febbca6` / `429ca90`. No rejected alternative recorded.*
30-year yield added to the FRED pipeline and surfaced in the UI. The v2 stress
scorer's yield-curve factor deliberately left on the 10Y−2Y spread. Cited by
`tests/test_dgs30_d0016.py`.

### D-0017 — VOID, NEVER ISSUED
Number does not appear in any commit, file or comment. Reserved permanently.

### D-0018 — VOID, NEVER ISSUED
As above.

### D-0019 — Do not block Fly health checks on startup fetches
*RECONSTRUCTED FROM COMMIT `28ef64d`. No rejected alternative recorded.*
The lifespan handler no longer runs FRED/TIC/gold/stress synchronously before
yielding. Cited by `tests/test_lifespan_cold_start.py`.

### D-0020 — Make CDS emptiness visible and fillable
*RECONSTRUCTED FROM COMMIT `17f2376`. No rejected alternative recorded.*
Cited by `tests/test_cds_coverage.py`.

### D-0021 — Continue decision numbering from 0021; void the gap

**Choice.** Adopt the existing commit-derived sequence. Back-fill 0016/0019/0020
as reconstructed, void 0017/0018, continue at 0021.

**Rejected.** Restart at D-0001 and record the orphans as a finding. Cleaner
register, honest about the fact that no decision was ever properly written.

**What forced the call.** Restarting orphans three citations that are live in
shipped code and in a test *filename*, and mints a second D-0016 that collides
with `tests/test_dgs30_d0016.py`. The orphan problem is recoverable; a
duplicated reference is not.

### D-0022 — Treasury Direct writes the same `DGS*` codes as FRED

**Choice.** `treasury_direct.py` writes `DGS7`, `DGS10`, `DGS30` and the rest of
the curve into the codes `fred_fetcher.py` already maintains. Treasury runs
21:00 UTC and arrives first; FRED runs 02:00 UTC and overwrites with the
revised value.

**Rejected.** A separate `UST_*` namespace. Cleaner provenance, and it would
surface source disagreement by construction rather than by test. Rejected
because it needs frontend work and leaves the one-day lag on every existing
tile.

**What forced the call.** FRED's `DGS*` *are* the Treasury constant maturity
rates. If that holds, two namespaces are redundant; if it does not, the dual
write is silently corrupting. That makes it an assumption with a test, not a
preference. See `A-0001`.

**Reversal condition.** The contract test failing. Revert to `UST_*` before any
further writes.

### D-0023 — Retain `days_back=1825` in the FRED fetch

**Choice.** Keep the five-year refetch window despite ~11,700 row updates
nightly to change perhaps eight values.

**Rejected.** Narrowing to 30 days now — the obvious efficiency win, and the
original recommendation.

**What forced the call.** The window is the observed repair mechanism. On
2026-09-23 a 502 lost `DGS10` for that run; the 09-24 run refetched and
repaired it unaided. Narrowing removes that behaviour at the same moment we add
retries that have never run in production. Change one thing.

**Revisit when.** Retries have held one week with zero `partial` runs. Then 30
days — never 1 or 2, because a missed night must still self-repair.

### D-0024 — Freshness thresholds are per-source

**Choice.** Each group in `CHECKS` carries its own `max_age_days`: treasuries 5,
oil 8, dollar index 12, gold price 45, gold reserves 130, TIC 55, CDS 4, OECD
yields 70, TRESEG 100, money supply 420.

**Rejected.** A single "stale after one business day" rule.

**What forced the call.** Against the state of the system on 2026-09-26, the
uniform rule alerts on healthy Treasury data every weekend and stays silent on
a gold series dead for 87 days. A check that fires when nothing is wrong trains
you to scroll past it.

### D-0025 — One repository-root constant, not per-module path arithmetic

**Choice.** A single shared root constant for every data path. Delete
`pipelines/data/`.

**Rejected.** Fixing each module's `parent` count in place. Smaller diff.

**What forced the call.** Three modules independently computed the root and one
got it wrong when it moved a directory deeper. The per-module fix leaves the
next move free to recreate the defect. See `F-0004`.

### D-0026 — Sentinel stays public

Principle 10 requires the observable meaning "development is complete" to be a
numbered decision on day one. Sentinel has none, and the repository is public.

Candidate: **the first stored data that cannot be rebuilt from public sources.**
Every current series — FRED, TIC, Treasury, WGC, World Bank — is rebuildable,
so Sentinel stays public and keeps its Planner's eyes. This week's diagnosis
depended on that access; the snapshot zip is what it costs when it goes.

Open question that decides it: are the AI analyst briefs persisted to the
database? If they are, they are generated content that no public source
reproduces. See `A-0004`.

**Owner's ruling, not the Builder's and not the Planner's.** Recorded as
unresolved rather than left unrecorded.

**RULED 2026-09-28, confirmed 2026-09-29: the repository stays public.** The
owner has made the call they intend to make, and this entry is closed rather
than left open pending a form of words.

**What watching it looks like.** The candidate observable is unchanged: *the
first stored data that cannot be rebuilt from public sources*. `F-0033`
established that the AI analyst briefs are not persisted and never have been,
so `A-0004` holds and nothing currently stored fails that test. If that stops
being true, this is the decision to revisit.

**The cost is being paid deliberately.** A public repository keeps the
Planner's direct access, and this week showed what that is worth — the snapshot
zip in `F-0037` is what it looks like when the Planner has to be hand-fed
instead. It is paid for by every credential staying in the platform and out of
the tree, which `F-0009` shows is a live obligation rather than a formality.

The candidate is unchanged and is now better supported: *the first stored data
that cannot be rebuilt from public sources*. `F-0033` established that the AI
analyst briefs are not persisted and never have been, so `A-0004` holds and
nothing currently stored fails that test. Every series — FRED, Treasury, LBMA,
TIC, WGC, World Bank — is rebuildable today.

---

### D-0028 — Backend remediation sequenced ahead of frontend decomposition

**Choice.** Work ORDER-03 Parts A–E (live exposures, `experimental/` promotion,
migrations, scorer performance, API contract) before Part F, the frontend
decomposition.

**Rejected.** The June 2026 V2 Refactoring Plan's ordering, which put frontend
decomposition second, immediately after Phase 0 hygiene.

**What forced the call.** Measurement, not preference. `App.jsx` was 2,248
lines when the plan named it the highest structural priority; it is 2,583 now
— it grew 15% during the three months it waited. Meanwhile all three defects
that fired in September were backend, and Parts A–C together are about two
days. Spending a week on the file that has not hurt anyone yet, while the
`.dockerignore` ships `.env` into the production image, is the wrong order.

**Note.** This does not retire the June plan. Sections 3 (CDS scoring) and the
repo reconciliation are done; Phase 0's CORS and committed-build items are not
and are carried into ORDER-03.

### D-0029 — Promote `experimental/` wholesale rather than fix path depth per module

**Choice.** Move all five modules to `pipelines/`, delete the directory, lift
imports to module level, and adopt a single repository-root constant.

**Rejected.** Correcting each module's `parent` count in place. Smaller diff,
no import changes, no risk of a missed reference.

**What forced the call.** The per-module fix leaves the next directory move
free to recreate `F-0004`. The extra path level is the defect, not the
arithmetic. Also mechanical: the directory name has been false for months, and
a name that lies is read by everyone who arrives.

### D-0030 — Composite score becomes a persisted read

**Choice.** The 04:30 scheduled job persists its scored result;
`/stress/composite` serves it with a computed-at timestamp; an authenticated
`?recompute=true` remains.

**Rejected.** (a) An in-process cache with a TTL — dies on every deploy and
gives each Fly machine its own answer. (b) Leaving it as a live recompute and
only fixing the N+1 — still ~200 queries per tab click for a number that
changes once a day.

**What forced the call.** The nightly job already computes this and the
endpoint ignores it. That is redundant work, not a missing capability.

**Cost this accepts.** A second producer of the same number, same shape as
`D-0022`, and it gets the same contract test.

### D-0031 — `/api/analyze/country` builds its prompt server-side

**Choice.** The endpoint accepts a country ISO code. The prompt is assembled on
the server from data already scored in the database.

**Rejected.** Keeping the client-supplied prompt behind an allowlist or length
cap. Smaller change, keeps the UI's prompt-authoring flexibility.

**What forced the call.** A validated free-text prompt forwarded with a
server-side API key is still a funded LLM endpoint for anyone past the shared
password. The only durable fix is for the server to decide what it is paying
for.

### D-0032 — Alembic is removed; DDL is manual and documented

`alembic==1.12.1` is pinned and has never been initialized. Schema comes from
`create_all()`, which ignores changed columns silently.

**(a) Initialize.** Baseline against current schema, stamp as head, migrations
from here.
**(b) Remove and document.** Drop from requirements; `architecture.md` states
DDL is manual and names the procedure.

Pinning an unused migration tool is worse than either, because it reads as
having migrations. **Owner's ruling.**


**RULED 2026-09-29: option (b), drop it.** Owner's decision, made against the
evidence in `F-0051` rather than a preference: alembic appears exactly once in
the project — the pin in `requirements.txt` — with no `alembic.ini`, no
`versions/`, no import anywhere in code, CI or the Dockerfile, and nothing
depending on it transitively. There were no migrations to abandon.

**What the decision costs, and what was done about it.** Removing a migration
tool removes *detection*, not migrations we were using. `create_all()` creates
missing tables and silently ignores every other change, so `models.py` and the
database can disagree indefinitely with nothing saying so.

So `tools/check_schema_drift.py` was added in the same change. It compares
`Base.metadata` against a live schema and exits non-zero on structural drift —
a declared table or column the database lacks, or the reverse.

**Type differences are advisory rather than fatal, deliberately.** Run against
the local database it reports eight `DATETIME` versus `TIMESTAMP` rows, all of
them correct: that is SQLAlchemy's `DateTime` rendering in Postgres. A check
that failed on those would fail on a perfectly good schema and be ignored
inside a week — `D-0024`'s argument, applied to schemas instead of freshness.

**Still not proved where it matters.** The drift check has never run against
production; that needs `fly ssh console`, which the Builder cannot reach.
`A-0010` stays ASSUMED until it does, and running it belongs in the next
session that has production access.

The procedure — how DDL is applied, that `psql` is absent from the image, and
where migration SQL lives — is in `docs/architecture.md` under *Schema changes
are manual*.
### D-0033 — Freshness lives on `/api/freshness`, not `/api/health`

**Choice.** The freshness report is served from an authenticated
`/api/freshness`. `/api/health` returns liveness only.

**Rejected.** ORDER-01 B6 as originally written, which attached the report to
`/api/health`.

**What forced the call.** `main.py:64` — `OPEN_PATHS = {"/api/health"}`. That
path bypasses `BasicAuthMiddleware` for the Docker and Fly probes. Attaching
the report would have published per-source data staleness unauthenticated.

**This amends ORDER-01 B6.** The amendment is recorded in ORDER-01 and in
ORDER-03 A0 as well as here — a rule changed in one document and not the others
has not been issued.

---

### D-0027 — A missing or frozen source file is a hard failure, not a `partial`

**Choice.** `run_gold_reserves_fetch` raises `FileNotFoundError` and logs
`status="failed"` where it previously logged `status="partial"` and returned a
result dict. `import_gold_price_csv` additionally refuses any file whose newest
row is older than `MAX_SOURCE_AGE_DAYS = 70`, and refuses a file that yields no
parseable rows at all.

**Rejected.** Keeping `partial` and letting the freshness watchdog be the only
thing that notices. Smaller change, and it keeps the pipeline "succeeding".

**What forced the call.** `partial` is a guard standing aside, and under
Principle 6 that is not a guard. The specific reason a presence check was
insufficient: the file was never missing. It was present and frozen for three
months, so a missing-file check could not have fired. See `F-0004`.

**Why 70 days.** The WGC series is month-end and is normalised to day-1 on
write, so a fully current file already measures 56 days old on 2026-09-26 and
reaches ~65 just before the next publication. 70 is the first value that does
not fire on healthy data. Anything near 45 alerts on a correct file — the
failure `D-0024` exists to prevent.

**Reversal condition.** If the source ever becomes daily, 70 is far too loose
and must be re-derived from the new cadence.

### D-0035 — Pipeline detail moves to `/api/pipeline-status` rather than being deleted

**Choice.** `/api/health` returns `{"status": "healthy"}` and takes no database
session. The `database` / `scheduler` / `last_*_update` fields it used to serve
move verbatim to `GET /api/pipeline-status`, behind the same Basic Auth as
every other route.

**Rejected.** Deleting the fields outright. ORDER-03 A0 only requires that
`/api/health` stop carrying them, and deleting would have removed a diagnostic
that the ADMIN tab's checklist tells an operator to go and read.

**What forced the call.** The path is in `main.py` `OPEN_PATHS`, so everything
it returns is public. Last-update timestamps and scheduler state describe
internal operations and do not belong on an unauthenticated probe. `F-0034`
established that nothing read them, so moving cost nothing.

**Second effect, deliberate.** The Fly probe hits this every 15 seconds and
previously issued three `update_logs` queries per hit against a pool of 10.
Liveness should not consume a connection.

**Reversal condition.** If an external monitor is ever pointed at
`/api/pipeline-status`, it needs credentials — that is the trade being made.

### D-0034 — The register assigns numbers; planning documents propose unnumbered

**Choice.** The Planner writes entries with a placeholder, never a number. The
Builder assigns at the moment of append, reading the live register. Any order
or entry document arriving with numbers is renumbered on application.

**Rejected.** (a) The Planner reserving a block in advance — requires the
register to be read at planning time and stay unchanged during the work, which
is exactly what failed. (b) The Planner numbering and the Builder reporting
collisions afterward — puts reconciliation after the citations are written.

**What forced the call.** On 2026-09-26 the Planner issued D-0027–D-0032 and
F-0012–F-0024 in Addendum B V1 while the Builder concurrently assigned D-0027
and F-0012–F-0016 against the register. Thirteen numbers collided in one
afternoon, with the register under two hours old.

The numbering preamble in the first entries document warned about this and did
not prevent it, because it told the Builder not to invent numbers and said
nothing about the Planner. A rule binding one player and not the other is not a
rule about numbering.

**Ratifies** the Builder's D-0027 (hard-error guard on the gold importers) over
the Planner's. It was minted against the register, is cited in shipped code,
and was correct to mint — a real choice with a rejected alternative, and
leaving it unrecorded is the failure this register exists to prevent.

---

### D-0036 — Ship `DGS7` through FRED alone; `treasury_direct` stays unregistered

**Choice.** Add `DGS7` to `FRED_METRICS` and surface it in the UI. Do not
register `treasury_direct` and do not add a second writer for the `DGS*`
namespace.

**Rejected.** Completing ORDER-01 B3-B5 in the same pass — registering the
21:00 Treasury Direct job and backfilling from `home.treasury.gov`. That is the
route the order specifies and it also delivers `DGS7`, same-day rather than on
FRED's one-business-day lag.

**What forced the call.** `D-0022` makes Treasury Direct and FRED two producers
writing the same metric codes, and it is valid only if the contract test in
ORDER-01 B1 passes — the two sources agreeing to 0.01 across overlapping dates.
That test has not been written or run, and `A-0002` records that this project
has never once fetched the Treasury endpoint. Registering the job to obtain the
seven-year would start the dual write that the test exists to validate, and
would do it for a reason unrelated to the test.

Adding `DGS7` to `FRED_METRICS` is a **single** producer on a namespace FRED
already owns. It carries none of `D-0022`'s risk and needs none of its
preconditions.

**Cost, stated.** The seven-year arrives on FRED's one-business-day lag rather
than same-day, and `F-0038` stays open: `treasury_direct.py` and
`freshness_watchdog.py` remain deployed and unreferenced.

**Reversal condition.** When the B1 contract test passes, Treasury Direct is
registered and takes the same-day write. `DGS7` needs no change at that point —
it is already in `FRED_METRICS`, which is where `D-0022` expects it.

### D-0037 — Six tickers to a line

**Choice.** The MARKETS stat-card grid moves from five columns to six, so the
eleven tickers occupy exactly two rows of 6 + 5. The yield curve and Fed Funds
fall on the first line together.

**Rejected.** Leaving five columns, which would have pushed the eleventh ticker
onto a third row holding a single card.

**What forced the call.** Requested by the owner as part of adding the
seven-year. Six columns is the first width at which eleven tickers fit two
lines; it also happens to put `DGS30 / DGS10 / DGS7 / DGS5 / DGS2 / FEDFUNDS`
on one row, which reads as the curve.

**Watch for.** A twelfth ticker still fits. A thirteenth spills to a third row
and this decision needs revisiting rather than silently widening again.

### D-0038 — `/api/*` is `no-store`; static assets keep their validators

**Choice.** A `NoStoreAPIMiddleware` sets `Cache-Control: no-store,
must-revalidate` plus `Pragma: no-cache` and `Expires: 0` on every response
whose path begins with `/api/`. Static assets are untouched and keep the
`ETag` and `Last-Modified` that `StaticFiles` provides.

**Rejected.** `ETag` with revalidation on the data endpoints. It would cut
bandwidth and still guarantee freshness, and for a dashboard whose payloads are
a few hundred kilobytes that saving buys nothing against the cost of getting
the validator wrong. Also rejected: a short `max-age`, which replaces "stale
forever" with "stale for N seconds" and leaves the same failure mode with a
smaller window.

**What forced the call.** `F-0039`. These endpoints are a live read of a
database that changes nightly, and the fingerprinted asset bundle already
handles the case that genuinely benefits from caching.

**Note on scope.** `/api/health` is also `no-store`. The Fly and Docker probes
issue their own requests and do not cache, so this costs nothing and keeps the
rule simple — one prefix, one behaviour, no exceptions to reason about.

**Reversal condition.** If a data endpoint is ever large enough that
revalidation matters, give that endpoint an `ETag` explicitly. Do not relax the
default.

### D-0039 — Disposability is a canary table, armed by the test package

**Choice.** `database.connection` carries `assert_disposable()`, which requires
a `canary` table holding the marker `SENTINEL_DISPOSABLE`. `tests/__init__.py`
sets `SENTINEL_TEST_RUN=1`, and `get_session()` / `get_db()` refuse with
`NotADisposableDatabase` when that marker is set and the canary is absent. The
canary is created only by `tools/mark_disposable.py`, never by the application.

**Rejected.** A hostname or port check — defeated by a tunnel, which is the
signature that emptied a database twice. A reachability check — "skip unless a
database is reachable" means supplying production credentials *arms* the guard
instead of tripping it, which is Principle 6's blood line exactly. A required
hand-typed environment variable — acceptable under Step 12, but it protects the
session rather than the database, so a second terminal with the variable set
carries the same risk to a different target.

**What forced the call.** Step 12 demands both halves at once: the suite passes
offline, and a real database is a hard error even through a tunnel. Firing on
session creation *during a test run* satisfies both — our tests use in-memory
SQLite and never ask for that session, so offline runs are untouched, while any
future fixture that does reach for a real database must prove identity first.

**What it does not cover, written where the next person will look.** It does
not protect scripts run outside the suite; pointing a pipeline at production is
what pipelines are for. It guards the case where a *test fixture* reaches a
database whose data is not expendable.

**Reversal condition.** If a test ever legitimately needs the real database,
that test marks its own throwaway instance. Do not weaken the guard to admit it.

### D-0040 — CI runs discovery from the repository root

**Choice.** `python -m unittest discover -t . -s tests -p "test_*.py" -v`.

**Rejected.** The hand-maintained module list, which left two test files outside
the gate for weeks (`F-0006`). Also rejected: `discover -s tests` without
`-t .`.

**What forced the call.** `-t .` is not cosmetic. Without it, discovery inserts
`tests/` on `sys.path` and imports the modules as top-level names, so
`tests/__init__.py` never executes and the `D-0039` guard is never armed. See
`F-0040`.

**How it is kept honest.** `test_disposable_guard` asserts that
`SENTINEL_TEST_RUN` is set. An invocation that disarms the guard fails the suite
rather than passing quietly, so this cannot regress into a silent hole.

### D-0041 — Gold spot comes from the LBMA daily fix

**Choice.** `pipelines/gold_price_fetcher.py` reads
`prices.lbma.org.uk/json/gold_pm.json` and writes `GOLD_SPOT_USD` daily at
02:30 UTC. Ruled by the owner on 2026-09-28 after ORDER-02 Part B reported.

**Rejected.** A FRED series — none exists. `GOLDPMGBD228NLBM` returns *"The
series does not exist"*; every recent gold hit on FRED is an index, not a price
in USD per troy ounce (`F-0043`). Also rejected: the World Bank Pink Sheet,
which is not exposed as a WDI indicator. Also rejected: keeping the manual WGC
CSV as the only path, which is what produced `F-0004`.

**What forced the call.** LBMA is live, unauthenticated, daily, and carries 702
months against the CSV's 584. It is not a second source spliced onto a first:
its monthly mean reproduces the existing history to **0.00% across every month
compared** (`F-0044`), because WGC sources from ICE Benchmark Administration,
which administers this fix. The stopping mechanism in ORDER-02 B2 exists to
catch a systematic level difference between two sources; there is none, because
there are not two sources.

**Consequence, measured before shipping.** `GOLD_SPOT_USD` becomes daily where
it was monthly-normalised-to-day-1. `A-0005` was the open question and it was
tested rather than assumed: scoring with monthly versus daily gold changed
`trend_3m_pct` from 8.25% to 5.83% and changed **zero** tier assignments across
29 countries. `rising` is a threshold at 2%, so both frequencies land on the
same side of it today — that is a measurement at one moment, not a proof for
all inputs.

**The freshness threshold moves with it.** `gold_price` goes from 75 days to
**8**. 75 was calibrated for a month-end series normalised to day-1, where a
healthy value is already 56 days old. Left at 75 against a daily feed, a dead
source would go unnoticed for eleven weeks — the decoration `D-0024` exists to
prevent. A threshold is a property of the source's cadence, so changing the
source without changing the threshold is half a change.

**What it does not cover.** Gold **reserves** by country stay manual. The WGC
country series is behind the same account wall with no public API, and Part B
did not change that. `pipelines/gold_price_import.py` is retained as the manual
CSV path and as the importer `D-0033`'s guards are attached to; it is no longer
the route by which spot arrives.

**Reversal condition.** LBMA requiring authentication, or its monthly mean
diverging from the WGC CSV by more than 1% in any month.

### D-0042 — The composite score is persisted nightly and the endpoint is a read

**Choice.** `persist_composite_snapshot()` scores every country once at 04:45
UTC and stores the scorer's own output as JSON text in `composite_snapshots`.
`GET /api/stress/composite` serves the stored result with its `computed_at`,
and `?recompute=true` bypasses it.

**Rejected.** Caching in process — lost on every deploy, and Fly restarts this
app often enough that the cache would be cold whenever anyone looked. Also
rejected: shredding the payload into columns, which would need a schema change
every time the scorer gains a dimension, against a project with no migrations
(`F-0022`).

**What forced the call.** The endpoint recomputed on every click of the
COMPOSITE tab. Measured: 297 queries before `D2`'s metric-cache hoist, 232
after, ~116ms per request against a pool of 10 connections.

**The contract this creates.** Persisting makes a second producer of the same
number — the same shape as `D-0022` — so it gets the same treatment:
`tests/test_composite_snapshot.py`, and equality on real data measured at
29 countries with **0 disagreements and an identical payload**. A stale score
served fast is worse than a slow correct one.

**Fall-through, deliberate.** With no snapshot the endpoint computes rather than
serving an empty tab. Absence is a case with a cause, never a blank.

**Reversal condition.** Stored and recomputed disagreeing on unchanged inputs.

### D-0043 — A manual trigger for the gold fetch

**Choice.** `POST /api/fetch/gold-price`, following the existing
`/api/fetch/gold-reserves` pattern.

**Rejected.** Waiting for the 02:30 UTC job. That is correct for a routine
refresh and wrong when the series is known stale, because the scorer is wrong
until it runs — which is the whole of `F-0004`.

**What forced the call.** The freshness endpoint's first production run
reported `Gold spot price CRITICAL, latest 2026-07-01, age 89, limit 8`. The
data existed; nothing could pull it before the next window.

### D-0044 — Credential rotation is deferred to Friday 2026-10-02

**Choice.** ORDER-01 Part C — rotating `AUTH_PASSWORD`, `FRED_API_KEY`,
`ANTHROPIC_API_KEY` and `GROK_API_KEY`, and scrubbing the `update_logs` rows —
is scheduled for **Friday 2026-10-02** rather than done on discovery. Owner's
ruling, 2026-09-28.

**Rejected.** Rotating on the spot. It is the safer default and it was the
recommendation; the owner has the context on what else the keys touch and when
there is time to do the scrub properly.

**What is being accepted for four days, stated plainly so it is a decision and
not a drift.** These two findings compose, and neither entry says so on its
own:

1. `F-0009` — the dashboard password is in public git history and is confirmed
   to be the live production credential.
2. `F-0010` — `/api/pipeline-logs` serves the live `FRED_API_KEY` in plaintext,
   21 occurrences as measured on 2026-09-28, zero redacted.

Together: the password that gates the endpoint is public, so the FRED key is
effectively readable without credentials until Friday. That is the exposure
being accepted, and its size is known rather than guessed.

**Not affected by the delay.** `GROK_API_KEY` is not set in Fly at all, so
nothing in production can spend it. `ANTHROPIC_API_KEY` and `GROK_API_KEY`
values do not appear in git history — their rotation rests on ORDER-01 C1's
claim that they were in a file shared into the Planner's project, which the
Builder cannot verify and the owner can.

**Sequencing for Friday, because the order lists these as one step and they are
not.**

1. Rotate `AUTH_PASSWORD` **first** — it is what gates the endpoint that leaks
   the FRED key.
2. Rotate `FRED_API_KEY` **second**. Rotation neutralises all 21 exposed copies
   immediately; the `update_logs` scrub is hygiene afterwards, not the fix.
3. Scrub `update_logs`. **`psql` is not in the image** — use `python3` with
   `psycopg2` over `fly ssh console`.
4. Rotate `ANTHROPIC_API_KEY` and `GROK_API_KEY` if the shared-file claim
   holds.
5. `DATABASE_URL` depends on `A-0007`, whose historical answer is
   unrecoverable. Treat as a separate call.

**Blocker that is still open and is not a key.** C1 requires a completed backup
and a recovery credential held outside any env file — Day-One Step 16, recorded
as unanswered in `architecture.md`. The destructive `UPDATE` in step 3 should
not run before that question is answered.

**Reversal condition.** Any sign the FRED key has been used by someone else —
an unexplained rate-limit error or a `partial` run that the 502 pattern in
`F-0003` does not explain. Then rotate that day, not Friday.

### D-0045 — A frozen TIC source is a failure, not a success and not a `partial`

**Choice.** `run_treasury_holdings_fetch` raises `StaleSourceError` when the
newest parsed observation is older than `MAX_SOURCE_AGE_DAYS = 100`, and that
error is logged as `status="failed"`.

**Rejected.** Leaving the freshness watchdog as the only thing that notices.
It *did* notice — the watchdog flagged TIC CRITICAL at 301 days on its first
production run, which is the watchdog earning its keep. But a pipeline that
reports `success` while importing a nine-month-old file is lying in its own
log, and the log is what anyone debugging reads first.

Also rejected: `partial`. `partial` reads as "mostly fine" and is precisely
what let this sit unexamined. A guard that stands aside is not a guard
(`D-0027`).

**What forced the call.** `F-0050`. Ten consecutive runs, all `success`, all
`0 inserted / 10009 updated`, newest observation never moving.

**Why 100 days.** TIC MFH is monthly, released about 45 days in arrears, so a
healthy newest row is around 60 days old and roughly 75 at the end of a cycle.
100 is the first value that does not fire on a correctly updating source. A
tighter limit would alert on healthy data, which is the decoration `D-0024`
exists to prevent.

**Distinguished from per-country errors.** `StaleSourceError` is its own type
so it cannot be swallowed by the loop that legitimately produces `partial` when
one country's row fails to parse.

**Reversal condition.** If TIC moves to a source whose cadence differs, the
constant is re-derived from that cadence rather than nudged.

### D-0046 — The jump anomaly reaches the freshness report, and still does not block

**Choice.** `treasury_direct`'s `MAX_JUMP_PP` anomaly, which it writes into
`update_logs.error_message` behind an `ANOMALIES:` marker, is now read by the
freshness watchdog. An affected source carries its anomaly text and, if it
would otherwise be `ok`, reports the new status **`anomaly`**.

**Rejected.** Making the jump detector block the write. The testplan has always
said why, and it has not changed: on 2026-09-23 the 10-year moved 15 basis
points in one session during a genuine selloff, and **a blocking jump detector
is a mechanism for refusing to record a crisis.** The defect was never
permissiveness.

**What forced the call.** The testplan's own open item: *"the anomaly lands
only in a log field nobody reads... a check placed where its answer cannot
change what anyone does - Principle 9's second form. Not closed."* The answer
existed and reached no one. Now it reaches the one report a human looks at.

**Ranking, and why it is low.** `anomaly` sits below `stale` and `unknown` in
both the per-source sort and the overall status. A stale source is definitely
wrong and a missing one is definitely absent; an anomalous one is plausibly
correct and worth a look. Ranked higher, every genuine market move would mask a
real gap - which is how a signal becomes noise and then becomes ignored.

**It raises, never lowers.** Stale data that also jumped is still stale. The
more serious finding wins.

**Reversal condition.** If `anomaly` fires often enough that people scroll past
it, `MAX_JUMP_PP` is mis-calibrated and should be re-derived from observed
daily moves - not silenced.

### D-0047 — One module owns the API base URL

**Choice.** `ui/src/lib/api.js` exports `API_BASE`, `apiUrl()` and
`apiFetch()`. All 22 call sites in `App.jsx` go through `apiFetch`; no bare
`fetch(` and no `API` constant remain in that file.

Resolution order: an explicit `VITE_API_BASE` wins; in dev the API is taken to
be port 8000 **of whatever host the page was loaded from**; in production it is
same-origin `/api`.

**Rejected.** Fixing the hostname test in place — `hostname === "localhost" ||
hostname === "127.0.0.1"` and so on. It extends the list of blessed hostnames
without removing the assumption that the list can be complete.

**What forced the call.** `F-0052`. Reading the host instead of comparing it to
a literal is the actual fix; the module is what stops the next person needing
to know that.

**Behaviour deliberately unchanged.** `apiFetch` does not throw on a non-2xx
response. Callers already branch on `r.ok` or read an error field from the
body, and changing that contract while moving 22 call sites would mix a
refactor with a behaviour change. Error handling belongs to Part F step 2.

**Verified.** The production bundle contains **zero** occurrences of
`localhost:8000` — `import.meta.env.DEV` is false in a production build, so
Vite removes the dev branch entirely and production ships only the same-origin
path.

### D-0048 — A manifest makes a stale UI bundle fail the gate

**Choice.** `tools/record_ui_build.py` records a SHA-256 over every source file
Vite compiles, plus the bundle `index.html` references, into
`api/static/BUILD_MANIFEST.json`. `tests/test_ui_bundle_freshness.py`
recomputes it, so editing `ui/src` without rebuilding fails CI.

**Rejected.** Adding a Node stage to the Dockerfile, which is what `F-0027`
actually asks for and which would prove more — it would build the UI from
source at image build time, making a stale bundle impossible rather than
merely detectable. Not taken **today**: it changes the deploy path, and
changing the deploy path is not something to do at the end of a long session
on a Monday evening. The guard is the cheap half that carries no deploy risk,
and `F-0027` stays open for the other half.

Also rejected: comparing file modification times. Git does not preserve
mtimes, so a fresh clone would fail or pass at random.

**What forced the call.** The bundle was rebuilt and copied by hand four times
today. Every one of those was a step that could have been skipped, and skipping
it ships the old interface against a new API with **nothing** indicating it —
the app loads, every endpoint answers, the UI is simply wrong.

**Detail that matters.** The digest normalises CRLF to LF before hashing. Git
checks this repository out with CRLF on Windows and LF in CI, and a line-ending
difference must not read as a source change.

**Proved by tripping it.** An unbuilt edit to `ui/src/App.jsx` fails with the
two digests and the exact commands to fix it; reverting clears it.

**What it does not prove.** That the committed bundle was built *correctly*
from that source — only that the source has not moved since. Building in CI is
what would close that.

### D-0049 — The UI is built in the image; `api/static/` is no longer committed

**Choice.** A `node:22-slim` stage runs `npm ci && npm run build` and the result
is copied to `/app/api/static/`. `api/static/` is removed from git and added to
both `.gitignore` and `.dockerignore`, so the build output is the only thing
that can ever be there. `D-0048`'s manifest guard and
`tools/record_ui_build.py` are retired — they existed to detect a problem that
no longer exists.

**Rejected.** Keeping the committed bundle alongside the build stage. That
leaves two writers into the same image path — `COPY . .` brings the committed
copy, `COPY --from=ui` brings the built one — and which wins is decided by line
order in the Dockerfile. Ambiguity that is invisible is worse than the original
defect.

Also rejected: keeping `D-0048` as a belt-and-braces check. Its own docstring
said it *"does not prove the bundle was built from that source correctly"* —
and Principle 6 is explicit that a guard naming its own failure mode has a
finding against itself. Keeping a guard for a closed problem trains people to
ignore it.

**What forced the call.** `F-0027`, and Principle 1. The UI had two canonical
copies, `ui/src` and `api/static/`, both committed, with nothing structural
keeping them in agreement. That is the same shape as `F-0004`'s shadow data
directory and `F-0050`'s frozen calendar file. The manual rebuild step was
performed by hand four times on 2026-09-28 alone; Principle 3's blood line is
*"a step that depends on you remembering it will eventually be forgotten."*

**Cost, accepted by the owner on 2026-09-29.** Deploys now depend on the npm
registry as well as PyPI, and take longer. `package-lock.json` is committed and
the stage uses `npm ci`, so the same commit produces the same bundle.

**Layer ordering is deliberate.** `package.json` and the lockfile are copied
before the source, so a change to `ui/src` rebuilds the bundle without
reinstalling dependencies.

**Proved from source, not by reasoning.** A marker was added to `ui/src` with
**no local `npm run build`** — the local `dist/` still held the previous bundle
— and the image was rebuilt. The marker appeared in the bundle inside the
image. That is the only evidence that the image builds from source rather than
from a committed artefact.

### D-0050 — The change window is measured, and the label says what was measured

**Choice.** `priorObservation(points, 30)` finds the last observation on or
before thirty days prior and returns the gap it actually found.
`changeWindowLabel(actualDays)` renders that number, so a card reads `vs 30d`
when the comparison really spans thirty days and `vs 3d` when it does not.

**Rejected.** Relabelling everything to "vs prev". Honest, and it throws away a
metric people want — a thirty-day move is a real question and the dashboard was
trying to answer it.

Also rejected: falling back to the oldest available point when a series is too
short. That is exactly the defect in another form — comparing against whatever
happens to be there and describing it as thirty days. `priorObservation`
returns null instead, and the card shows no change at all.

**What forced the call.** `F-0055`. Eight of eleven tickers described a
one-to-three-day move as a month.

**Consequence, stated.** Numbers on the MARKETS cards will change, because they
now measure a different and longer period. That is the fix, not a regression.

**Tested.** `ui/src/lib/series.test.js` covers the date lookup, the too-short
case, the exact-boundary case, the percentage-point versus percent branch, and
that the label never claims thirty days for a three-day gap.

### D-0051 — The STRESS tab is retired; the scorer behind it is not

**Choice.** `STRESS` is removed from `TABS` and `StressScoreTab` is deleted.
The ABOUT tab carries a RETIRED section recording what it was, why it went, and
what still runs.

**Rejected.** Deleting `stress_score_v2.py` and `GET /api/stress-score` as
well. The scheduled job at 04:30 UTC still writes `Stress_Score` rows, and
`get_latest_metric_value` is imported from that module by `api/routes.py` and
by `composite_stress.py`. Removing it is a much larger change than retiring a
tab, and nothing asked for it.

**What forced the call.** Owner's ruling, 2026-09-29. The tab showed a single
US-level score built from the yield curve, holdings concentration and commodity
volatility. `COMPOSITE` scores sovereign stress per country. They answer
different questions, and presenting both as top-level tabs invited them to be
read as one number disagreeing with itself — which ORDER-03 already flagged as
*"a recurring source of confusion"*.

**Why the ABOUT note matters more than the deletion.** A surface that simply
vanishes gets rebuilt by whoever misses it. The note says what it measured and
that the endpoint still serves it, so the next person can decide rather than
rediscover.

**Reversal condition.** If the US-level score is wanted again, it is an ABOUT
entry away from being a tab, and the endpoint never stopped working.

### D-0052 — The last tick on every chart axis is always rendered

**Choice.** All six `XAxis` components carry `interval="preserveStartEnd"`
alongside `minTickGap={60}`.

**Rejected.** Reducing `minTickGap`, which would crowd the axis on a five-year
daily series to fix the one label that matters.

**What forced the call.** The owner reported the latest treasury tick reading
2026-09-23. The data was not stale — production held 2026-09-28 across all five
`DGS` series, `/api/stats` reported `data_latest` of 2026-09-29, and the
`no-store` headers from `D-0038` were in place. With `minTickGap` alone, the
rightmost *label* falls wherever the spacing puts it, which on a daily series
is several days short of the last *point*. The line was right and the axis
under it was not.

**Why it is worth a decision.** A chart whose last label predates its last
point invites exactly the question it was asked twice this week. Freshness that
the data has but the display does not show is still a freshness problem.

### D-0053 — Gold spot joins the MARKETS tickers

**Choice.** `GOLD_SPOT_USD` becomes the twelfth ticker, filling the slot
`D-0037` left open on the second row. `formatValue` gains a `$/oz` branch
rendering whole dollars with a thousands separator — `$4,145` — because gold
trades in four figures where cents are noise and the separator is what makes it
readable at a glance.

**Rejected.** Reusing the `$/bbl` branch. It keeps cents, which is right for
oil at $96.41 and prints `$4261.05` in a column sized for five characters.

**What forced the call.** Owner's request, and it only became reasonable
recently: before `D-0041` the series was a manual monthly CSV that had been
frozen since July (`F-0004`). A markets ticker showing a three-month-old
monthly average would have been worse than no ticker. It is a live daily LBMA
fix now.

**Layout.** Twelve tickers across six columns is two full rows — exactly the
capacity `D-0037` recorded. A thirteenth still spills to a third row and still
needs that decision revisited rather than the grid silently widened again.

**On the chart, deliberately opt-in.** Gold is roughly 800 times the scale of a
yield, so plotting both on one axis flattens the yields to a flat line. It is
not in the default selection, and the `% CHANGE` toggle exists for anyone who
wants them together.

**Verified against production before shipping:** the card renders
`Gold Spot $4,145 ▼ 9.17% vs 31d`. The "31d" is `D-0050` working — the nearest
observation at or before thirty days back was 31 days out, and the label says
so rather than claiming thirty.

### D-0054 — App.jsx is decomposed into pages, components and constants

**Choice.** ORDER-03 Part F steps 2 and 3. `App.jsx` goes from **2,398 lines to
240**: nine tabs into `ui/src/pages/`, eight shared components into
`ui/src/components/`, and the shared constants into `ui/src/lib/constants.js`.
`App` keeps the shell — header, ticker, tab bar, and the MARKETS body, which is
composed inline from `METRICS` rather than living in its own component.

**Rejected.** Moving everything by hand. Nine tabs with different dependency
sets is where a missed import becomes a runtime error on a tab nobody opened in
testing.

Also rejected: doing it without a net. The order says decomposing this file is
*"the change most likely to break something silently"*, and it was right.

**The net came first, deliberately.** `ui/src/pages.dom.test.jsx` mounts every
tab with `fetch` stubbed and asserts each renders something. Those twelve tests
were written and **passed against `App.jsx` before anything moved**, then
passed again against `pages/` afterwards. Only the import paths changed; every
assertion is identical, which is what makes them a net for the move rather than
a description of wherever the code landed.

**Imports are computed, not copied.** Each extracted file gets only what its
body references. Copying the import block wholesale is how a file ends up
carrying eight unused symbols, which is `F-0056` restarted.

**What is not done.** Step 4, extracting hooks, and the components inside each
page. `CountryDetail` is 269 lines and `USADashboard` 346; both are now
separately addressable, which is the point of the step. Coverage is still
render-level: these tests prove each tab mounts, not that any of them is right.

### D-0055 — The frontend's data layer is hooks, and the two large pages are decomposed

**Choice.** ORDER-03 Part F step 4, plus the components inside each page that
`D-0054` left as separately addressable and unaddressed.

Four hooks now own everything that talks to the API:

| hook | what it owns |
|---|---|
| `useApiResource` | fetch one JSON resource on mount, with `reload()` |
| `useMarketSeries` | the ticker's latest and ~30-day-prior values |
| `useChartSeries` | the MARKETS chart's rows for the current selection |
| `useAsyncAction` | a keyed write, with per-key progress and outcome |
| `useCountryDetail` | the four requests behind the country panel |
| `useCountryNarrative` | the analyst brief for one country |
| `useUSASeries` | every USA series for the selected window |

**No component calls `apiFetch` any more.** `App.jsx`, all nine pages and both
large components import a hook instead. That is the property worth stating,
because it is checkable and it is what makes `F-0063` fixable in one place
rather than five.

**Sizes.** `App.jsx` 240 → **166**. `USADashboard` 351 → **83**.
`CountryDetail` 274 → **111**. The arithmetic came out as four testable pure
modules — `lib/fiscal.js`, `lib/usaSeries.js`, `lib/countrySeries.js`,
`lib/rateScenarios.js` — and the JSX as ten components under
`components/country/` and `components/usa/`.

**Rejected.** Doing the decomposition without touching the fetch shape. The
five copies of the fetch block were not merely repetitive, they were
repetitively wrong (`F-0063`), and moving five copies of a defect into one
place without fixing it would have made the register say the work was done.

**Rejected.** Keeping the extraction purely mechanical. Four defects surfaced
only because the arithmetic was pulled into modules that could be tested at
all — `F-0064` through `F-0068`. A move that refuses to look at what it is
moving is a cheaper change and a worse one.

**Not a mechanical refactor, and recorded as such.** Six behaviour changes
land here: an HTTP error stops being a resource (`F-0063`), the GOLD tab's
country panel gets its yields (`F-0064`), a re-entering country stops
rendering "+Infinity%" (`F-0066`), the M2 chart looks back by date like the
tile beside it (`F-0067`), a missing CPI series stops throwing (`F-0069`), and
two stale comments are corrected (`F-0068`). Each has a test that goes red
against the code it replaced.

**Coverage.** 159 Python + **207** frontend, from 74 at the start of Part F.
`lib/` and `hooks/` are unit-tested; the components are render-tested against
the claims they make about their own numbers rather than their layout.

**What is still not done.** The tab render tests prove a tab mounts; they do
not prove the HOLDINGS table sorts correctly or that the COMPOSITE tiers are
right. The scorers behind those numbers are Python and are covered there; the
join between them is not.

### D-0056 — The twelve MARKETS cards say what they are, and whether they are scored

**Choice.** Each card on MARKETS carries a hover and keyboard-focus tooltip:
what the series is, why it belongs on a sovereign-stress board, and — on a
separate line — what it actually does in the model.

**The part that matters is the second line.** Twelve series sit under a
heading about sovereign stress, and **three** of them are read by a scorer:

| code | role |
|---|---|
| `DGS10` | long leg of the yield-curve factor (35–40% of v2), and the benchmark every sovereign spread is measured against |
| `DGS2` | short leg of `DGS10 − DGS2`; pins at maximum stress at −1.00pp |
| `DCOILWTICO` | 30-day volatility drives the commodity factor (20–25% of v2); petrodollar fallback when Brent is missing |

The other nine are context. Their tooltips say so in those words.

**Why this is a decision and not a copy change.** Presence on that board
implies a connection. `D-0016` exists because the 30Y looked like a factor and
had to be ruled explicitly as ingest-and-display. Every card had the same
ambiguity and no card resolved it. A dashboard that lets a reader infer a
causal claim it does not make is misinforming them politely.

**Rejected.** Writing the role in prose alone. Prose goes stale silently, and
this prose describes Python that lives in another language's test suite.

**So the claim is structured.** Each metric carries `scored: true|false`
beside its text, and `tests/test_markets_tooltips.py` reads `constants.js` and
cross-checks it against the scorers — a card marked unscored that appears in
`stress_score_v2.py` fails the build. Demonstrated rather than asserted, by
flipping `DGS10`:

```
AssertionError: True is not false : DGS10's tooltip says it is not
scored, but stress_score_v2.py reads it
```

The same test pins the two thresholds the tooltips quote — the −1.0 inversion
floor and the 1%/5% volatility bounds — against the scorer that implements
them, so a tuned constant cannot leave the explanation behind.

**`InfoTip`.** The bubble logic came out of `ColHeader`, which already had it.
A portal to `document.body` is load-bearing: both tables here scroll
horizontally and the card grid clips, so an in-place bubble is cut off on
exactly the columns and cards furthest from the middle. Copying it would have
been `F-0062` a third time.

**Keyboard too.** The cards are where this application explains what it
measures, and an explanation available only to a mouse is not an explanation.
`focus` and `blur` open and close the bubble, and the card is focusable only
when it has one.

**Not verified.** The rendering is covered by tests, not by eye — production
is behind basic auth and no screenshot was taken. Placement is "below" for
these cards because they sit at the top of the viewport, and the bubble is
clamped 8px inside the window on both edges, but neither has been seen.

### D-0057 — The Fed Funds card reads the daily rate, not the monthly average

**Choice.** Ingest `DFF` — FRED's **daily** effective federal funds rate — and
point the MARKETS card, the 10Y–FF spread, the default chart selection, the
USA dashboard tile and the yield-curve chart's Fed Funds line at it.
`FEDFUNDS` stays in the pipeline.

**Why, and it is not the cadence.** Measured against live FRED on 2026-09-29:

| series | latest | value |
|---|---|---|
| `FEDFUNDS` — what the card showed | 2026-08-01 | **3.63** |
| `DFF` — daily effective | 2026-09-25 | 3.88 |
| `EFFR` — NY Fed daily | 2026-09-28 | 3.88 |
| `DFEDTARU` / `DFEDTARL` — target range | 2026-09-29 | 4.00 / 3.75 |

Production held `3.63` flat since June. The card was not merely a month
behind — it was **25bp wrong about where policy sits**, on a board whose
fiscal calculator is denominated in yields and whose scenario panel argues
about what the Fed does next. See `F-0072`.

**Rejected: `EFFR`.** More precise — a volume-weighted median of actual
transactions — and three days fresher than `DFF` on the day of measurement.
Rejected because its history starts in 2000 and, more to the point, it is a
*different* quantity from what the card showed yesterday. `DFF` is the same
quantity unaveraged, so the five-year chart keeps its shape and nothing about
the switch needs explaining to a reader.

**Rejected: the target range (`DFEDTARU`/`DFEDTARL`).** It is the freshest of
the four and has a real argument behind it — the COUNTRY tab's scenario panel
models *target* cuts, so the panel and the card quote different quantities.
Rejected for now because it changes a single-value card into a range, which is
a layout question, and because the effective rate sits inside the range within
a few basis points. Recorded in `A-0013` as still open rather than closed.

**`FEDFUNDS` is kept deliberately.** The monthly average is what most
published analysis quotes, and five years of history should not be discarded
to fix a display choice. It is ingested and not shown.

**Guarded.** `tests/test_markets_tooltips.py` now asserts that every code the
twelve cards reference is one some pipeline actually fetches — a card pointing
at an un-ingested code renders a permanent dash, which is the quietest
possible way to break this. The guard that made this change necessary was the
one written an hour earlier, which failed the moment `DFF` was added:

```
DFF is now ingested - revisit the FEDFUNDS card (A-0013)
```

**Side effect worth having.** The yield-curve chart's Fed Funds line was
sixty monthly points against ~1,250 daily ones — the sparse case that produced
`F-0007`. It is now daily like the rest of the curve. The date join is **not**
redundant as a result: `DFF` skips weekends and holidays and publishes behind
the Treasury yields, so an index zip would still pair the wrong dates, just
less visibly.

### D-0058 — The M2 card reads the weekly series, not the monthly level

**Choice.** Ingest `WM2NS` — FRED's **weekly** M2, not seasonally adjusted —
and point the MARKETS card and the USA dashboard's M2 growth chart at it.
`M2SL` stays in the pipeline.

**What this does and does not buy.** Unlike `D-0057`, nothing here was wrong.
Production held `M2SL = 23342.8` for 2026-08-01, matching FRED exactly. And
unlike `D-0057`, **there is no fresher release to move to**:

```
WM2NS  last updated 2026-09-22 12:01  | Not Seasonally Adjusted
M2SL   last updated 2026-09-22 12:01  | Seasonally Adjusted
```

Identical timestamps, because both come from the same monthly H.6
publication. The Fed publishes M2 once a month and no series anywhere is more
current than that.

What it buys is a newer *observation* and more of them:

| | newest observation |
|---|---|
| `M2SL` | 2026-08-01 |
| `WM2NS` | **2026-08-31** |

Thirty days forward, and four to five chart points a month instead of one.

**The cost, and why it is acceptable.** `WM2NS` is not seasonally adjusted.
At the card's display precision the swap is invisible — 23342.8 and 23305.5
both render as **$23.3T** — which is precisely why the tooltip has to say so.
For the year-on-year line, seasonals largely cancel over twelve months, and
`yoySeries` compares by date against a 340–400 day window rather than by
position, so a weekly series is if anything better behaved there than a
monthly one.

**Rejected.** Leaving it. The owner reported the card as stale twice. It was
not *wrong*, but "correct and a month behind the best available reading" is
not a good answer when a thirty-day improvement costs one pipeline entry.

**Rejected.** Showing both. A second M2 tile would take the grid to thirteen
cards and break the 6×2 layout for a distinction most readers do not need.

**Guarded.** `tests/test_markets_tooltips.py` asserts the card reads `WM2NS`,
that `M2SL` is still collected, that the tip discloses "not seasonally
adjusted", and — the one that matters — that it does **not** promise weekly
*releases*. "Weekly" invites exactly the reading that produced `A-0013`, so
the tip says "the Fed publishes M2 once a month" and a test keeps it saying
that.

### D-0059 — The FRED write is an upsert, and only on the dialect that can be

**Choice.** `pipelines/fred_fetcher.py` writes observations through
`upsert_observations()`. On Postgres that is a single
`INSERT ... ON CONFLICT (metric_id, country_id, date) DO UPDATE`. On every
other dialect it keeps the previous check-then-insert.

**Why the branch is not laziness.** `ON CONFLICT` can only arbitrate on a NULL
`country_id` because `ix_metric_country_date` is `NULLS NOT DISTINCT`
(`F-0073`). SQLite has the same NULL-distinct default and no equivalent, so an
`ON CONFLICT` written there would **silently fail to arbitrate** and insert
the duplicate it was added to prevent. One explicit branch beats a fix that
only appears to apply everywhere.

**Verified against production before shipping**, because the tests here run on
SQLite and cannot exercise the Postgres path at all. The statement the new
code emits, run against a real DFF row inside a rolled-back transaction:

```
rows 66400 -> 66400   value 3.88 -> 4.88
VERDICT: UPDATED IN PLACE
rows after rollback: 66400
```

Row count unchanged, value replaced. Without `D-0058`'s predecessor — the
`NULLS NOT DISTINCT` index — that same statement would have inserted a
duplicate, which is exactly the chain worth stating: the constraint is not
merely related to this change, it is what makes it work.

**The dedupe lives in the helper, not the caller.** A FRED payload can carry
one date twice across a revision boundary, and Postgres refuses to let
`ON CONFLICT DO UPDATE` touch a row twice in one statement — *"cannot affect
row a second time"*. Last value for a date wins, which is what the
per-observation loop did implicitly. It sits inside `upsert_observations`
because a helper that raises on input its only current caller happens never to
send is a trap for the second caller.

**Counts come from a SELECT, not from the write.** `inserted` and `updated`
feed `update_logs`, and `ON CONFLICT` does not report which branch it took per
row without a `RETURNING` and an `xmax` trick. Reading the existing dates once
per metric gives the same numbers on both dialects, which matters more than
saving a query.

**Rejected.** Leaving it at the constraint. With `F-0073` applied but the
fetcher unchanged, two overlapping runs no longer duplicate — they raise
`IntegrityError`, the metric's batch rolls back, and the run logs `partial`.
Loud rather than silent is the right direction, but it is still a failure
mode, and every deploy starts a FRED run on top of the nightly schedule, so
overlap is ordinary rather than exotic.

**Not changed.** The N+1 SELECT is gone as a side effect — one query per
metric instead of one per observation, ~1,800 fewer round trips for DFF alone
— but performance was not the reason and no timing claim is made here.

### D-0060 — CDS is shown as part of the score, and the country panel is where the surfaces meet

**Choice.** Four changes, answering *"is the CDS surface telling any of the
sovereign stress story, and can it be made evident?"*

1. **The methodology panel lists all six scored dimensions** and all three
   multipliers, from one list that a test cross-checks against the scorer
   (`F-0076`).
2. **The country panel carries a `StressContribution` block**: the country's
   tier, its composite score, and a segmented bar breaking that score into the
   dimensions that produced it - CDS among them, with its share.
3. **The CDS tab gains two columns**: the country's composite tier, and what
   its CDS spread contributed in points and as a share. A country ranked on
   CDS alone renders at 100% and in the CDS colour.
4. **A refused quote explains itself** rather than rendering as a dash.

**Why the country panel and not a new tab.** The COMPOSITE tab ranks countries
and the CDS tab lists spreads; neither said how the two relate, and a third
surface would have been a fourth thing that does not relate to the others. The
country panel already gathers holdings, gold, reserves, spread and CDS for one
sovereign - it was the only place that was already answering "what is going on
with this country", and it was doing it without ever mentioning the score.

**The breakdown is derived from the same fields the tiering used**, not
recomputed. A second implementation of the scoring arithmetic in JavaScript
would drift, and the drift would be invisible precisely because both numbers
would look plausible.

**Rejected.** Showing every dimension including the zeroes. A country with one
contributing dimension would render five empty segments, and the panel's job
is to say what is driving the score rather than to enumerate what is not.

**Rejected.** Joining the CDS tab to the composite on ISO code. The CDS metric
namespace uses its own country token - `RUSSIA`, not `RUS` - and
`CdsAllItem`'s docstring says so explicitly. The join is on country name,
which both carry.

**What this does not do.** It does not make CDS coverage better. Sixteen
countries have an admitted quote out of forty-eight scored, and four of those
contribute points. The surface now states that honestly instead of implying
breadth it does not have.

### D-0061 — CDS is on the country panel: tile, contribution and history

**Choice.** The country panel now carries CDS three ways:

1. **The 5Y tile works at all** (`F-0078`) — it had never resolved a country.
2. **`StressContribution`** shows CDS as a share of the composite score
   (`D-0060`).
3. **A 5Y CDS history chart** sits beside holdings, gold and reserves.

**The history comes from `/cds?country=`, not `/timeseries`.** The ISO → metric
name map lives server-side, and a second copy of it in JavaScript is `F-0062`
for the third time. The endpoint the panel already calls now returns the
series.

**The chart is withheld when the latest quote was refused.** Charting a
history whose most recent point the tile above it denies would put a line on
screen that the rest of the panel contradicts. Ninety days, matching the
widening window the scorer measures over, so the chart and the score describe
the same span.

**A refused quote states its reason on the tile** — "stale (75d old)", "not
quoted as a running spread" — rather than the generic "Not factored into
stress score", which was true of both a country nobody quotes and a country
whose quote was thrown away.

### D-0062 — The 10Y CDS and term-structure surfaces are removed

**Choice.** The 10Y CDS column, the Term Structure column, the curve-inversion
summary tile, the `INVERTED` badge and the term-structure component of the CDS
score are all gone.

**Established, not assumed.** Fetching the live board and reading its headers:

```
Country | S&P | 5Y CDS | Var 1m | Var 6m | PD (*) | Date
any mention of 10Y anywhere in the payload? False
```

It is a 5Y board. The string "10Y" does not occur in what the source sends.
The 500.0 values that used to populate those columns were never 10Y data —
they were the ISDA standard running coupon read from the wrong column by an
earlier scraper, and the current fetcher's docstring already said so.

**Rejected.** Keeping the columns as permanently empty. A column of dashes
reads as *missing data* — something that might arrive tomorrow — rather than
as a tenor this source does not carry. `F-0074` is what happens when a reader
tries to fill such a gap.

**The scoring component goes with them.** `+3` for an inverted curve could not
be reached: the only inversions it ever produced were a frozen July
placeholder subtracted from a current 5Y. A branch that cannot fire is not
conservatism, it is decoration that reads as rigour.

**A real 10Y would need a different source.** Sovereign 10Y CDS exists, from
licensed vendors. That is a procurement decision, not a scraping one, and
nothing here should pretend otherwise.

### D-0063 — The board's other columns are captured and used

**Choice.** The fetcher now reads the S&P rating, Var 1m, Var 6m and implied
PD it had been discarding on every run, and persists implied PD and the
six-month change as `{COUNTRY}_CDS_PD` and `{COUNTRY}_CDS_VAR6M`.

The CDS tab shows **6M Change** and **Implied PD** in the two column slots the
dead 10Y and Term Structure columns vacated, and the summary tile counts
*Widening >20% (6M)* instead of inversions.

**Var 6m is the genuinely new data.** CDS ingest began 2026-07-10, so a
six-month change predates everything stored here. It is the one widening
measure available that is not derived from our own short history.

**PD is stored rather than derived**, although it is the spread times 1/60
(`F-0080`). Deriving it would put that constant in this codebase, where it
would silently stop matching the source if WGB ever changed its recovery
assumption. Storing the source's own number keeps the assumption where it
belongs.

**The extras are optional by construction.** A board that drops these columns
costs us the extras, not the spread — there is a test for exactly that,
because the spread is the thing the score depends on.

**Not taken.** The board lists **33 sovereigns** and `CDS_INSTRUMENTS`
configures 21. `A-0014`'s objection that CDS coverage is only 33% of scored
countries is therefore partly self-inflicted, and widening the configured set
is the cheapest available improvement to it. Left for a ruling with the rest
of `A-0014`.

### D-0064 — Every sovereign the board carries is configured

**Choice.** `CDS_INSTRUMENTS` goes from 21 entries to 31, covering all 30
sovereigns the World Government Bonds board publishes, plus Saudi Arabia,
which it does not (`F-0075`).

Added: Austria, Belgium, Denmark, Finland, Ireland, Israel, Netherlands,
Portugal, Sweden, United Kingdom.

**Why it was worth doing first among `A-0014`'s options.** That assumption
cites CDS coverage at 33% of scored countries as an argument against the
dimension. Ten of those absences were not a data problem — nobody had
configured them. Arguing about whether a dimension deserves its weight while a
third of its available inputs are switched off is arguing about the wrong
thing.

**What it buys, stated honestly: coverage, not signal.** Every one of the ten
prints well under the 100bps band — Sweden 7.36, Denmark 8.91, Netherlands
10.34, United Kingdom 21.08, Israel 59.08. None will score at current levels,
and that is the correct outcome: the dimension should be silent on these
because they are calm, not because nobody asked.

It also means the denominator in any future coverage argument is real. A
country that is quoted and scoring zero is evidence; a country that was never
requested is not.

**The ISO map moves with it.** `CDS_NAME_BY_ISO` gains all ten, so the country
panel can reach them — `tests/test_cds_country_lookup.py` fails in both
directions if a configured country has no ISO or an ISO maps to a token
nothing stores, which is what made this change mechanical rather than
error-prone.

**The board list is recorded, not fetched, in the test.** A test that hit the
live board would fail on the source's outage rather than on our regression.
What is pinned is what the board was observed to carry on 2026-09-29, and that
the only configured absentee is the one `F-0075` recorded deliberately.

**Correction to an earlier count.** I reported the board as listing 33
sovereigns. It carries **30** — the earlier figure counted header and spacer
rows in the raw table.

### D-0065 — The CDS elevated band moves from >100bps to >200bps

**Ruling.** The owner raised the first CDS level band to 200.

**What it was.** `>100 bps: 5 pts`. Measured against the live board on
2026-09-29:

```
India         87.7   below the old band
Mexico        91.0   below
Brazil       129.6   ABOVE — ranked WATCH on a composite of 5.0,
                     entirely from this band
South Africa 130.9   ABOVE
Turkey       248.1   above
Egypt        307.3   above
```

A threshold that separates 91 from 130 is not separating calm from stressed.
It is separating two ordinary emerging-market spreads, and it was producing a
false positive: Brazil appeared on the COMPOSITE tab because its CDS is normal
for Brazil.

**What changes.** Brazil and South Africa stop scoring. Turkey and Egypt are
unaffected — both were already above 200, so this removes false positives
without touching a single true one. Nothing else on the board moves.

**Recorded rather than silently smoothed:** the ladder is now
200 / 250 / 500, which leaves a narrow 50bps window worth 5 points before the
250 band takes over at 10, and then 250bps for the next 5. The bottom rung is
compressed. Re-spacing the upper bands is a separate judgement nobody has
made, so it has not been made here — but the next person to look at this
ladder should know it was left uneven deliberately.

### D-0066 — Dimension 4, Sovereign Spread, is retired from scoring

**Ruling.** The owner retired it.

**Why.** `F-0079` measured it across all 48 scored countries: **0 countries,
0 points**. It scores a sovereign more than 50bps **above** the US 10Y and
holds yield data only for the fourteen developed markets in
`SOVEREIGN_YIELD_CODES`, every one of which trades **below** the US:

```
AUS  -22.5bps    FRA  -124.0bps
GBR  -25.1       ITA  -125.4
NOR  -95.4       BEL  -148.0
KOR  -95.4       CAN  -156.5
```

It could only fire for emerging markets and held no yield data for any. Twenty
points that no country could earn.

**Measured, not scored.** `spread_bps` is still computed and still displayed —
Japan sitting 300bps below the US 10Y is a real fact about the world and the
COMPOSITE tab shows it. What is gone is its ability to award points.

**`spread_score` is removed from the payload and the schema, not set to
zero.** A field that is always zero is a trap: a reader takes it for a
dimension that happens to be quiet this week. `api/schemas.py` carries a note
where it used to be.

**Consequences.** The raw maximum drops from 185 to 165. Five scoring
dimensions remain. `ui/src/lib/dimensions.js` loses the entry and
`tests/test_composite_dimensions.py` — which cross-checks that list against
the scorer in both directions — is what forced every dependent number to move
with it.

**What was NOT done.** Repairing it. Giving the spread dimension emerging-
market yield data would make it fire, and would then measure roughly what CDS
measures for roughly the same countries — `A-0014`'s third objection, which
was hypothetical while the dimension was dead and would become real the moment
it was revived. Retiring it is the choice that does not create that problem.

### D-0067 — The CDS ladder is re-spaced to 200 / 350 / 600

**Ruling.** The owner smoothed the ladder.

`D-0065` raised the floor to 200 and left the upper rungs where they were, at
250 and 500. That gave **5 points across a 50bps window** and the next 5
across 250bps — steeply sensitive at the bottom and flat above it. `D-0065`
recorded the compression rather than silently fixing it, because re-spacing
was a separate judgement. This is that judgement.

```
        was              now
  5 pts  >200     |   5 pts  >200
 10 pts  >250     |  10 pts  >350
 15 pts  >500     |  15 pts  >600

 gaps:   50, 250  |  gaps:  150, 250
```

**The consequence is not cosmetic, and it is a real country.** Egypt prints
307.3bps. Under the old rungs that was "significant" and worth 10; under the
new ones it is "elevated" and worth 5. Egypt's composite sat at **exactly
50.0** — the STRESSED floor — so it becomes **ELEVATED**.

That is the ladder doing what it was re-spaced to do: 307bps is elevated
rather than significant once "significant" means 350. But a five-point change
tipping a country across a tier boundary is worth stating plainly rather than
discovering later, and Egypt's position exactly on the threshold is the kind
of coincidence that makes a threshold look arbitrary when it moves.

Turkey at 248.1 is unaffected — it was in the first rung before and is in the
first rung now.

**Named constants, not literals.** `CDS_ELEVATED_BPS`, `CDS_SIGNIFICANT_BPS`
and `CDS_DISTRESS_BPS`. The ladder is now stated once and the tests assert its
shape — monotone, no rung compressed below 100bps, and no rung more than twice
the width of the one beneath it — rather than asserting three numbers that
would have to be edited in lockstep.

### D-0068 — The COMPOSITE table gives its space to the columns that carry numbers

**Choice.** The **Activity** column drops from `minWidth: 260` to
`minWidth: 170, maxWidth: 240`; the **CDS Term** column is removed entirely
(`D-0062`); cell padding goes from 5px to 8px and header padding from 4px to
7px.

**Why it looked the way it did.** Activity was the widest column on a
thirteen-column table and was empty in every row — not because countries had
no signals, but because `active_signals` was being stripped by the response
model (`F-0082`). The layout was giving the most room to the one column that
could never show anything.

Fixing `F-0082` fills it; narrowing it stops it dominating a table whose other
columns are numbers that were being squeezed to 5px of padding.

**It stays sticky.** Pinning Activity to the right edge is what lets the
numeric columns scroll under a persistent explanation, which is worth more
than the width it costs — the complaint was the proportion, not the position.

### D-0069 — The analyst brief calls Anthropic, whose key is actually deployed

**Choice.** `/api/analyze/country` posts to `https://api.anthropic.com/v1/messages`
with `claude-haiku-4-5-20251001`, guarded on `ANTHROPIC_API_KEY`.

**Why not set a Grok key instead.** It would work, and it would be the wrong
repair: the UI has always credited Claude Haiku, an Anthropic key has always
been deployed, and the only thing missing was code that used them. Adding a
second provider's credential to satisfy code nobody had reconciled is paying
to keep a mismatch.

**Haiku, deliberately.** The brief is bounded at 750 tokens and rate-limited
per client, and the work is summarising figures already gathered from the
database by `_gather_brief_context` — not reasoning its way to them. The model
is named once as `BRIEF_MODEL` so the footer's claim has something to be true
about, and a test asserts the two agree.

**What carried over unchanged.** The 422 on anything but a 3-letter ISO code
(`F-0013` — the prompt is assembled server-side and free-form input is
refused), the per-client hourly limit, and the deliberate absence of a
`Depends(get_db)` so a 75-second await cannot hold one of ten pool
connections.

**What changed in the error path.** The handler logged `f"Grok API call
failed: {e}"` and returned the provider's name to the client. It now logs the
exception *type* and returns a flat "analysis failed" — `F-0010`'s lesson
about exception text carrying request detail applies to any client, and the
key now travels in a header where it is likelier to appear in one.

### D-0070 — The cross-asset table trades its gauge for an explanation

**Choice.** The `StressBar` gauge in the Score column is replaced by the
number and its multiplier; every cell's padding drops from `10px 12px` to
`8px 9px`; and the reclaimed space becomes an **Analysis** column.

**Why the gauge went.** It occupied `minWidth: 140` to answer *"how full is
this score out of 150"*, which is not a question anyone asks of a
de-dollarisation table. The number plus a tier colour says the same thing in a
quarter of the space, and the multiplier beside it says what a bar could not:
whether the score is large because the signals are large, or because a 2×
divergence multiplier was applied to modest ones.

**The analysis is composed, not generated.** `lib/crossAssetNarrative.js`
turns the row's own fields into a headline and its evidence. It is not an LLM
call, and that is a decision rather than a shortcut: it must be identical for
identical rows, cost nothing per render, and work when the brief endpoint is
down — which, until `D-0069`, it always was.

It lives in `lib/` with fourteen tests rather than as a ternary chain inside a
`<td>`, because prose assembled inline is exactly what `F-0081` was.

**The headline names the mechanism.** For DIVERGENCE it reads *"Selling gold
into a +12.4% 3M rally — raising cash, not rebalancing"*. That distinction is
the table's entire subject, and it was previously left for the reader to infer
from a tier badge and two percentages in separate columns.

### D-0071 — The brief's provider is selectable, and Grok is the default

**Ruling.** The owner set `GROK_API_KEY` as a Fly secret and asked for the
provider to be selectable with Grok as the default.

**One table, not a branch.** `BRIEF_PROVIDERS` holds the four things that
differ between providers — which setting carries the key, where to post, which
model, and how to read text back out. The handler reads only from it; a test
asserts no provider-specific literal (`api.x.ai`, `x-api-key`, `Bearer `,
a model name) appears anywhere in the handler body.

`F-0084` was three places disagreeing about which provider was in use. The way
not to repeat that is to have one place that knows.

**Availability is reported, not assumed.** `GET /api/analyze/providers`
returns each provider's id, label, model and whether its key is **present** —
never any part of one. The panel offers only configured providers and shows
the others disabled with a reason. Offering a provider whose key is absent
produces a 503 the reader cannot act on, which is `F-0084` made interactive.

**The footer credits what ANSWERED.** The response carries `provider` and
`model`, and the panel renders that rather than what was requested. Those
differ the moment a default changes or a request falls back — and a hardcoded
"Generated by Claude Haiku" is precisely how `F-0084` began.

**The selector degrades rather than blocks.** `Generate` is disabled only
while loading, never on a missing selection. The selector depends on
`/analyze/providers`; if that is slow or fails, no provider is chosen, the
request omits the field, and the **server** applies its default. Caught by an
existing test that went red when the button briefly required a second network
call to succeed first — the feature falls back to the behaviour it had before
the selector existed.

**Rejected: a UI to paste the key into.** There is nowhere safe to put it —
the database means a plaintext credential in a shared store, and `fly.toml`
declares no `[mounts]` so the filesystem does not survive a deploy. It would
also invert the credential hierarchy: the app sits behind one shared basic-auth
credential that is itself on the rotation list, and a secret-entry box behind
it means the weakest credential guards the strongest. `flyctl secrets set` is
versioned and auditable; a UI paste is not.

### D-0073 — The six country tiles explain themselves, and the CDS tile is coloured by the ladder

**Choice.** Each tile on the country panel carries a hover and
keyboard-focus tooltip, through the same `InfoTip` the MARKETS cards and
column headers use (`D-0056`) rather than a fourth implementation.

Each says what the figure is and what it does in the model — including, where
it is true, that it does **nothing**. The Spread tile states plainly that
`D-0066` retired it from scoring and that it awarded zero points to zero
countries across all 48.

**A drift caught while writing them.** The 5Y CDS tile still coloured on
`>250` and `>100` — the rungs `D-0065` and `D-0067` replaced with 200/350/600.
A tile whose colour disagrees with the score it illustrates: Turkey at 248bps
sits in the first scoring rung and was painted as the second.

Third appearance of the same drift (`F-0068`, `F-0076`, `F-0081`), so it is
derived rather than written down again. `cdsBandColor` reads `CDS_BANDS`, and
the tooltip's ladder is generated by `cdsBandText()` from the same constant
the Python cross-check already pins to the scorer — so the tile's colour, the
tile's text and the scorer's arithmetic now cannot disagree.

### D-0074 - Every surface declares its sources, and the watchdog is the only judge

**The ask.** *"We want the user to be confident in what's in the UI surface,
so let's make sure each surface either provides that assurance, or we improve
our data."*

**What I found first.** `pipelines/freshness_watchdog.py` already answered
this exactly - per source, with a tolerance tuned to that source's own
release cadence, a note explaining it, and detection of a single lagging
series inside an otherwise current source. `GET /api/freshness` already
served it. **Nothing on the screen consumed it.** The machinery was right
and silent, which by `P9` is the same as not having it: a check nobody can
see is a check nobody must obey.

**Choice.** Each tab names the sources it draws on, and `DataConfidence`
reports the watchdog's verdict on exactly those. Not a generic "last
updated" - a per-source ruling against what that source is supposed to do.

| Surface | Declared sources |
|---|---|
| HOLDINGS | `tic` |
| CROSS-ASSET | `tic`, `gold_reserves`, `gold_price`, `reserves_ex_gold` |
| COMPOSITE | `tic`, `gold_reserves`, `money_supply`, `oil`, `cds`, `sovereign_yields` - labelled *Score inputs* |
| CDS | `cds` |
| GOLD | `gold_reserves`, `gold_price` |
| MARKETS | `treasury_yields`, `oil`, `dollar_index`, `gold_price` |
| Country panel | `tic`, `gold_reserves`, `reserves_ex_gold`, `cds`, `sovereign_yields` |

Declared per tab rather than showing all ten everywhere, so a tab is never
reddened by a source it does not draw on - which is the failure that trains
a reader to ignore the strip.

**Collapsed by default**, because the tab that most needs this is the one
where the news is worst, and a permanent block of red is a permanent block
of red. Expanded, it gives each source's date, age, its tolerance *and where
that tolerance comes from*, and any laggard.

**Laggards are surfaced.** `reserves_ex_gold` is "ok" at 60 days and
contains `TRESEG_CODES.RUS` at 333. An aggregate that reports the first
without the second is the specific thing this exists to stop.

**One judge.** The footers stopped ruling on their own dates (`F-0087`) -
they state an age, `DataConfidence` says whether that age is acceptable, and
the tolerance behind it comes from the server. Three components had held
opinions about staleness; one does now.

**A stale note found while doing it.** The watchdog's `cds` note read
"Blocked by Investing.com 403 from datacenter IPs pending proxy". That
source was replaced by the World Government Bonds board and CDS has been
current for months. The note described an outage already fixed - and it was
about to be put on screen. A note nobody revisits eventually becomes the
thing it is warning about.

**What it says today, in production.** This is the point of the decision,
and it does not flatter us:

```
critical  tic               303d (tolerance  55)  -> dimension 1, up to 50 pts
stale     money_supply      637d (tolerance 420)  -> dimension 3, up to 35 pts
stale     gold_reserves     272d (tolerance 200)  -> dimension 2, up to 40 pts
ok        reserves_ex_gold   60d  - laggard TRESEG_CODES.RUS at 333d
ok        oil 8d, dollar_index 5d, gold_price 2d, treasury_yields 1d, cds 1d
```

**The three largest dimensions - 125 of 165 available points - run on data
between 9 and 21 months old.** The user asked for assurance *or* better
data. This half delivers the assurance, and the honest content of that
assurance is that the composite's inputs are old. Saying so on the screen is
the prerequisite for fixing it, not a substitute: the data half is open
work, tracked as `A-0015`.

### D-0075 - TIC reads SLT Table 5; the history file keeps its parser

**Choice.** `TIC_MFH_URL` is `slt_table5.txt`. `mfhhis01.txt` keeps a name,
`TIC_MFH_HISTORY_URL`, and nothing scheduled reads it.

**Why keep the legacy parser at all.** Table 5 carries a rolling 13 months.
`mfhhis01.txt` carries years, and that history is the only machine-readable
source for it. The two-row header path is therefore a live format with a real
use, not code kept out of sentiment - and it is fixture-tested, including the
case that matters: a bare year row (`Country 2025 2025`) must not be mistaken
for an ISO month row, since both begin with "Country".

**Dates stay on the first of the month.** The file says "Holdings at end of
time period", so dating rows to month-end would be more accurate and would
tighten the healthy age range from 77-106 days to 47-76 - a meaningfully
faster detection of a missed release. It is not done here because every
existing row is dated to the first, so the change is a migration of the whole
series rather than a pipeline edit, and a half-applied one would duplicate
history under two conventions. Recorded as the reason the tolerances in
`F-0089` are as large as they are, and left as open work rather than done
quietly as part of something else.

**Thresholds derived, not guessed.** `F-0089`. The watchdog warns at 110 and
the pipeline refuses at 140, both computed from the release calendar: newest
row 77 days old on arrival, ~106 the day before the next release, ~136 after
one missed release, ~166 after two. The test file asserts against those
derived figures rather than against the constants, so a future edit to a
constant cannot also edit its own justification.

**What this does not fix.** `money_supply` and `gold_reserves` remain MANUAL
with no fetcher - 75 of 165 points. `A-0015`.

### D-0076 - Gold reserves come from IMF IRFCL, monthly, not from a hand-downloaded WGC file

**The ask.** *"Go the gold reserves, if you can find a real ticker. That's why
we do the downloads."*

**There is one, and the downloads were its own output.** The files in
`data/incoming/` are named
`World_official_gold_holdings_as_of_Sep2026_IFS.xlsx`. The `IFS` is IMF
International Financial Statistics: the World Gold Council's reserves table is
a re-publication of an IMF feed. We were reading a **quarterly** re-issue of a
**monthly** series, three months behind it, by hand.

**The ticker.** IMF **IRFCL** (International Reserves and Foreign Currency
Liquidity), indicator `IRFCLDT1_IRFCL56V_FTO` - Reserves Data Template line
56, "gold (including gold deposits and, if appropriate, gold swapped)", volume
in fine troy ounces. SDMX 2.1, key order `COUNTRY.INDICATOR.SECTOR.FREQUENCY`.

```
https://api.imf.org/external/sdmx/2.1/data/IRFCL/.IRFCLDT1_IRFCL56V_FTO..M
```

Note the host. Every older example uses `dataservices.imf.org`, which **no
longer resolves at all** - not a 404, no connection. The new API was found by
walking `/dataflow` and looking for a reserves dataset; `IFS` itself is no
longer published as a dataflow.

**Validated before it was wired in, not after.** 68 countries appear both in
this feed and in the WGC data already in the database:

| | count | |
|---|---|---|
| agree within 10% | **55** | including every large holder to the decimal |
| real change WGC had missed | 12 | Turkey 534.9 -> **791.4** t, Poland 581.6 -> 648.0, Czechia 76.6 -> 85.8 |
| scale defect | 1 | Brazil - see `F-0093` |

USA 8133.5/8133.5, Germany 3350.2/3349.1, Italy 2451.8/2451.8, France
2437.0/2437.0. The sum of the latest reading per country is 30,785 tonnes
against a world official total of roughly 36,000, which is the right shape for
83 of ~100 reporting countries.

Turkey is the case that justifies the change on its own: **+256 tonnes** that
the stale file simply did not contain, in a country the composite scores.

**Choice: IRFCL is primary, the WGC CSV is retained as backfill.** IRFCL
carries 83 countries; the WGC set has 28 that IRFCL does not (Canada, UAE,
Qatar, Kuwait, Pakistan and others that do not file the monthly template).
Dropping the CSV would have traded 272-day-old data for no data at all for
those. Both write to the same `GOLD_RESERVES` metric, so the UI, the composite
and the watchdog all read one series - a parallel metric would have left the
tab showing the stale one with the fresh data beside it unread, which is
`F-0090`'s shape.

**Tolerance derived, not inherited.** The watchdog's 200 days was marked
PROVISIONAL and was set for a quarterly hand-downloaded file. IRFCL publishes
about three weeks after month end and rows are dated to the first of the data
month, so the newest row is ~50 days old on arrival and ~80 the day before the
next release. Now **95**. Derived explicitly because today produced two
thresholds (`F-0089`, `F-0091`) that no healthy source could satisfy, and in
both cases the false alarm concealed the real defect.

Scheduled monthly on the 25th at 05:15 UTC, after the 05:00 watchdog.
`POST /api/fetch/gold-reserves-imf` triggers it.

**Validated is not the same as working.** The *values* were cross-checked
against production before this was wired in, and that check was sound. The
*write path* still failed on its first real run, because the feed carries
several series per country and `ix_metric_country_date` admits one row per
country-month (`F-0095`). Validating a source says nothing about the code that
stores it.

**What this did not fix.** Angola's entire IRFCL series is a thousandfold out
and is rejected, so Angola has no gold data rather than wrong gold data. It is
not in the WGC set either. `A-0018`.

### D-0077 - Age is measured from when the period ended, not from its label

**A-0016.** Every series is stored dated to the START of the period it
describes. A TIC row for July 2026 is dated `2026-07-01`; a broad-money row for
calendar 2025 is dated `2025-01-01`. But the observation describes a period that
**ends** later - TIC's own file says "Holdings at end of time period" - so an
age measured from the stored date overstates staleness by up to a full period.

Every tolerance had been inflated to absorb that, and the inflation was large
enough to matter:

| source | period | age by label | age by coverage | tolerance was | now |
|---|---|---|---|---|---|
| `tic` | month | 91d | **61d** | 110 | **85** |
| `gold_reserves` | month | 60d | **30d** | 95 | **65** |
| `money_supply` | year | 637d | **273d** | 960 | **600** |

960 days is wide enough to be nearly decorative. That was not generosity - it
was the cost of measuring a calendar year's data from the first of January.

**Not done as a migration, which is what `A-0016` proposed.** Rewriting three
whole series is an irreversible `UPDATE` across the history, a half-applied
version would leave one holding recorded under two conventions, and the gold
series would collide with itself - WGC quarter-start rows map to the same
quarter-end as IMF month-start rows for the third month. Deriving
`coverage_end` at read time is the same arithmetic with nothing to undo, and it
fixes the display problem too, which a migration would also have had to do
separately.

I have recorded this as a deliberate substitution rather than doing it quietly:
the destructive version remains available if the stored dates themselves matter
for some reason I have not seen.

**Computed as "first day of the next period, minus one day"** rather than from a
table of month lengths, so February and leap years need no special case.
`period` is declared on all ten sources and a test fails if any is missing -
a missing period silently defaults to daily, which would restore the original
overstatement for exactly the monthly and annual sources this is about.

**Only the three inflated tolerances were retuned.** `reserves_ex_gold` at 100
and `sovereign_yields` at 70 were set by `calibrate` from observed data, and
shifting the measurement basis by a month gives them *more* headroom, not less -
so leaving them cannot cause a false alarm. Stated in a test rather than left
for someone to conclude they were overlooked.

**One threshold deliberately keeps the old basis.** `MAX_SOURCE_AGE_DAYS = 140`
in `treasury_holdings.py` is applied against the parsed row date, which is the
first of the data month; the pipeline never sees a coverage end. Two thresholds
measured against two different things is exactly `F-0087`, so the difference is
written down in the test rather than silently carried.

**On screen**, the confidence strip now shows the coverage end and reads
"61d since period end" rather than "91d old". Showing a period label beside an
age measured from the period's end is how a reader concludes the two disagree.

### D-0078 - The surface states which dimensions can speak about each country

**A-0019 option 1.** `F-0097` removed the false-exit path, and the honest
consequence is that dimension 1 - 50 of 165 points, the largest in the model -
reaches only the twenty countries SLT Table 5 names. The other 28 get nothing
from it, **not because they look calm but because their position is unknown**.

A composite that ranks 48 sovereigns while its largest dimension reaches 20 of
them is weighted in a way no reader would infer from the number alone. Germany
scores 8.0 out of a possible 115 rather than 165, and nothing on screen said so.

**Chosen over re-weighting, on purpose.** Option 4 - scoring each country out of
the dimensions that can actually speak about it - is more principled and changes
every number in the model, which needs a decision rather than an
implementation. Option 1 changes **no number** and tells the reader what the
number covers. `ui/src/lib/coverage.test.js` asserts the module cannot alter a
row, so the disclosure cannot quietly become option 4.

**It generalises a pattern that already existed for one dimension.**
`StressContribution` explained a rejected CDS quote rather than showing a blank,
and the COMPOSITE table already carried a `◦` marker for a country with no CDS.
Both were right, and both covered one dimension of three that can go silent.
Explaining Treasury while leaving broad money at a bare zero would have been the
half-honest version, so all three reasons live in one module and there is one
marker instead of one per dimension.

| dimension | max | goes silent when |
|---|---|---|
| Treasury | 50 | the country is not among Table 5's twenty (`F-0097`) |
| Monetary / M2 | 35 | its newest broad money figure is over 3 years old (`F-0092`) |
| Sovereign CDS | 20 | no quote, a stale one, or not a running spread (`F-0074`) |

**On the COMPOSITE table**, a muted badge beside the score counts the silent
dimensions and names them on hover, with the points they would have been worth:
*"50 of 165 points cannot be scored for this country"*. Muted deliberately - an
unavailable dimension is a limit on what the score means, not a finding about
the country, and colouring it like a risk signal would invert the point.

**On the country panel**, the breakdown gains a NOT SCORED FOR THIS COUNTRY
block listing each silent dimension, its maximum, and why. The existing
"no single dimension is contributing points" line was also misleading where the
reason was coverage rather than calm, so it now distinguishes the two.

**The reason text names the figure.** *"it last reported $103.1bn in
2025-12 ... Scored as nothing, not as zero"*. `F-0097` was a fabrication
precisely because it asserted a number nobody had observed; the fix has to
assert only what was observed, and say when that was.

**What this does not fix.** Two countries with the same score may still have
been measured on different amounts of evidence, and the score itself does not
encode that. `A-0019` options 2-4 remain open; this closes option 1 only, and
the register says so rather than marking the assumption resolved.

### D-0079 - The "All Other" aggregate is captured, and reported once

**A-0019 option 2.** SLT Table 5 names twenty holders and folds every other
foreign holder into a single **"All Other"** row. `F-0097` established that a
country absent from the table is inside that row rather than at zero, and
`D-0078` marked that on each score as a gap. This closes the other half: the row
is published, so the non-reporters' **combined** position is knowable even
though no individual position is.

Live at 2026-07: **$1,842.4bn, 19.92% of all foreign holdings**, -0.43% MoM,
-1.00% over three months, **+2.74% over twelve**, three consecutive monthly
declines.

**Grand Total is captured with it**, because All Other alone is close to
uninterpretable. That +2.74% level rise came with a *falling* share - total
foreign holdings grew faster - so a level-based reading would have called it
accumulation by the non-reporters when the opposite was happening. The share is
the figure that means something, and it needs both rows.

**The line this must not cross.** All Other covers roughly a hundred holders:
sovereign wealth funds, private institutions, and the 28 scored countries
outside the table. A -1% move says *someone* reduced. Turning that into 28
country-level findings would be `F-0097` in a new costume - a number nobody
observed, asserted about a named sovereign - and that defect cost 1,050 points
across 32 countries.

So it is a **system-level** series and the constraint is enforced rather than
intended. `tests/test_tic_all_other.py` asserts it lives in `summary` and not in
the per-country loop, that `CompositeCountry` has no field for it, that the
signal module never touches `Country`, and that it reads only rows with
`country_id IS NULL`.

**It earns no points for anyone.** Option 2 adds context, not score. That is
the whole of it, and the tests are what keep it that way.

**Notability is judged on the share, not the level**, at half a percentage point
over three months - derived from the observed series, which held 19.3%-20.1%
across thirteen months. The real current reading is **not** flagged: a brand-new
signal that fires on its first live data is the cry-wolf shape of `F-0089`,
`F-0091` and `F-0095`, and a test pins that too.

**One parser, not two.** `parse_tic_mfh` gained an `admit` argument rather than
a second function, because two parsers would each own a copy of the
column-to-month mapping and an off-by-one in either would silently date July's
aggregate to May. A first attempt rewrote the text so the aggregates were the
only data rows and returned nothing, because `SKIP_ROWS` drops those labels
however they arrive.

**"Of Which: Foreign Official" is still excluded.** It is a subset of Grand
Total, not a peer of All Other, and admitting it would double-count. It is also
the single most interesting remaining aggregate for this application's thesis -
central banks selling to private buyers shows up there and nowhere else - and is
left as open work rather than folded in here.

**On screen**, once, above the table, never on a row: level, share, three
windows, the decline run, and its own note saying it does not say who. Coloured
only when the share moves. The `D-0078` coverage tooltip now points at it -
*"it moves with this country in it, but says nothing about this country
specifically"*.

**Freshness needs no new entry.** The watchdog's `tic` pattern is `TIC%`, which
already matches both aggregates, and they arrive in the same file as the country
rows so their age is identical. The `A-0017` diagnostic joins on `country_id`
and so correctly excludes them from a per-country distribution.

### D-0080 - Foreign Official is captured: what central banks are doing

Table 5 publishes **"Of Which: Foreign Official"** - US Treasuries held by
central banks and sovereign funds, across every holder, named and unnamed.
`D-0079` deliberately left it out as out of scope; this takes it, because it is
the one cut of the table that separates **official** selling from private
selling, which is the question this application exists to ask.

**What it says today.**

| | 2025-07 | 2026-07 |
|---|---|---|
| Official holdings | $3,886.5bn | **$3,773.1bn** (-2.92%) |
| Official share of all foreign holdings | 42.66% | **40.80%** (-1.86pp) |
| Private (Grand Total minus official) | $5,223.0bn | **$5,475.0bn** (+4.82%) |
| Bills as a share of official | 10.55% | 9.39% (-1.16pp) |

**Official holdings fell in 9 of the last 12 months while private holdings
rose.** That is the clearest statement of this application's thesis available
anywhere in its data, and it was sitting in a row the parser was skipping.

**The private side is derived, not stored** - Grand Total minus official - so
there is no third figure to keep in step with two others.

**A threshold derived here, not inherited.** `D-0079` set
`SHARE_MOVE_PCT_POINTS = 0.5` for All Other. Against this series that fires on
**7 of 10 three-month windows**: Foreign Official is far more volatile in share
terms. Carrying a number from where it was derived to where it was not is
exactly `F-0089` and `F-0091`, so it was measured again.

It was then **not used at all**, because no magnitude works. The observed
3-month moves run -1.21 to +0.55 with no gap between ordinary and notable:
0.75pp fires on 4 of 10 windows, 1.0pp on 2, 1.25pp on none. Rather than pick a
number from a continuum and call it a threshold, the rule is **persistence** -
the share fell in at least 8 of the last 12 monthly steps AND moved at least
1.0pp cumulatively. One noisy month cannot produce that, and both halves are
computable from the history that exists.

**The calibration limit is stated, not buried.** This is one thirteen-month
window, which is all Table 5 carries; `FO_CALIBRATION_MONTHS = 13` records it in
the code. The open question is whether 9-of-12 falls is ordinary for this series
or is the de-dollarization it currently appears to be, and only a second year
answers it. Written down rather than marked PROVISIONAL and forgotten, which is
what happened to the gold tolerance for months before `D-0076`.

**The components are captured as an integrity check.** Table 5 decomposes the
headline into Treasury Bills and T-Bonds & Notes, and they must sum to it. They
reconcile to within 0.1 across all thirteen months, and `components_reconcile`
is computed on every run - if the source layout changes, the strip says the
figures are unverified in failure-red, louder than the signal itself, because
every number on it depends on the parse.

The bills share is also a signal in its own right: the duration posture of
official holders. It fell from 10.55% to 9.39%, which is lengthening, not the
shortening a defensive rotation would show.

**Exact-label matched, not prefix matched.** All three rows begin "Of Which:
Foreign Official". A prefix match would map the headline and both components to
whichever code was tried first - and the reconciliation check would then compare
a figure with itself and pass forever. A test pins each of the three to its own
value.

**Not additive with All Other, and a test says so.** Foreign Official spans
every holder; All Other spans the unnamed ones. They overlap. A first draft of
that test asserted `all_other + official > grand_total` as "arithmetic proof of
overlap" - which is **false**: 1,842.4 + 3,773.1 = 5,615.5, well under 9,248.1,
because the named private holders are large. Overlap is real but not provable
from three numbers. What is provable, and is the mistake a reader would actually
make, is that the two are **not a partition** of the total.

**System-level, like All Other**, rendered once above the table and never on a
row, under the same constraint and the same reasoning: a group's move attributed
to a named sovereign is `F-0097`.

**A display bug found on the way.** `(5475.0 / 1000).toFixed(2)` is `"5.47"`,
not `"5.48"` - 5.475 has no exact binary representation and lands just below the
midpoint. The private side read $5.47T while the payload said 5.475.
`trillions()` scales to an integer before rounding. Its first version claimed
"half away from zero" and used `Math.round`, which is half-**up**:
`Math.round(-547.5)` is `-547`. Every figure here is positive, so nothing on
screen was affected - but a helper whose comment and behaviour disagree is how
the next caller gets surprised, so the sign is handled explicitly.
