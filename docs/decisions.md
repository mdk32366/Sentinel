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
