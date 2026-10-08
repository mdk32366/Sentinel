/**
 * The Auction Demand panel's rules (ORDER auction-demand §7).
 *
 * CHARTED_TERMS and STALE_BUSINESS_DAYS are owner rulings that also live in
 * `pipelines/auction_demand.py` (D-0103, D-0101). They are mirrored here
 * rather than fetched because the panel needs them before the first response
 * arrives; `tests/test_treasury_auctions.py` fails if the two copies differ.
 */

/** Panel term labels, in display order (D-0103). */
export const CHARTED_TERMS = ["4W", "8W", "13W", "17W", "26W", "52W", "2Y", "5Y", "10Y", "30Y"];

/** More than this many business days without a new auction is stale (D-0101). */
export const STALE_BUSINESS_DAYS = 3;

const DAY_MS = 86_400_000;

function utcDay(value) {
  if (value instanceof Date) {
    return Date.UTC(value.getUTCFullYear(), value.getUTCMonth(), value.getUTCDate());
  }
  const [y, m, d] = String(value).slice(0, 10).split("-").map(Number);
  return Date.UTC(y, m - 1, d);
}

/** Weekdays after `asOf` up to and including `today`. */
export function businessDaysSince(asOf, today = new Date()) {
  if (!asOf) return null;
  let count = 0;
  for (let t = utcDay(asOf) + DAY_MS; t <= utcDay(today); t += DAY_MS) {
    const weekday = new Date(t).getUTCDay();
    if (weekday !== 0 && weekday !== 6) count += 1;
  }
  return count;
}

export function isStale(asOf, today = new Date()) {
  const days = businessDaysSince(asOf, today);
  return days != null && days > STALE_BUSINESS_DAYS;
}

/**
 * A sorted copy. A missing value sorts last in BOTH directions (§3): absent is
 * a category, and putting it at the bottom of an ascending sort would read as
 * "weakest demand".
 */
export function sortRows(rows, key, dir = "desc") {
  const sign = dir === "asc" ? 1 : -1;
  return [...rows].sort((a, b) => {
    const x = a[key];
    const y = b[key];
    if (x == null && y == null) return 0;
    if (x == null) return 1;
    if (y == null) return -1;
    if (x < y) return -sign;
    if (x > y) return sign;
    return 0;
  });
}

/**
 * Plain-language text for the API's null-reason codes. Placeholder copy:
 * panel wording is owner-ruled (§7) and these are listed in the PR.
 */
const REASONS = {
  source_null: "Not published by Treasury for this auction.",
  absent: "Not published by Treasury for this auction.",
  empty: "Not published by Treasury for this auction.",
  unparseable: "Treasury's figure could not be read.",
  soma_not_reported: "SOMA was not reported for this auction, so bid-to-cover cannot be recomputed without it.",
  totals_not_reported: "Treasury did not publish the totals for this auction.",
  zero_accepted: "Nothing was accepted net of SOMA.",
  reported_missing: "Treasury did not publish a bid-to-cover for this auction.",
  input_missing: "An input to this figure was not published for this auction.",
  zero_denominator: "No competitive bids were accepted.",
  insufficient_history: "Fewer than 8 earlier auctions of this term to compare against.",
  zero_variance: "Every earlier auction in the window had the same value.",
  value_missing: "No value to score.",
  no_term_family: "Cash-management bills have no term family to compare against.",
};

export function reasonText(code) {
  if (!code) return "Not available.";
  return REASONS[code] ?? `Not available (${code}).`;
}

export const fmtRatio = (v) => (v == null ? null : v.toFixed(2));
export const fmtShare = (v) => (v == null ? null : `${(v * 100).toFixed(1)}%`);
export const fmtPct = (v) => (v == null ? null : `${v.toFixed(1)}%`);
export const fmtZ = (v) => (v == null ? null : `${v > 0 ? "+" : ""}${v.toFixed(2)}`);
export const fmtBn = (v) => (v == null ? null : `$${(v / 1e9).toFixed(1)}bn`);
