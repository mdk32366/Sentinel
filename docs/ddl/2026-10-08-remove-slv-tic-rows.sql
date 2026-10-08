-- F-0114: remove El Salvador's TIC holdings, which no current source supports.
--
-- Owner authorised 2026-10-08 ("Delete the SLV rows").
--
-- APPLIED to production 2026-10-08.
--
--     precondition: 12 rows, newest 2025-12-01, max 93.8 - passed
--     timeseries before=93707 deleted=12 after=93695
--     SLV TIC rows remaining: 0
--
-- BACKUP of the deleted rows (date, $bn, id), all created 2026-06-24 14:08:
--   2025-01-01     1.1  (id 15647)
--   2025-02-01     1.1  (id 15646)
--   2025-03-01    85.0  (id 15645)
--   2025-04-01    86.3  (id 15644)
--   2025-05-01    88.4  (id 15643)
--   2025-06-01    89.5  (id 15642)
--   2025-07-01    82.0  (id 15641)
--   2025-08-01    82.2  (id 15640)
--   2025-09-01    88.6  (id 15639)
--   2025-10-01    91.6  (id 15638)
--   2025-11-01    92.2  (id 15637)
--   2025-12-01    93.8  (id 15636)
--
-- WHAT GOES, AND WHY
--   The 12 TIC_UST_HOLDINGS rows for SLV, 2025-01-01 .. 2025-12-01:
--   $1.1bn, $1.1bn, then $85.0bn .. $93.8bn. All 12 were written in the
--   6,680-row import of 2026-06-24 from Treasury's frozen history file
--   mfhhis01.txt (F-0088), where a row labelled "El Salvador" carries those
--   values. Treasury's current 76-country Table 3 has no El Salvador row,
--   and no other country or aggregate carries the series. The importer read
--   the label correctly; the label is wrong at source.
--
-- WHAT STAYS
--   SLV's gold rows (GOLD_RESERVES, GOLD_RESERVE_CHANGES) are IMF/WGC data
--   and are not in question. The SLV country row stays; with no TIC rows its
--   state becomes no_data, which is the truth: Table 3 does not list it.
--
-- WHAT COULD BRING THEM BACK
--   Only a manual backfill from mfhhis01.txt. Nothing scheduled or routed
--   reads it: TIC_MFH_HISTORY_URL in treasury_holdings.py is a name only, and
--   pipelines/tic_fetcher.py is imported nowhere. Do not backfill SLV from it.
--
-- Run as one transaction. The precondition refuses to delete unless the set
-- is exactly the 12 rows described above.

BEGIN;

DO $$
DECLARE n int; newest date; biggest numeric;
BEGIN
  SELECT count(*), max(t.date)::date, max(t.value)
    INTO n, newest, biggest
    FROM timeseries t
    JOIN metrics m ON m.id = t.metric_id
    JOIN countries c ON c.id = t.country_id
   WHERE m.code = 'TIC_UST_HOLDINGS' AND c.iso_code = 'SLV';
  IF n <> 12 OR newest <> DATE '2025-12-01' OR biggest <> 93.8 THEN
    RAISE EXCEPTION 'precondition failed: n=% newest=% max=%', n, newest, biggest;
  END IF;
END $$;

DELETE FROM timeseries t
 USING metrics m, countries c
 WHERE t.metric_id = m.id AND t.country_id = c.id
   AND m.code = 'TIC_UST_HOLDINGS' AND c.iso_code = 'SLV';

COMMIT;
