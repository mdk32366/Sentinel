export const METRICS = [
  { code: "DGS30",      label: "30Y Treasury",  color: "#D4B06A", unit: "%" },
  { code: "DGS10",      label: "10Y Treasury",  color: "#C8A96E", unit: "%" },
  { code: "DGS7",       label: "7Y Treasury",   color: "#A3B19B", unit: "%" },
  { code: "DGS5",       label: "5Y Treasury",   color: "#7EB8C9", unit: "%" },
  { code: "DGS2",       label: "2Y Treasury",   color: "#9B8EC4", unit: "%" },
  { code: "FEDFUNDS",   label: "Fed Funds",     color: "#5DB87A", unit: "%" },
  { code: "DFII10",     label: "Real Yield",    color: "#E8C547", unit: "%" },
  { code: "DCOILWTICO", label: "WTI Crude Oil", color: "#E07B5A", unit: "$/bbl" },
  { code: "DTWEXBGS",   label: "Dollar Index",  color: "#7EC4A0", unit: "" },
  { code: "CPIAUCSL",   label: "CPI",           color: "#C47EB8", unit: "" },
  { code: "M2SL",       label: "M2 Money",      color: "#6A8FC4", unit: "B$" },
  // D-0053. Twelfth ticker, filling the slot D-0037 left on the second row.
  // GOLD_SPOT_USD has been a live daily series since D-0041; before that it
  // was a manual monthly CSV and had no business on a markets ticker.
  //
  // On the chart it is opt-in and roughly 800x the scale of a yield, so
  // plotting both at once flattens the yields - that is what the % CHANGE
  // toggle is for.
  { code: "GOLD_SPOT_USD", label: "Gold Spot",  color: "#DAA520", unit: "$/oz" },
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
