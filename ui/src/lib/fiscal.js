/**
 * The fiscal breaking-point arithmetic behind the USA dashboard.
 *
 * `A-0012`: every constant here is an input to a displayed number and none of
 * them came from the database. They are FY2024 actuals and CBO estimates,
 * entered by hand, and they will go stale without anything saying so. They
 * live in one module so that the staleness has one address rather than eight.
 *
 * The model is deliberately crude and the page presents it as such: interest
 * cost is what is already locked in, plus this year's rollover at whatever
 * yield you name. It is a sensitivity, not a forecast.
 */

/** $T of federal revenue. FY2024 actual. */
export const ANNUAL_REVENUE_T = 4.9;

/** $T of debt rolling over annually, at an average maturity of about six years. */
export const ANNUAL_ROLLOVER_T = 6.0;

/** $T of interest already locked in at existing rates. */
export const LOCKED_IN_INTEREST_T = 0.55;

/** Million barrels currently in the Strategic Petroleum Reserve. */
export const SPR_CURRENT_MB = 370;

/** Million barrels of SPR capacity. */
export const SPR_CAPACITY_MB = 714;

/** Tonnes of US gold. Unchanged since 1971. */
export const US_GOLD_TONNES = 8133;

/** Troy ounces of US gold, the unit a spot price is quoted in. */
export const US_GOLD_TROY_OZ = 261.5e6;

/** Interest / revenue at which an issuer is in the emerging-market danger zone. */
export const BREAKING_POINT_RATIO = 0.25;

/** Interest / revenue at Japan-level crisis. */
export const CRISIS_RATIO = 0.35;

/**
 * $T of annual interest cost if new debt is issued at `yieldRate` percent.
 *
 * Only the rollover reprices; the rest stays at the rate it was issued at.
 */
export function interestCost(yieldRate) {
  if (yieldRate == null || Number.isNaN(yieldRate)) return null;
  return LOCKED_IN_INTEREST_T + ANNUAL_ROLLOVER_T * (yieldRate / 100);
}

/** Interest cost at `yieldRate` as a percentage of revenue. */
export function interestPercentOfRevenue(yieldRate) {
  const cost = interestCost(yieldRate);
  return cost == null ? null : (cost / ANNUAL_REVENUE_T) * 100;
}

/** The yield at which interest reaches `ratio` of revenue, as a percentage. */
export function rateForRatio(ratio) {
  return ((ratio * ANNUAL_REVENUE_T - LOCKED_IN_INTEREST_T) / ANNUAL_ROLLOVER_T) * 100;
}

/** The yield at which interest reaches 25% of revenue. About 5.5%. */
export const breakingPointRate = () => rateForRatio(BREAKING_POINT_RATIO);

/** The yield at which interest reaches 35% of revenue. About 8.5%. */
export const crisisRate = () => rateForRatio(CRISIS_RATIO);

/** The rows of the sensitivity table. */
export const RATE_TABLE_YIELDS = [3.5, 4.0, 4.5, 5.0, 5.5, 6.0, 7.0, 8.0];

export function rateTable() {
  return RATE_TABLE_YIELDS.map((rate) => ({
    rate,
    cost: interestCost(rate),
    pct: interestPercentOfRevenue(rate),
  }));
}

/**
 * The colour a given yield earns.
 *
 * Failure-red only at or above the crisis rate. The band one point below the
 * breaking point is amber rather than green, because the point of the tile is
 * to show the threshold approaching rather than to announce it on arrival.
 */
export function dangerColor(yieldRate) {
  if (yieldRate == null) return "#5A6878";
  const crisis = crisisRate();
  const breaking = breakingPointRate();
  if (yieldRate >= crisis) return "#FF4444";
  if (yieldRate >= breaking) return "#E07B5A";
  if (yieldRate >= breaking - 1) return "#E8C547";
  return "#5DB87A";
}

/** $T of US gold at a given spot price per troy ounce. */
export function usGoldValueT(spotGold) {
  if (spotGold == null) return null;
  return (US_GOLD_TROY_OZ * spotGold) / 1e12;
}
