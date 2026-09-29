/**
 * Display formatting. Extracted from App.jsx so it can be tested (F-0053).
 *
 * These are small and look obvious, which is exactly why they are worth
 * covering: a wrong branch here prints a plausible number with the wrong unit,
 * and nothing about the output says so.
 */

/**
 * Parse one of this application's dates as a LOCAL calendar date.
 *
 * `F-0071`: every date here is a calendar date — the day an observation is
 * attributed to — not an instant. But `new Date("2026-08-01")` is defined by
 * ECMAScript to parse a bare date as **UTC midnight**, and
 * `toLocaleDateString` then renders it in the viewer's zone. Anywhere west of
 * UTC that is the previous evening, so every date displayed one day early.
 *
 * It was loudest on the monthly series. FRED dates a monthly average to the
 * first of the month, so August's fed funds average rendered as "Jul 31" —
 * making a one-month-old figure look two months old.
 *
 * Accepts `YYYY-MM-DD` and `YYYY-MM-DDTHH:MM:SS`, which is what the API and
 * `pivotByDate` produce, and takes the calendar day from the string itself
 * rather than from a timezone conversion.
 */
export function asLocalDate(value) {
  if (typeof value === "string") {
    const parts = /^(\d{4})-(\d{2})-(\d{2})/.exec(value);
    if (parts) return new Date(+parts[1], +parts[2] - 1, +parts[3]);
  }
  return new Date(value);
}

export function formatDate(d) {
  return asLocalDate(d).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "2-digit",
  });
}

/**
 * `B$` is billions in, trillions out — M2 arrives as 23342.8 and reads as
 * "$23.3T". The division and the label have to move together; changing one
 * without the other misstates money by a factor of a thousand.
 */
export function formatValue(v, unit) {
  if (v == null) return null;
  if (unit === "%") return `${v.toFixed(2)}%`;
  if (unit === "$/bbl") return `$${v.toFixed(2)}`;
  if (unit === "B$") return `$${(v / 1000).toFixed(1)}T`;
  // Gold trades in four figures. Cents are noise at that scale and the
  // separator is what makes 4261 readable at a glance in a ticker row.
  if (unit === "$/oz") return `$${Math.round(v).toLocaleString("en-US")}`;
  return v.toFixed(2);
}

export function scoreColor(score) {
  if (score >= 50) return "#E07B5A";
  if (score >= 25) return "#E8C547";
  return "#5A6878";
}

/**
 * Tier presentation.
 *
 * These cover SIX tiers, not four. An earlier extraction lifted a four-tier
 * copy out of App.jsx and tested it, while the component that actually renders
 * tiers kept its own inline ternary handling EXITED and EXITED+GOLD_SELL as
 * well. Two divergent implementations, and the tested one was the dead one.
 * The live component now calls these.
 */
export function tierColor(tier) {
  if (tier === "DIVERGENCE") return "#FF4444";
  if (tier === "CROSS_ASSET") return "#E07B5A";
  if (tier === "EXITED" || tier === "EXITED+GOLD_SELL") return "#FF8C00";
  if (tier === "TREASURY_ONLY") return "#E8C547";
  if (tier === "GOLD_ONLY") return "#C8A96E";
  return "#5A6878";
}

export function tierLabel(tier) {
  if (tier === "DIVERGENCE") return "⚡ DIVERGENCE";
  if (tier === "CROSS_ASSET") return "⚠ CROSS-ASSET";
  if (tier === "EXITED") return "🚨 EXITED";
  if (tier === "EXITED+GOLD_SELL") return "🚨 EXITED+Au↓";
  if (tier === "TREASURY_ONLY") return "T-ONLY";
  if (tier === "GOLD_ONLY") return "Au ONLY";
  return tier;
}

/** Sovereign spread against the US 10Y, in basis points. */
export function spreadBasisPoints(countryYield, us10y) {
  if (countryYield == null || us10y == null) return null;
  return (countryYield - us10y) * 100;
}

export function spreadColor(spreadBps) {
  if (spreadBps == null) return "#3A4D5C";
  if (spreadBps > 150) return "#FF4444";
  if (spreadBps > 50) return "#E07B5A";
  if (spreadBps > 0) return "#E8C547";
  return "#7EB8C9";
}
