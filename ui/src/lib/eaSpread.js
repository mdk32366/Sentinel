/**
 * Sentinel D-0117 (vault:D-0059): "Spread to EA AAA 10Y" on the six euro-area
 * member cards. Display only: computed at read time from what the card already
 * shows, nothing stored, no metric code, never scored (the composite, the
 * scorer and D-0114 are untouched).
 *
 * The hard part is basis (spec §8): the AAA leg is a daily Svensson spot rate,
 * the member legs are daily yields or monthly averages. So a daily member value
 * pairs with the latest AAA on or before its own date (at most 3 calendar days
 * back), and a monthly member value pairs with the MEAN of the AAA daily points
 * in the same month (at least 10 of them). Anything else is a dash, never a
 * guess, and never a daily AAA point against a monthly member.
 */
import { FB_MAX_AGE_DAYS, SOVEREIGN_YIELD_CODES } from "./constants";

/** The members, fixed in code (spec §2). Nothing is inferred from the data. */
export const EA_SPREAD_MEMBERS = ["FRA", "DEU", "ESP", "ITA", "GRC", "PRT"];
/** The only benchmark. FB_EA_ALL_10Y is never the subtrahend (spec §3). */
export const EA_AAA_10Y = "FB_EA_AAA_10Y";
/** The EA panel on FOREIGN-BONDS, a tab view (the D-0109 `#/<tab>/<view>` form). */
export const EA_BENCHMARK_HREF = "#/foreign-bonds/ea-benchmark";

const MAX_GAP_DAYS = 3;
const MIN_MONTH_OBS = 10;
// The watchdog's `sovereign_yields` limit, measured from the month end, for
// ESP's last fallback (the OECD monthly series, which the card does not age).
const OECD_MAX_AGE_DAYS = 70;

/** Member 10Y sources a readout may use, in the card's fallback order (§2). */
const SOURCES = {
  FRA: ["FB_FR_10Y"],
  DEU: ["FB_DE_10Y"],
  ESP: ["FB_ES_10Y", "FB_ES_10Y_ECB_M", SOVEREIGN_YIELD_CODES.ESP],
  ITA: ["FB_IT_10Y", "FB_IT_10Y_ECB_M"],
  GRC: ["FB_GR_10Y_ECB_M"],
  PRT: ["FB_PT_10Y_ECB_M"],
};
const DAILY = new Set(["FB_FR_10Y", "FB_DE_10Y", "FB_ES_10Y"]);
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

const TIP = "Member 10Y minus ECB euro-area AAA Svensson 10Y spot (ECB YC). Display only; not scored. The AAA curve is fitted, not a traded bond; basis differs from the member's source (see Foreign Bonds → EA benchmark).";
const DEU_TIP = " DEU is itself in the AAA basket, so its spread is small or negative: that is correct, not a bug.";
const MONTHLY_TIP = " MONTHLY: the member value is a monthly figure, set against the mean of the AAA daily observations in the same month.";

const DAY = 86400000;
const day = (d) => String(d).slice(0, 10);
const daysBetween = (a, b) => Math.round((Date.parse(`${b}T00:00:00Z`) - Date.parse(`${a}T00:00:00Z`)) / DAY);
function monthEnd(d) {
  const [y, m] = d.split("-").map(Number);
  return new Date(Date.UTC(y, m, 0)).toISOString().slice(0, 10);
}

/**
 * (member − AAA) in bp, both in percent, rounded to an integer with halves
 * away from zero so +x.5 and −x.5 mirror each other. The difference is first
 * snapped to 1e-4 bp so float noise (3.41 − 2.705 = 0.70499…) cannot flip a half.
 */
export function eaSpreadBp(member, aaa) {
  const bp = Math.round((member - aaa) * 1e6) / 1e4;
  return Math.sign(bp) * Math.round(Math.abs(bp)) || 0;
}

/** The extra codes a member card requests for its readout; [] for anyone else. */
export function eaSpreadFetchCodes(iso) {
  if (!EA_SPREAD_MEMBERS.includes(iso)) return [];
  return iso === "ESP" ? [EA_AAA_10Y, SOVEREIGN_YIELD_CODES.ESP] : [EA_AAA_10Y];
}

/**
 * The readout for one card, or null for a non-member. `bond` is what
 * `countryBond` returned (its 10Y already applies the fallback order and the
 * watchdog-mirrored freshness limits); `series` is `{code: [{date, value}]}`
 * for the card's codes plus `eaSpreadFetchCodes(iso)`.
 *
 * Returns `{ bp, monthly, asOf, reason, tip, href }`; `bp` is null for a dash
 * and `reason` then says why.
 */
export function eaSpreadReadout(iso, bond, series = {}, now = new Date()) {
  if (!EA_SPREAD_MEMBERS.includes(iso)) return null;
  const baseTip = TIP + (iso === "DEU" ? DEU_TIP : "");
  const out = { bp: null, monthly: false, asOf: null, reason: null, tip: baseTip, href: EA_BENCHMARK_HREF };
  const dash = (reason) => ({ ...out, reason, tip: `${out.tip} A dash: ${reason}.` });

  const ten = bond?.tenYear;
  const code = ten?.code;
  const member = ten?.value;
  const memberLast = code ? series[code]?.at(-1) : null;
  if (!SOURCES[iso].includes(code) || !Number.isFinite(member) || !memberLast) return dash("member 10Y unavailable");
  const dm = day(memberLast.date);
  const today = now.toISOString().slice(0, 10);
  if (code === SOVEREIGN_YIELD_CODES.ESP && daysBetween(monthEnd(dm), today) > OECD_MAX_AGE_DAYS) {
    return dash("member 10Y unavailable");
  }
  out.monthly = !DAILY.has(code);
  if (out.monthly) out.tip += MONTHLY_TIP;

  const aaa = (series[EA_AAA_10Y] ?? []).filter((p) => Number.isFinite(p?.value)).map((p) => ({ date: day(p.date), value: p.value }));
  const aaaLast = aaa.at(-1);
  if (!aaaLast || daysBetween(aaaLast.date, today) > FB_MAX_AGE_DAYS.EA) return dash("benchmark unavailable");

  if (!out.monthly) {
    const pair = aaa.filter((p) => p.date <= dm).at(-1);
    if (!pair || daysBetween(pair.date, dm) > MAX_GAP_DAYS) return dash(`no AAA observation within ${MAX_GAP_DAYS} days of ${dm}`);
    return { ...out, bp: eaSpreadBp(member, pair.value), asOf: dm };
  }
  const month = dm.slice(0, 7);
  const label = `${MONTHS[Number(month.slice(5)) - 1]} ${month.slice(0, 4)}`;
  const inMonth = aaa.filter((p) => p.date.startsWith(month));
  if (inMonth.length < MIN_MONTH_OBS) {
    return { ...dash(`fewer than ${MIN_MONTH_OBS} AAA observations in ${label}`), monthly: true };
  }
  const mean = inMonth.reduce((s, p) => s + p.value, 0) / inMonth.length;
  return { ...out, bp: eaSpreadBp(member, mean), asOf: label };
}
