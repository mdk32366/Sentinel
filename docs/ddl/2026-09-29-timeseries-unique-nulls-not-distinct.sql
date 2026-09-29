-- F-0073: the unique index on timeseries does not constrain the rows that
-- matter, because every macro series has country_id IS NULL and Postgres
-- treats NULLs as distinct in a unique index.
--
--   CREATE UNIQUE INDEX ix_metric_country_date
--     ON public.timeseries USING btree (metric_id, country_id, date)
--
-- That index exists, looks correct, and has never rejected a single duplicate
-- for a country-less series. 67,332 rows carried 1,190 exact duplicates when
-- this was written.
--
-- Postgres 16 (production is 16.14) supports NULLS NOT DISTINCT, which makes
-- the index mean what everyone reading it already assumed it meant.
--
-- RUN THE TWO STATEMENTS IN ORDER. The index cannot be created while
-- duplicates remain, which is the point.
--
-- ════════════════════════════════════════════════════════════════════════════
-- STATUS
--   Statement 1 (DELETE) — APPLIED to production 2026-09-29, owner authorised.
--       groups with more than one distinct value: 0
--       before=67332 deleted=1190 after=66142
--       duplicate groups remaining: 0
--
--   Statement 2 (the index) — APPLIED to production 2026-09-29, owner
--       authorised. Preconditions checked first: 0 pipeline runs in flight,
--       0 duplicate groups. DROP and CREATE ran in one transaction, so there
--       was no window without a unique index.
--
--         CREATE UNIQUE INDEX ix_metric_country_date ON public.timeseries
--           USING btree (metric_id, country_id, date) NULLS NOT DISTINCT
--
--       Verified to BIND, rather than assumed — a duplicate insert attempted
--       in a rolled-back transaction:
--
--         RESULT: rejected -> IntegrityError
--                 duplicate key value violates unique constraint
--                 "ix_metric_country_date"
--         COUNTRY-SCOPED: still rejected -> IntegrityError
--         rows after rollbacks: 66400
--
--       database/models.py carries postgresql_nulls_not_distinct=True so a
--       fresh database gets the same semantics; tests/test_timeseries_
--       uniqueness.py asserts the emitted DDL. SQLite shares Postgres' NULL
--       semantics and ignores the kwarg, so the in-memory test databases do
--       NOT enforce this.
--
--   Re-running statement 1 is safe and idempotent: with no duplicates present
--   its subquery returns no rows and it deletes nothing.
-- ════════════════════════════════════════════════════════════════════════════

-- ── 1. Remove the duplicates ────────────────────────────────────────────────
-- Every duplicate group was verified to hold a SINGLE distinct value before
-- this was written, so this discards no information:
--
--   SELECT COUNT(*) FROM (
--     SELECT metric_id, date, country_id FROM timeseries
--     GROUP BY metric_id, date, country_id
--     HAVING COUNT(*) > 1 AND COUNT(DISTINCT value) > 1) x;
--   -- 0
--
-- Re-run that check before deleting. If it is not 0, STOP: the groups
-- disagree, one of the values is a correction, and keeping MIN(id) would
-- discard it.
--
-- Everything here is re-fetchable from FRED, so the worst case is a re-run of
-- the pipeline rather than lost data.

DELETE FROM timeseries t
USING (
    SELECT MIN(id) AS keep, metric_id, country_id, date
    FROM timeseries
    GROUP BY metric_id, country_id, date
    HAVING COUNT(*) > 1
) d
WHERE t.metric_id = d.metric_id
  AND t.date = d.date
  AND t.country_id IS NOT DISTINCT FROM d.country_id
  AND t.id <> d.keep;
-- expected: 1190 rows deleted, 67332 -> 66142

-- ── 2. Make the constraint bind ─────────────────────────────────────────────
-- IS NOT DISTINCT FROM above and NULLS NOT DISTINCT here are the same idea:
-- two NULL country_ids are the same country (none), not two different ones.

DROP INDEX IF EXISTS ix_metric_country_date;

CREATE UNIQUE INDEX ix_metric_country_date
    ON public.timeseries USING btree (metric_id, country_id, date)
    NULLS NOT DISTINCT;

-- ── Verify ──────────────────────────────────────────────────────────────────
--   SELECT COUNT(*) FROM (
--     SELECT 1 FROM timeseries GROUP BY metric_id, country_id, date
--     HAVING COUNT(*) > 1) x;
--   -- must be 0
--
-- And prove the guard bites, in a transaction you roll back:
--
--   BEGIN;
--   INSERT INTO timeseries (metric_id, country_id, date, value)
--   SELECT metric_id, country_id, date, value FROM timeseries LIMIT 1;
--   -- must raise: duplicate key value violates unique constraint
--   ROLLBACK;
--
-- ── Afterwards ──────────────────────────────────────────────────────────────
-- pipelines/fred_fetcher.py inserts with check-then-insert and no ON CONFLICT,
-- which is a race by construction. With this index it becomes a loud
-- IntegrityError caught by the per-metric handler and reported as `partial`,
-- instead of silent duplication. Converting it to an upsert is the remaining
-- half and is not done here.
