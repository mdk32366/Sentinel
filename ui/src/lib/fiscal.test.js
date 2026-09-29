import { describe, expect, it } from "vitest";

import {
  ANNUAL_REVENUE_T, ANNUAL_ROLLOVER_T, LOCKED_IN_INTEREST_T,
  SPR_CAPACITY_MB, SPR_CURRENT_MB, US_GOLD_TONNES, US_GOLD_TROY_OZ,
  breakingPointRate, crisisRate, dangerColor, interestCost,
  interestPercentOfRevenue, rateTable, usGoldValueT,
} from "./fiscal";

/**
 * The USA dashboard's fiscal panel had no tests and eight hand-entered
 * constants (`A-0012`). These do not check that the MODEL is right — it is an
 * admitted sensitivity, not a forecast. They check that the arithmetic says
 * what the page claims it says, and that the thresholds it draws lines at are
 * where it says they are.
 */
describe("interestCost", () => {
  it("is locked-in cost plus this year's rollover at the given yield", () => {
    // 0.55 + 6.0 * 0.04 = 0.79
    expect(interestCost(4)).toBeCloseTo(LOCKED_IN_INTEREST_T + ANNUAL_ROLLOVER_T * 0.04, 10);
    expect(interestCost(4)).toBeCloseTo(0.79, 10);
  });

  it("matches the headline claim: every 100bps costs about $60B a year", () => {
    // The panel prints "Every 100bps = +$60B/yr in new interest". $0.06T.
    const delta = interestCost(5) - interestCost(4);
    expect(delta).toBeCloseTo(0.06, 10);
  });

  it("is null rather than NaN for a missing yield", () => {
    expect(interestCost(null)).toBeNull();
    expect(interestCost(undefined)).toBeNull();
    expect(interestCost(NaN)).toBeNull();
  });
});

describe("the thresholds the page draws lines at", () => {
  it("the warning rate is where interest reaches 25% of revenue", () => {
    const rate = breakingPointRate();
    expect(interestPercentOfRevenue(rate)).toBeCloseTo(25, 6);
  });

  it("the crisis rate is where interest reaches 35% of revenue", () => {
    const rate = crisisRate();
    expect(interestPercentOfRevenue(rate)).toBeCloseTo(35, 6);
  });

  it("the comments' rough figures are still roughly right", () => {
    // The source says "~5.5%" and "~8.5%". If a constant changes, these move,
    // and the comment beside them should move too.
    expect(breakingPointRate()).toBeCloseTo(11.25, 2);
    expect(crisisRate()).toBeCloseTo(19.42, 2);
  });

  it("crisis is strictly above warning", () => {
    expect(crisisRate()).toBeGreaterThan(breakingPointRate());
  });
});

describe("dangerColor", () => {
  const BREAK = breakingPointRate();
  const CRISIS = crisisRate();

  it("is failure-red only at or above the crisis rate", () => {
    expect(dangerColor(CRISIS)).toBe("#FF4444");
    expect(dangerColor(CRISIS + 1)).toBe("#FF4444");
    expect(dangerColor(CRISIS - 0.01)).not.toBe("#FF4444");
  });

  it("warns a full point BEFORE the breaking point, not on arrival", () => {
    // The tile exists to show the threshold approaching.
    expect(dangerColor(BREAK - 0.5)).toBe("#E8C547");
    expect(dangerColor(BREAK)).toBe("#E07B5A");
  });

  it("is green well below the threshold and grey with no yield at all", () => {
    expect(dangerColor(2)).toBe("#5DB87A");
    expect(dangerColor(null)).toBe("#5A6878");
  });
});

describe("rateTable", () => {
  const rows = rateTable();

  it("covers 3.5% to 8% and is monotonically increasing in cost", () => {
    expect(rows[0].rate).toBe(3.5);
    expect(rows[rows.length - 1].rate).toBe(8.0);
    for (let i = 1; i < rows.length; i += 1) {
      expect(rows[i].cost).toBeGreaterThan(rows[i - 1].cost);
      expect(rows[i].pct).toBeGreaterThan(rows[i - 1].pct);
    }
  });

  it("agrees with interestCost row by row", () => {
    for (const row of rows) {
      expect(row.cost).toBeCloseTo(interestCost(row.rate), 10);
      expect(row.pct).toBeCloseTo((row.cost / ANNUAL_REVENUE_T) * 100, 10);
    }
  });
});

describe("usGoldValueT", () => {
  it("prices the US hoard at the live spot rate", () => {
    // F-0057: this was a hardcoded 4587 against a live series. At $4261 the
    // hoard is about $1.11T; the frozen constant overstated it by ~$85bn.
    expect(usGoldValueT(4261)).toBeCloseTo((US_GOLD_TROY_OZ * 4261) / 1e12, 10);
    expect(usGoldValueT(4587) - usGoldValueT(4261)).toBeCloseTo(0.0852, 3);
  });

  it("is null with no spot price, so the tile can say so", () => {
    // Deliberately no fallback constant: a plausible wrong number is worse
    // than an admitted absence.
    expect(usGoldValueT(null)).toBeNull();
  });
});

describe("the recorded constants", () => {
  it("are the FY2024 figures the panel's footnote quotes", () => {
    expect(ANNUAL_REVENUE_T).toBe(4.9);
    expect(ANNUAL_ROLLOVER_T).toBe(6.0);
    expect(LOCKED_IN_INTEREST_T).toBe(0.55);
    expect(US_GOLD_TONNES).toBe(8133);
  });

  it("keep the SPR below its capacity", () => {
    expect(SPR_CURRENT_MB).toBeLessThan(SPR_CAPACITY_MB);
  });
});
