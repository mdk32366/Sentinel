/**
 * Where every number on these screens comes from.
 *
 * `F-0096`: this catalogue lived inside `AboutTab.jsx` as a local const, so
 * nothing could check it, and it drifted badly - three sources marked MANUAL
 * that had become automated, `mfhhis01.txt` named as the TIC file (which is the
 * `F-0088` defect verbatim), CDS and TreasuryDirect missing entirely, and CDS
 * listed under FUTURE while it was a live scoring dimension.
 *
 * It is the one surface whose entire purpose is to say where the numbers come
 * from, so a stale entry here is worse than a stale entry anywhere else. Moved
 * out so `dataSources.test.js` can hold it shut.
 */

// F-0096. This catalogue told the reader that three sources were MANUAL when
// they had become automated, named `mfhhis01.txt` as the TIC file - which is
// the F-0088 defect verbatim - credited gold reserves to a World Gold Council
// download when the upstream IMF feed is now read directly, omitted CDS and
// TreasuryDirect entirely, and listed CDS under FUTURE while it was a live
// scoring dimension a day old.
//
// It is the one surface whose entire purpose is to tell the reader where the
// numbers come from, so a stale entry here is worse than a stale entry
// anywhere else. `manual` is now false for every source, which removes the
// amber border from the whole list - the visual claim that nothing is
// hand-fed, which is true for the first time.
export const SOURCES = [
  {
    name: "FRED — Federal Reserve Economic Data",
    url: "https://fred.stlouisfed.org",
    update: "Daily (auto)",
    lag: "1 day",
    coverage: "US, plus 14 developed-market sovereign yields",
    metrics: ["30Y/10Y/5Y/2Y Treasury yields", "Fed Funds (DFF, daily)", "Real Yield (TIPS)", "WTI Crude Oil", "Dollar Index (DXY)", "CPI", "M2 Money Supply (WM2NS, weekly)", "Total reserves ex-gold by country"],
    notes: "Free API, key in FRED_API_KEY. Runs at 02:00 UTC and again on every app start. Writes are upserts, so a concurrent run cannot duplicate rows (D-0060).",
    manual: false,
  },
  {
    name: "TIC — Treasury International Capital",
    url: "https://ticdata.treasury.gov/resource-center/data-chart-center/tic/Documents/slt_table5.html",
    update: "Monthly (auto)",
    lag: "77–106 days — rows are dated to the first of the data month and published ~2.5 months later",
    coverage: "20 reporting countries",
    metrics: ["Foreign holdings of US Treasury securities by country, in $B"],
    notes: "SLT Table 5, 'Major Foreign Holders of Treasury Securities'. NOT mfhhis01.txt: Treasury retired the standalone MFH release in March 2023 and folded the table into SLT, and mfhhis01.txt is the history file — still served, still rewritten by every release, and frozen at December 2025. This pipeline read it for nine months (F-0088). Runs on the 15th at 03:00 UTC.",
    manual: false,
  },
  {
    name: "IMF IRFCL — Gold Reserves",
    url: "https://api.imf.org/external/sdmx/2.1/data/IRFCL/.IRFCLDT1_IRFCL56V_FTO..M",
    update: "Monthly (auto)",
    lag: "~50–80 days after month-end",
    coverage: "83 countries from IMF, 98 on the tab including WGC backfill",
    metrics: ["Central bank gold in metric tonnes, converted from fine troy ounces"],
    notes: "International Reserves and Foreign Currency Liquidity, template line 56. This is the upstream of the World Gold Council table that used to be downloaded by hand — WGC's own files are named '..._IFS.xlsx' (D-0076). The WGC CSV is retained as backfill for the ~28 countries that do not file the monthly template. Runs on the 25th at 05:15 UTC. Implausible values are rejected rather than imported: Brazil's series rescales by 1000 mid-series and Angola's reads 18,441 tonnes (F-0093).",
    manual: false,
  },
  {
    name: "World Bank — Broad Money Growth",
    url: "https://api.worldbank.org/v2/country/all/indicator/FM.LBL.BMNY.ZG",
    update: "Annual data, checked monthly (auto)",
    lag: "558–923 days — annual, dated to 1 January of the data year and published ~18 months later",
    coverage: "47 requested, 22 with usable data",
    metrics: ["Annual % growth in broad money supply (M2/M3)"],
    notes: "Free API, no auth. Fetched over HTTP on the 14th at 05:30 UTC; the committed JSON is now only an offline fallback, and a run served from it reports 'partial' rather than success (F-0091). Thresholds: >15% elevated, >30% significant debasement, >50% crisis. A country whose newest figure is over 3 years old is shown but NOT scored — Canada's newest is 2008 (F-0092).",
    manual: false,
  },
  {
    name: "LBMA — Spot Gold Price",
    url: "https://prices.lbma.org.uk",
    update: "Daily (auto)",
    lag: "1 day",
    coverage: "Global",
    metrics: ["Gold spot price USD/troy oz, daily fix"],
    notes: "The LBMA fix directly, unauthenticated, at 02:30 UTC. Not FRED, which deleted every ICE Benchmark Administration series in 2022 (F-0043), and no longer the WGC CSV — the monthly mean of these fixes reproduces that history to 0.00% across every month compared, because both come from the same administrator (D-0041, F-0044).",
    manual: false,
  },
  {
    name: "World Government Bonds — Sovereign CDS",
    url: "http://www.worldgovernmentbonds.com/sovereign-cds/",
    update: "Daily (auto)",
    lag: "1 day",
    coverage: "21 of 31 configured sovereigns quote on a given day",
    metrics: ["5Y sovereign CDS spread in basis points", "3-month change", "implied default probability"],
    notes: "Scoring dimension 7 and the only forward-looking, market-priced input in the model. 5Y only — the board publishes no 10Y, so term structure stays blank (D-0062). Quotes over 10,000bps are refused: they are ISDA standard coupons, not running spreads, which is how Russia appeared at 13,775bps (F-0074). Runs at 03:00 UTC and on app start.",
    manual: false,
  },
  {
    name: "TreasuryDirect — Par Yield Curve",
    url: "https://home.treasury.gov/resource-center/data-chart-center/interest-rates",
    update: "Weekdays (auto)",
    lag: "same day",
    coverage: "US curve",
    metrics: ["Par yield curve, 1M through 30Y"],
    notes: "Runs at 21:00 UTC, after Treasury publishes and before FRED's 02:00 run, so the curve is current a business day earlier than FRED alone (D-0022). FRED overwrites with its revised value overnight; A-0001's contract test is what makes that safe.",
    manual: false,
  },
];

export const SIGNALS = [
  {
    name: "Sovereign Stress Score",
    tier: 1,
    color: "#E8C547",
    // F-0100. This described a formula that has never existed in this codebase:
      // 40/30/20 with an "acceleration" term the scorer has no concept of. The
      // real dimension 1 was 30/20 and is now the D-0084 rule below.
      formula: "Treasury (0–50): worst of a 3-month fall in the total position or a bill-book drawdown, size-weighted, + 4 pts per consecutive declining month (max 20). Gold (0–40), Monetary (0–35), Petrodollar (0–20), CDS (0–20). Raw maximum 165.",
    threshold: "Alert: score ≥ 25 OR 3+ consecutive declining months",
    interpretation: "A country reducing treasury holdings. Could be strategic repositioning or liquidity need. Watch for persistence.",
  },
  {
    name: "Cross-Asset Stress (1.5×)",
    tier: 2,
    color: "#E07B5A",
    formula: "Treasury stress score × 1.5 when country is ALSO reducing gold reserves",
    threshold: "Fires when selling_treasuries AND selling_gold simultaneously",
    interpretation: "Selling both assets = more than repositioning. Reduced optionality. Country is drawing down its strategic reserve base.",
  },
  {
    name: "Divergence Signal (2×)",
    tier: 3,
    color: "#FF4444",
    formula: "Cross-asset score × 2 when spot gold is rising (>2% over 3 months)",
    threshold: "Fires when cross-asset AND spot_gold_rising",
    interpretation: "Selling gold INTO a rising gold price. This is the forced seller signal. A country only does this if it desperately needs USD liquidity. Maximum distress indicator.",
  },
];

// F-0096. This list used to promise "CDS Spreads ... Requires Bloomberg or
// Markit data" and "Country M2 / Broad Money Growth". Both are live scoring
// dimensions — CDS is dimension 7, one day old, from a free public board, and
// broad money is dimension 3. A roadmap that lists shipped features as future
// work is a roadmap nobody can use to tell what the system does.
export const FUTURE = [
  { name: "Currency Exchange Rates", why: "USD/local depreciation would confirm the reserve-selling thesis independently. FRED carries some pairs; full coverage needs a forex API." },
  { name: "IMF Reserve Adequacy", why: "Reserves to short-term external debt. Below 1.0 a country is vulnerable. The IRFCL dataset already wired in for gold (D-0076) carries the reserve side, so this is now a query away rather than a new integration." },
  { name: "Per-country data-age checks beyond dimension 3", why: "Dimension 3 refuses to score a country whose newest figure is over 3 years old (F-0092). No other dimension has that check, and the source-level freshness verdict cannot see a country-level gap. A-0017." },
  { name: "Period-end dating", why: "Annual and monthly series are dated to the START of their period, which overstates every age by a period and forces wide staleness tolerances. Dating to period end would tighten the gold and TIC guards materially. A-0016." },
];
