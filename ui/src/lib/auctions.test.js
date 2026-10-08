/**
 * The Auction Demand panel's pure rules (ORDER auction-demand §7).
 *
 * The stale threshold and the charted terms are owner rulings that live in
 * Python too (D-0101, D-0103). tests/test_treasury_auctions.py reads this
 * module and fails if the two disagree; a JS test cannot read the Python.
 */
import { describe, expect, it } from "vitest";

import {
  CHARTED_TERMS,
  STALE_BUSINESS_DAYS,
  businessDaysSince,
  isStale,
  sortRows,
} from "./auctions";

describe("the rulings", () => {
  it("charts the ten v1 terms in order (D-0103)", () => {
    expect(CHARTED_TERMS).toEqual(["4W", "8W", "13W", "17W", "26W", "52W", "2Y", "5Y", "10Y", "30Y"]);
  });

  it("goes stale after three business days (D-0101)", () => {
    expect(STALE_BUSINESS_DAYS).toBe(3);
  });
});

describe("staleness counts business days, not calendar days", () => {
  const friday = "2026-10-02";

  it("counts weekdays after the data date", () => {
    expect(businessDaysSince(friday, new Date("2026-10-05T12:00:00Z"))).toBe(1); // Mon
    expect(businessDaysSince(friday, new Date("2026-10-07T12:00:00Z"))).toBe(3); // Wed
  });

  it("is not stale at three and is stale at four", () => {
    expect(isStale(friday, new Date("2026-10-07T12:00:00Z"))).toBe(false);
    expect(isStale(friday, new Date("2026-10-08T12:00:00Z"))).toBe(true);
  });

  it("has nothing to judge without a date", () => {
    expect(isStale(null, new Date("2026-10-08T12:00:00Z"))).toBe(false);
  });
});

describe("a missing value never sorts as lowest (§3)", () => {
  const rows = [
    { cusip: "A", b2c_recomputed: 2.5 },
    { cusip: "B", b2c_recomputed: null },
    { cusip: "C", b2c_recomputed: 3.1 },
  ];

  it("ascending puts it last", () => {
    expect(sortRows(rows, "b2c_recomputed", "asc").map((r) => r.cusip)).toEqual(["A", "C", "B"]);
  });

  it("descending puts it last too", () => {
    expect(sortRows(rows, "b2c_recomputed", "desc").map((r) => r.cusip)).toEqual(["C", "A", "B"]);
  });

  it("does not reorder its input", () => {
    sortRows(rows, "b2c_recomputed", "asc");
    expect(rows.map((r) => r.cusip)).toEqual(["A", "B", "C"]);
  });
});
