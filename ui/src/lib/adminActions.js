/**
 * Every scheduled job and every manual trigger the system actually has.
 *
 * `F-0098`: the ADMIN tab listed **four** actions against eleven scheduled jobs
 * and ten POST triggers. It described TIC as "45 countries" (Table 5 names
 * twenty), put Gold Reserves under a heading of "Manual (CSV import)" with
 * instructions to re-download quarterly from gold.org months after `D-0076`
 * automated it from IMF IRFCL, and omitted CDS, Treasury Direct, Gold Price,
 * Gold Reserve Changes, Broad Money, IMF Gold, the composite snapshot and the
 * freshness watchdog entirely.
 *
 * Like the ABOUT catalogue (`F-0096`) it lived inside the component as a local
 * const, so nothing could check it. Moved here, and
 * `tests/test_admin_surface.py` now asserts from the Python side that every
 * POST route and every registered job id appears - a JS test cannot read
 * `api/routes.py`, and the drift is exactly between those two files.
 */

/** Jobs registered by `pipelines/scheduler.py`, with their real cron. */
export const SCHEDULED_JOBS = [
  { id: "fred_fetch", name: "FRED Data Fetch", schedule: "Daily 02:00 UTC",
    pipeline: "FRED",
    desc: "Yields, Fed Funds (DFF daily), TIPS, WTI, DXY, CPI, M2 (WM2NS weekly), sovereign yields, reserves ex-gold. Also runs on every app start; writes are upserts so a concurrent run cannot duplicate rows (D-0060)." },
  { id: "gold_price", name: "Gold Spot Price (LBMA)", schedule: "Daily 02:30 UTC",
    pipeline: "Gold_Spot_Price",
    desc: "The LBMA daily fix, unauthenticated. Not FRED, which deleted every ICE Benchmark Administration series in 2022 (F-0043)." },
  { id: "cds_multi_tenor_job", name: "Sovereign CDS", schedule: "Daily 03:00 UTC",
    pipeline: "CDS_MultiTenor",
    desc: "5Y spreads from the World Government Bonds board, 31 configured sovereigns. Quotes over 10,000bps are refused as ISDA coupons rather than running spreads (F-0074). Also runs on app start." },
  { id: "stress_score", name: "Macro Stress Score", schedule: "Daily 04:30 UTC",
    pipeline: "Stress_Score",
    desc: "The US-level 4-factor index. A different scorer from the composite (F-0047); its tab was retired under D-0051 but the job and GET /api/stress-score remain." },
  { id: "composite_snapshot", name: "Composite Stress Snapshot", schedule: "Daily 04:45 UTC",
    pipeline: "Composite_Snapshot",
    desc: "Scores every country once and stores the result, so a tab click does not recompute ~230 queries (D-0042). GET /api/stress/composite serves what this writes." },
  { id: "freshness_check", name: "Data Freshness Watchdog", schedule: "Daily 05:00 UTC",
    pipeline: "Freshness",
    desc: "Per-source verdict against each source's own release cadence. What the confidence strip on every tab reads (D-0074)." },
  { id: "treasury_direct", name: "Treasury Direct Par Yield Curve", schedule: "Weekdays 21:00 UTC",
    pipeline: "TreasuryDirect",
    desc: "After Treasury publishes and before FRED's 02:00 run, so the curve is current a business day earlier than FRED alone (D-0022)." },
  { id: "gold_fetch", name: "Gold Reserves (WGC backfill)", schedule: "1st of month, 04:00 UTC",
    pipeline: "Gold_Reserves",
    desc: "The World Gold Council CSV, retained as backfill for the ~28 countries that do not file the monthly IMF template. No longer the primary source (D-0076)." },
  { id: "money_supply", name: "Broad Money Growth (World Bank)", schedule: "14th of month, 05:30 UTC",
    pipeline: "Broad_Money_Growth",
    desc: "World Bank FM.LBL.BMNY.ZG over HTTP. Annual data checked monthly because the Bank revises between releases. Had no job at all until F-0091." },
  { id: "treasury_fetch", name: "TIC Holdings", schedule: "15th of month, 03:00 UTC",
    pipeline: "TIC_Holdings",
    desc: "SLT Table 5, 'Major Foreign Holders of Treasury Securities' — twenty named countries plus an 'All Other' row. NOT mfhhis01.txt, which is the frozen history file this read for nine months (F-0088)." },
  { id: "tic_table3", name: "TIC Holdings, All Countries (Table 3)", schedule: "15th of month, 03:30 UTC",
    pipeline: "TIC_Table3",
    desc: "SLT Table 3 — per-country Treasury holdings for all 76 reporters, against Table 5's twenty (D-0081). Also carries net sales and valuation change, so selling can be told from repricing. Refuses to write unless it first reproduces Table 5 for the named twenty." },
  { id: "imf_gold", name: "Gold Reserves (IMF IRFCL)", schedule: "25th of month, 05:15 UTC",
    pipeline: "Gold_Reserves_IMF",
    desc: "IMF IRFCL line 56, fine troy ounces converted to tonnes, 83 countries. The upstream of the WGC table (D-0076). Implausible values are rejected, not imported (F-0093)." },
];

/** Manual triggers. Every POST route the API exposes, plus the read-only report. */
export const MANUAL_TRIGGERS = [
  { name: "FRED Data", endpoint: "/fetch/fred", method: "POST",
    desc: "Force the FRED pull now." },
  { name: "TIC Holdings", endpoint: "/fetch/treasury-holdings", method: "POST",
    desc: "Force the SLT Table 5 import. Refuses a file older than 140 days rather than re-importing a frozen year (D-0045)." },
  { name: "TIC Holdings, All Countries", endpoint: "/fetch/tic-table3", method: "POST",
    desc: "Force the Table 3 import. Validates against Table 5 before writing." },
  { name: "Gold Reserves (IMF)", endpoint: "/fetch/gold-reserves-imf", method: "POST",
    desc: "Force the IMF IRFCL monthly import. This is the primary gold source." },
  { name: "Gold Reserves (WGC backfill)", endpoint: "/fetch/gold-reserves", method: "POST",
    desc: "Import the WGC CSV from data/gold_reserves.csv. Backfill only — for countries IRFCL does not carry." },
  { name: "Gold Reserve Changes", endpoint: "/fetch/gold-reserve-changes", method: "POST",
    desc: "The WGC quarterly changes table. A separate metric from reserve levels." },
  { name: "Gold Spot Price", endpoint: "/fetch/gold-price", method: "POST",
    desc: "Force the LBMA fix pull." },
  { name: "Broad Money Growth", endpoint: "/fetch/money-supply", method: "POST",
    desc: "Force the World Bank pull. Reports origin=api or origin=cache, and cache counts as partial rather than success (F-0091)." },
  { name: "Sovereign CDS", endpoint: "/cds/fetch", method: "POST",
    desc: "Force the CDS scrape." },
  { name: "Composite Snapshot", endpoint: "/snapshot/composite", method: "POST",
    desc: "Recompute and STORE the composite. Needed after any manual data fetch, or the score lags the data it reads until 04:45 (F-0090)." },
  { name: "Country Analyst Brief", endpoint: "/analyze/country", method: "POST",
    desc: "Generate the LLM brief for one country. Provider selectable; Grok by default." },
  { name: "Macro Stress Score", endpoint: "/stress-score", method: "GET",
    desc: "Recompute the US-level index. A GET because it does not persist." },
  { name: "Per-country Data Age", endpoint: "/diagnostics/data-age", method: "GET",
    desc: "Distribution of per-country data age for every monitored source (A-0017). Read-only; it computes no verdict." },
];
