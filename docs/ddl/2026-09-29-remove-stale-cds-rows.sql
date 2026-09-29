-- F-0074: remove the CDS rows a previous scraper wrote and the current one
-- would never produce.
--
-- APPLIED to production 2026-09-29, owner authorised.
--
--     newest row in scope: 2026-07-16 (75d old)
--     before=66400 deleted=125 after=66275
--     10Y rows remaining: 0
--     SAUDI 5Y rows remaining: 0
--     live 5Y series still present: 20
--
-- WHAT WENT, AND WHY IT WAS SAFE
--   * Every *_CDS_10Y row - 118 of them, two distinct values across the whole
--     set: 500.0 (the ISDA standard running coupon) and one 77.2. Germany,
--     Japan, Switzerland and the United States all at 500bps. The current
--     fetcher does not write 10Y at all; its docstring says WGB's 5Y board
--     has no paired 10Y.
--   * SAUDI_ARABIA_CDS_5Y - 7 rows, all 500.0, from the same window. The
--     current fetcher reports Saudi Arabia as absent from the board on every
--     run, which is why it never overwrote them.
--
--   Both sets froze at 2026-07-16. The precondition asserted the newest row
--   in scope was older than MAX_CDS_AGE_DAYS before deleting, so nothing
--   current could be caught by the pattern.
--
-- WHAT DELIBERATELY STAYED
--   RUSSIA_CDS_5Y. Its 13,775.2 is refused as implausible rather than stale,
--   and it is the CURRENT output of a running pipeline - the CDS fetch writes
--   it again on every run. Deleting rows a live pipeline recreates daily is
--   theatre. It is excluded at read by admit_cds_quote, the country panel
--   states the reason, and the durable fix is either a source change or a
--   frozen-series detector (see below).
--
-- NOT DONE: a frozen-series detector
--   Magnitude is a blunt instrument. The most diagnostic property of the
--   Russian series was not that 13,775 is large but that it did not MOVE:
--   one value, to one decimal, for 23 consecutive observations including
--   weekends. A live price moves. A check for "this series has not changed in
--   N observations" would catch a stuck feed at any magnitude, including a
--   plausible one - which is the case magnitude cannot see.

DELETE FROM timeseries t
USING metrics m
WHERE m.id = t.metric_id
  AND (m.code LIKE '%_CDS_10Y' OR m.code = 'SAUDI_ARABIA_CDS_5Y');
-- expected: 125 rows deleted, 66400 -> 66275

-- Verify:
--   SELECT COUNT(*) FROM timeseries t JOIN metrics m ON m.id=t.metric_id
--   WHERE m.code LIKE '%_CDS_10Y';   -- must be 0
