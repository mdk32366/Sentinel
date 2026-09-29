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
