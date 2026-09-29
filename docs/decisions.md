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

### D-0026 — [OWNER TO RULE] The go-private observable

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

**Partial ruling 2026-09-28: not ready to go private.** The repository stays
public for now, which settles the *state*.

**What this does not settle.** Principle 10 asks for the **observable** that
will make "development is complete" true, recorded as a numbered decision, so
the stopping point is not argued about at the moment it matters. "Not ready
yet" is a position, not an observable, and this entry stays open until one is
named.

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

### D-0032 — [OWNER TO RULE] Alembic: initialize or remove

`alembic==1.12.1` is pinned and has never been initialized. Schema comes from
`create_all()`, which ignores changed columns silently.

**(a) Initialize.** Baseline against current schema, stamp as head, migrations
from here.
**(b) Remove and document.** Drop from requirements; `architecture.md` states
DDL is manual and names the procedure.

Pinning an unused migration tool is worse than either, because it reads as
having migrations. **Owner's ruling.**

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
