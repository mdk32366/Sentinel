/**
 * The twelve cards on MARKETS.
 *
 * `tip` says what the series is and why it is on a sovereign-stress board.
 * `stressRole` says what it actually does in the model, and `scored` is the
 * checkable version of that claim: true means a scorer reads this code.
 *
 * Eight of the twelve are NOT scored, and their tooltips say so. That is the
 * point of writing the role down rather than letting a card's presence imply
 * a connection — `D-0016` had to rule explicitly that the 30Y is displayed
 * and not weighted, because having it on the board looked like a factor.
 *
 * `tests/test_markets_tooltips.py` reads this file and fails if a code marked
 * `scored: false` turns up in `stress_score_v2.py`, or if a code marked
 * `scored: true` is in neither scorer. The prose can go stale; the flag
 * cannot go stale quietly.
 */
export const METRICS = [
  {
    code: "DGS30",
    label: "30Y Treasury",
    color: "#D4B06A",
    unit: "%",
    scored: false,
    tip: "US 30-year Treasury constant-maturity yield, daily from FRED. The long end is where foreign selling shows up first: the Fed sets the short end, so a 30Y that rises while the Fed cuts is the bond market repricing duration risk rather than following policy.",
    stressRole: "Not scored. D-0016 ruled it ingest-and-display — it is here to be watched, not weighted.",
  },
  {
    code: "DGS10",
    label: "10Y Treasury",
    color: "#C8A96E",
    unit: "%",
    scored: true,
    tip: "US 10-year yield — the most load-bearing number on this board. It is the world's reference risk-free rate, and the price at which the US refinances the debt every other country is holding.",
    stressRole: "Scored twice: the long leg of the yield-curve factor (35-40% of the v2 score), and the benchmark every sovereign spread is measured against — a country more than 50bps over it earns up to 20 composite points.",
  },
  {
    code: "DGS7",
    label: "7Y Treasury",
    color: "#A3B19B",
    unit: "%",
    scored: false,
    tip: "US 7-year yield. Sits between the 5Y and the 10Y so the curve has a shape rather than four disconnected points, and an inversion between adjacent tenors is visible rather than inferred.",
    stressRole: "Not scored. Curve shape only.",
  },
  {
    code: "DGS5",
    label: "5Y Treasury",
    color: "#7EB8C9",
    unit: "%",
    scored: false,
    tip: "US 5-year yield — the belly of the curve, and close to the average maturity of the roughly $6T of US debt that rolls over each year. It is the rate that decides next year's interest bill.",
    stressRole: "Not scored here. It does its work on the COUNTRY tab's fiscal breaking-point calculator (A-0012).",
  },
  {
    code: "DGS2",
    label: "2Y Treasury",
    color: "#9B8EC4",
    unit: "%",
    scored: true,
    tip: "US 2-year yield — the market's read on where policy goes over the next two years. Against the 10Y it gives the curve slope, which is the oldest recession signal there is.",
    stressRole: "Scored: the short leg of DGS10 - DGS2. Below zero is an inversion; at -1.00pp the yield-curve factor pins at maximum stress.",
  },
  {
    code: "FEDFUNDS",
    label: "Fed Funds",
    color: "#5DB87A",
    unit: "%",
    scored: false,
    tip: "FRED's FEDFUNDS: the effective federal funds rate as a MONTHLY AVERAGE, dated to the first of the month and published in the first week of the next one. It is the line between what the Fed controls and what the bond market controls — but it is not a live rate, and it will always read older than the daily yields beside it. A-0013.",
    stressRole: "Not scored. The stress model reads market yields, not policy rates.",
  },
  {
    code: "DFII10",
    label: "Real Yield",
    color: "#E8C547",
    unit: "%",
    scored: false,
    tip: "10-year TIPS yield: the inflation-protected return on holding Treasuries. When it is negative, a reserve manager is paying for the privilege of holding dollars — which is the mechanism behind rotating reserves into gold.",
    stressRole: "Not scored. It is the reason behind reserve shifts the model does score, rather than a factor itself.",
  },
  {
    code: "DCOILWTICO",
    label: "WTI Crude Oil",
    color: "#E07B5A",
    unit: "$/bbl",
    scored: true,
    tip: "West Texas Intermediate, daily. Oil exporters fund their Treasury purchases out of oil revenue, so a sustained fall means fewer petrodollars recycled into US debt — and forced selling when reserves have to cover the gap instead.",
    stressRole: "Scored twice: 30-day volatility drives the commodity factor (20-25% of the v2 score; 1% daily sigma = 0, 5%+ = 100), and it is the petrodollar factor's fallback when Brent is unavailable.",
  },
  {
    code: "DTWEXBGS",
    label: "Dollar Index",
    color: "#7EC4A0",
    unit: "",
    scored: false,
    tip: "Trade-weighted broad dollar index. A rising dollar tightens every foreign borrower funded in USD and is what forces reserve sales — the selling this application counts, country by country, in the TIC data.",
    stressRole: "Not scored directly. The selling it causes is what the Treasury factor measures.",
  },
  {
    code: "CPIAUCSL",
    label: "CPI",
    color: "#C47EB8",
    unit: "",
    scored: false,
    tip: "US headline CPI, monthly, as an index level rather than a rate — the COUNTRY tab carries the year-on-year figure. Released mid-month for the month before, so it runs a month or more behind the daily cards. Inflation erodes the real value of the Treasuries foreign central banks hold, and with it the case for holding them.",
    stressRole: "Not scored. This is the debasement half of the thesis, not a stress factor.",
  },
  {
    code: "M2SL",
    label: "M2 Money",
    color: "#6A8FC4",
    unit: "B$",
    scored: false,
    tip: "US broad money supply, monthly, in billions. The 2020-22 surge peaked near +27% year-on-year and CPI followed it to 9.1%. It is the supply side of dollar debasement, and the reason reserve managers ask whether dollar reserves are worth holding at all.",
    stressRole: "Not scored. Context for why a country might diversify, not evidence that it is.",
  },
  {
    code: "GOLD_SPOT_USD",
    label: "Gold Spot",
    color: "#DAA520",
    unit: "$/oz",
    scored: false,
    tip: "LBMA daily gold fix, USD per troy ounce. Gold is the alternative reserve asset: when a central bank sells Treasuries and buys gold, this is the price it pays. Live daily since D-0041 — D-0053 put it on this board as the twelfth card.",
    stressRole: "Context, not a factor. The composite carries its 3-month trend to confirm a pattern, but the SCORED gold signal is reserve tonnage, not price.",
  },
];

export const RANGES = [
  { label: "6M",  days: 180 },
  { label: "1Y",  days: 365 },
  { label: "2Y",  days: 730 },
  { label: "5Y",  days: 1825 },
];

export const TABS = ["MARKETS", "HOLDINGS", "CROSS-ASSET", "GOLD", "COMPOSITE", "CDS", "COUNTRY", "ADMIN", "ABOUT"];

// ── Shared UI ─────────────────────────────────────────────────────────────────

export const SOVEREIGN_YIELD_CODES = {
  JPN: "IRLTLT01JPM156N", DEU: "IRLTLT01DEM156N", ITA: "IRLTLT01ITM156N",
  FRA: "IRLTLT01FRM156N", ESP: "IRLTLT01ESM156N", GBR: "IRLTLT01GBM156N",
  AUS: "IRLTLT01AUM156N", CAN: "IRLTLT01CAM156N",
  NLD: "IRLTLT01NLM156N", NOR: "IRLTLT01NOM156N", SWE: "IRLTLT01SEM156N",
  CHE: "IRLTLT01CHM156N", BEL: "IRLTLT01BEM156N", KOR: "IRLTLT01KRM156N",
};


// Map ISO -> FRED total reserves ex-gold series code

export const TRESEG_CODES = {
  CHN: "TRESEGCNM052N",
  JPN: "TRESEGJPM052N",
  RUS: "TRESEGRUM052N",
  IND: "TRESEGINM052N",
  TUR: "TRESEGTRM052N",
  DEU: "TRESEGDEM052N",
  FRA: "TRESEGFRM052N",
  GBR: "TRESEGGBM052N",
  SAU: "TRESEGSAM052N",
  BRA: "TRESEGBRM052N",
  USA: "TRESEGUSM052N",
  IDN: "TRESEGIDM052N",
};
