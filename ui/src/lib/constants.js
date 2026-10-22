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
    code: "DFF",
    label: "Fed Funds",
    color: "#5DB87A",
    unit: "%",
    scored: false,
    tip: "The effective federal funds rate, daily — what overnight money actually traded at, inside the target range the Fed sets. This is the line between what the Fed controls and what the bond market controls, which is the distinction the COUNTRY tab's scenario panel is built on. D-0057 moved this card off FRED's monthly average, which had it reading 3.63% while the rate was 3.88%.",
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
    code: "WM2NS",
    label: "M2 Money",
    color: "#6A8FC4",
    unit: "B$",
    scored: false,
    tip: "US broad money supply, weekly and not seasonally adjusted. The 2020-22 surge peaked near +27% year-on-year and CPI followed it to 9.1% — this is the supply side of dollar debasement, and the reason reserve managers ask whether dollar reserves are worth holding at all. The Fed publishes M2 once a month in the H.6 release, so the newest reading is always a few weeks back however it is sliced; the weekly series just puts that reading four weeks further forward than the monthly one. D-0058.",
    stressRole: "Not scored. Context for why a country might diversify, not evidence that it is.",
  },
  {
    code: "GOLD_SPOT_USD",
    label: "Gold Spot",
    color: "#DAA520",
    unit: "$/oz",
    scored: false,
    tip: "Gold spot, USD per troy ounce (gold-api.com daily snapshot; World Bank Pink Sheet monthly fallback, with attribution). Gold is the alternative reserve asset: when a central bank sells Treasuries and buys gold, this is the price it pays. Live daily since D-0041; source re-ruled under D-0094 after LBMA's Cloudflare block — D-0053 put it on this board as the twelfth card.",
    stressRole: "Context, not a factor. The composite carries its 3-month trend to confirm a pattern, but the SCORED gold signal is reserve tonnage, not price.",
  },
];

export const RANGES = [
  { label: "6M",  days: 180 },
  { label: "1Y",  days: 365 },
  { label: "2Y",  days: 730 },
  { label: "5Y",  days: 1825 },
];

// Sentinel D-0111: FOREIGN-BONDS sits straight after MARKETS, the surface it
// is modelled on (#/foreign-bonds).
export const TABS = ["MARKETS", "FOREIGN-BONDS", "HOLDINGS", "CROSS-ASSET", "GOLD", "COMPOSITE", "CDS", "AUCTIONS", "COUNTRY", "ADMIN", "ABOUT"];

/**
 * The MARKETS spread strip, moved verbatim out of App.jsx (Sentinel D-0111) so
 * MarketsTab can draw either tab's strip. null = no strip, exactly the old
 * `latest["DGS10"] != null && latest["DGS2"] != null` guard.
 */
export function US_SPREADS(latest) {
  if (latest["DGS10"] == null || latest["DGS2"] == null) return null;
  return [
    { label: "30Y–10Y", val: latest["DGS30"] != null ? latest["DGS30"] - latest["DGS10"] : null,
      tip: "30-year minus 10-year Treasury yield (DGS30 − DGS10), in percentage points. A widening gap is the market charging more to lend for the longest terms: the long end repricing duration risk." },
    { label: "10Y–2Y", val: latest["DGS10"] - latest["DGS2"], inverts: true,
      tip: "10-year minus 2-year Treasury yield (DGS10 − DGS2), the classic curve slope. Below zero the curve is inverted, the oldest recession signal there is, and is marked INVERTED." },
    { label: "10Y–5Y", val: latest["DGS5"] != null ? latest["DGS10"] - latest["DGS5"] : null,
      tip: "10-year minus 5-year Treasury yield (DGS10 − DGS5). The 5Y is close to the average maturity of the debt that rolls over each year, so this is the extra the market asks to lend past the rollover point." },
    { label: "5Y–2Y", val: latest["DGS5"] != null ? latest["DGS5"] - latest["DGS2"] : null,
      tip: "5-year minus 2-year Treasury yield (DGS5 − DGS2): the front of the curve, where expectations for Fed policy over the next few years show first." },
    { label: "10Y–FF", val: latest["DFF"] != null ? latest["DGS10"] - latest["DFF"] : null,
      tip: "10-year yield minus the effective fed funds rate (DGS10 − DFF): what the bond market sets against what the Fed sets. A long end rising while the Fed cuts widens this." },
  ].filter(s => s.val != null);
}

// ── Foreign Bonds (Sentinel D-0111, vault:D-0057) ────────────────────────────

/**
 * The twenty cells on FOREIGN-BONDS: DE / GB / JP / FR x 2 / 5 / 7 / 10 / 30Y.
 *
 * `kind` is what the number IS, and every tip says it:
 *   FIT  fitted-curve zero-coupon / spot yield at the exact maturity
 *        (Bundesbank Svensson, BoE GLC spot)
 *   CMT  constant-maturity yield (MOF Japan par yields; Banque de France TEC)
 *   MON  monthly average, not daily (OECD via FRED) - badged MONTHLY
 *
 * Sentinel D-0112 replaced D-0111 option A's four NO SOURCE cells: France is
 * the Banque de France TEC, daily. D-0112 amendment 1: TEC10 is the only FR
 * 10Y here; the monthly OECD France series is not shown, spread or requested
 * on this tab (it stays in FRED's fetch and composite D4).
 *
 * Every entry is `scored: false`. `tests/test_markets_tooltips.py` holds that
 * shut against both scorers, as it does for METRICS. The `FB_` codes are in
 * no ticker and no scorer; since Sentinel D-0113 the DEU/GBR/JPN/FRA country
 * cards display them (display only, `countryBond` below).
 */
const FB_COUNTRY = {
  DE: { kind: "FIT", colors: ["#8A7448", "#A38A57", "#B89A60", "#C8A96E", "#E0C690"] },
  GB: { kind: "FIT", colors: ["#4F7A86", "#5F909E", "#6FA4B3", "#7EB8C9", "#A5D2DF"] },
  JP: { kind: "CMT", colors: ["#94503B", "#B0604A", "#C86D52", "#E07B5A", "#F0A487"] },
  FR: { kind: "CMT", colors: ["#6E6496", "#8277AD", "#9B8EC4", "#B3A8D6", "#CCC4E6"] },
};
const FB_TENORS = [2, 5, 7, 10, 30];
const FB_NOT_SCORED =
  "Not scored. Display only (Sentinel D-0111): composite dimension 4 already scores this country's monthly OECD 10Y, and a daily copy would count the same signal twice on a different clock.";
function fbTip(cc, t) {
  const pad = String(t).padStart(2, "0");
  if (cc === "DE") {
    return `Germany ${t}-year Bund yield. FIT: Bundesbank Svensson zero-coupon yield at exactly ${t} years, fitted to listed Federal securities, business-daily. Series BBSIS/D.I.ZST.ZI.EUR.S1311.B.A604.R${pad}XX.R.A.A._Z._Z.A.`;
  }
  if (cc === "GB") {
    return `UK ${t}-year gilt yield. FIT: Bank of England GLC nominal spot curve at ${t}.0 years (sheet "4. spot curve"), business-daily, published one business day later. A fitted spot rate, not a par or benchmark yield.`;
  }
  if (cc === "FR") {
    return `France ${t}-year OAT yield. CMT: Banque de France TEC ${t} (taux de l'échéance constante), the yield of a notional OAT of exactly ${t} years interpolated from benchmark OATs, business-daily. Series FM.D.FR.EUR.FR2.BB.FRMOYTEC${t}.HSTA (Webstat).`;
  }
  return `Japan ${t}-year JGB yield. CMT: Ministry of Finance constant-maturity par yield interpolated from benchmark JGBs, column ${t}年 of jgbcm.csv, business-daily. A par yield, so not the same construction as the DE and UK fitted spot rates.`;
}

export const FOREIGN_BOND_METRICS = [
  ...["DE", "GB", "JP", "FR"].flatMap((cc) => FB_TENORS.map((t, i) => ({
    code: `FB_${cc}_${String(t).padStart(2, "0")}Y`,
    key: `FB_${cc}_${String(t).padStart(2, "0")}Y`,
    label: `${cc} ${t}Y`,
    color: FB_COUNTRY[cc].colors[i],
    unit: "%",
    kind: FB_COUNTRY[cc].kind,
    scored: false,
    tip: fbTip(cc, t),
    stressRole: FB_NOT_SCORED,
  }))),
];

/** The cells to draw: the 20 daily cells, nothing swapped in (D-0112 amendment 1). */
export function foreignBondCells() {
  return FOREIGN_BOND_METRICS;
}

/** "Source: Banque de France, updated <YYYY-MM-DD>" from the newest French daily row (D-0112). */
export function bdfAttribution(dates) {
  const newest = FOREIGN_BOND_METRICS
    .filter((m) => m.code.startsWith("FB_FR_"))
    .map((m) => dates?.[m.code])
    .filter(Boolean)
    .sort()
    .at(-1);
  return newest
    ? `Source: Banque de France, updated ${String(newest).slice(0, 10)}`
    : "Source: Banque de France, not yet available";
}

/** Codes FOREIGN-BONDS reads: its own cells plus the legs of its spreads. */
export const FOREIGN_BOND_CODES = [
  ...FOREIGN_BOND_METRICS.map((m) => m.code),
  "DGS10",
];

/** Which watchdog source vouches for a code (spec §5 / §7.7). */
export function foreignBondSourceKey(code) {
  if (code.startsWith("FB_DE_")) return "foreign_bonds_de";
  if (code.startsWith("FB_GB_")) return "foreign_bonds_gb";
  if (code.startsWith("FB_JP_")) return "foreign_bonds_jp";
  if (code.startsWith("FB_FR_")) return "foreign_bonds_fr";
  if (code.startsWith("DGS")) return "treasury_yields";
  return null;
}

const pp = (a, b) => (a != null && b != null ? a - b : null);

/**
 * The FOREIGN-BONDS spread strip, in pp. `fresh(code)` is false when the
 * watchdog calls that leg's source stale or worse; such a spread stays in
 * place and shows "—" rather than a number against a leg that has stopped
 * moving (Sentinel D-0113 follow-up; it used to be hidden). A spread with a
 * fresh but absent leg (no data at all) is still left out.
 */
export function foreignBondSpreads(latest, fresh = () => true, series = {}) {
  const settle = (s, a, b) => {
    if (!fresh(a) || !fresh(b)) return { ...s, val: null, display: "—" };
    return { ...s, val: pp(latest[a], latest[b]) };
  };
  const lag = " The two legs can be dated a business day apart (the BoE curve is published a day late).";
  return [
    settle({ label: "Bund–UST 10Y",
      tip: "German 10Y (Bundesbank fitted) minus US 10Y Treasury (DGS10), in percentage points." + lag }, "FB_DE_10Y", "DGS10"),
    settle({ label: "Gilt–UST 10Y",
      tip: "UK 10Y (BoE fitted spot) minus US 10Y Treasury (DGS10), in percentage points." + lag }, "FB_GB_10Y", "DGS10"),
    settle({ label: "JGB–UST 10Y",
      tip: "Japan 10Y (MOF constant-maturity) minus US 10Y Treasury (DGS10), in percentage points." + lag }, "FB_JP_10Y", "DGS10"),
    settle({ label: "Gilt–Bund 10Y",
      tip: "UK 10Y minus German 10Y, both fitted curves, in percentage points." + lag }, "FB_GB_10Y", "FB_DE_10Y"),
    settle({ label: "Gilt–Bund 2Y",
      tip: "UK 2Y minus German 2Y, both fitted curves, in percentage points." + lag }, "FB_GB_02Y", "FB_DE_02Y"),
    settle({ label: "DE 10Y–2Y", inverts: true,
      tip: "German curve slope: 10Y minus 2Y (Bundesbank fitted). Below zero the curve is inverted." }, "FB_DE_10Y", "FB_DE_02Y"),
    settle({ label: "GB 10Y–2Y", inverts: true,
      tip: "UK curve slope: 10Y minus 2Y (BoE fitted spot). Below zero the curve is inverted." }, "FB_GB_10Y", "FB_GB_02Y"),
    settle({ label: "JP 30Y–10Y",
      tip: "Japan long end: 30Y minus 10Y (MOF constant-maturity), where the super-long JGB repricing shows." }, "FB_JP_30Y", "FB_JP_10Y"),
  ].filter((s) => s.val != null || s.display === "—").concat([oatBundCurrent(fresh, series)]);
}

export const OAT_BUND_LABEL = "OAT–Bund 10Y (daily, BdF TEC − Bundesbank)";

/**
 * Sentinel D-0112 amendment 2: the daily OAT–Bund 10Y, FB_FR_10Y minus
 * FB_DE_10Y in basis points, on the dates where BOTH legs have an
 * observation. Never forward-filled: a date missing either leg is a gap.
 * `fr` / `de` are [{date, value}] as `seriesByCode` returns them.
 */
export function oatBundDailySpread(fr = [], de = []) {
  const deByDate = new Map((de ?? []).filter((p) => p.value != null).map((p) => [p.date, p.value]));
  return (fr ?? [])
    .filter((p) => p.value != null && deByDate.has(p.date))
    .map((p) => ({ date: p.date, bp: (p.value - deByDate.get(p.date)) * 100 }))
    .sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0));
}

/**
 * The strip entry for the daily OAT–Bund, in pp. Always present on the tab: when
 * either leg is past the FB freshness rule (`fresh`), or no shared date
 * exists, it reads "—" instead of quoting a number.
 */
function oatBundCurrent(fresh, series) {
  const tip = "French 10Y (Banque de France TEC, constant-maturity) minus German 10Y (Bundesbank fitted), daily, in percentage points like the rest of the strip, only on dates both legs publish - a missing leg is a gap, never filled. Two constructions: a constant-maturity yield against a fitted zero-coupon one. Shows — when either leg is stale (Sentinel D-0112 amendment 2).";
  const dash = { label: OAT_BUND_LABEL, val: null, display: "—", tip: tip };
  if (!fresh("FB_FR_10Y") || !fresh("FB_DE_10Y")) return dash;
  const last = oatBundDailySpread(series.FB_FR_10Y, series.FB_DE_10Y).at(-1);
  // pp, like the rest of the strip (Sentinel D-0113 follow-up); the daily
  // series itself stays in bp.
  return last ? { label: OAT_BUND_LABEL, val: last.bp / 100, date: last.date, tip: tip } : dash;
}

/**
 * Sentinel D-0113 (amends D-0111's card clause, display only): the country
 * cards for the four FB countries show the daily FB curve. ISO3 -> FB code.
 */
export const FB_CARD_COUNTRY = { DEU: "DE", GBR: "GB", JPN: "JP", FRA: "FR" };

/** The five FB codes a country card reads, or [] for every other country. */
export function fbCardCodes(iso) {
  const cc = FB_CARD_COUNTRY[iso];
  return cc ? FB_TENORS.map((t) => `FB_${cc}_${String(t).padStart(2, "0")}Y`) : [];
}

/** The FB tab's chart metrics for one country, for the card's embedded chart. */
export function fbCardMetrics(iso) {
  const codes = new Set(fbCardCodes(iso));
  return FOREIGN_BOND_METRICS.filter((m) => codes.has(m.code));
}

/**
 * Per-source staleness limits, in days. A mirror of `max_age_days` for
 * foreign_bonds_{de,gb,jp,fr} in pipelines/freshness_watchdog.py, the rule the
 * Foreign Bonds tab's spreads already follow; tests/test_d0113_card_freshness.py
 * fails if the two disagree.
 */
export const FB_MAX_AGE_DAYS = { DE: 4, GB: 5, JP: 7, FR: 4 };

const FB_CARD_SOURCE = {
  DE: "FIT: Deutsche Bundesbank Svensson fitted zero-coupon curve, daily",
  GB: "FIT: Bank of England GLC fitted spot curve, daily",
  JP: "CMT: Ministry of Finance constant-maturity par yield, daily",
  FR: "CMT: Banque de France TEC constant-maturity, daily",
};

const DAY = 86400000;
function ageDays(date, now) {
  if (!date) return null;
  return Math.floor((now.getTime() - Date.parse(`${String(date).slice(0, 10)}T00:00:00Z`)) / DAY);
}

/**
 * What a country card shows from the FB curve (Sentinel D-0113), or null for a
 * non-FB country. `latest` is the flat `{code: value}` map (FB codes plus the
 * SOVEREIGN_YIELD_CODES fallback), `dates` the newest observation date per code.
 *
 * tenYear: the daily FB 10Y while fresh; otherwise the monthly OECD series,
 *   badged MONTHLY. slopes: 2s10s and 10s30s in bp, null ("—") when a leg is
 *   missing, stale beyond FB_MAX_AGE_DAYS, or dated differently from the other.
 */
export function countryBond(iso, latest = {}, dates = {}, now = new Date()) {
  const cc = FB_CARD_COUNTRY[iso];
  if (!cc) return null;
  const limit = FB_MAX_AGE_DAYS[cc];
  const curve = fbCardCodes(iso).map((code, i) => {
    const value = latest[code] ?? null;
    const date = value != null && dates[code] ? String(dates[code]).slice(0, 10) : null;
    const age = ageDays(date, now);
    return { tenor: FB_TENORS[i], label: `${FB_TENORS[i]}Y`, code, value, date,
      stale: value == null || age == null || age > limit };
  });
  const leg = (t) => curve.find((c) => c.tenor === t);
  const slope = (label, a, b) => {
    const s = leg(a), l = leg(b);
    const ok = !s.stale && !l.stale && s.date === l.date;
    return { label, bp: ok ? Math.round((l.value - s.value) * 10000) / 100 : null };
  };
  const ten = leg(10);
  const monthlyCode = SOVEREIGN_YIELD_CODES[iso];
  const tenYear = !ten.stale
    ? { value: ten.value, daily: true, code: ten.code, badge: null, kind: FB_COUNTRY[cc].kind,
        tip: `Source: ${ten.code}, ${FB_CARD_SOURCE[cc]} (as of ${ten.date}). Display only (Sentinel D-0113).` }
    : { value: latest[monthlyCode] ?? null, daily: false, code: monthlyCode, badge: "MONTHLY", kind: "MON",
        tip: `Source: monthly OECD average via FRED ${monthlyCode}, the FALLBACK: no daily ${ten.code} within ${limit} days. It can sit weeks behind (Sentinel D-0113).` };
  return {
    tenYear,
    curve,
    slopes: [slope("2s10s", 2, 10), slope("10s30s", 10, 30)],
  };
}

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
