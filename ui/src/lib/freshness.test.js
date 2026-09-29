import { describe, expect, it } from "vitest";

import { TIC_TOLERANCE_DAYS, ageInDays, freshness } from "./freshness";

const NOW = new Date(2026, 8, 29); // 2026-09-29, local

describe("ageInDays", () => {
  it("handles the month-precision form the composite sends", () => {
    // The composite's as_of is "2025-12" — a month, not a day.
    expect(ageInDays("2025-12", NOW)).toBe(302);
  });

  it("handles a full date and an ISO timestamp", () => {
    expect(ageInDays("2026-09-28", NOW)).toBe(1);
    expect(ageInDays("2026-09-28T00:00:00", NOW)).toBe(1);
  });

  it("reads the calendar day from the string, not from a timezone shift", () => {
    // F-0071 again: a bare date parsed as UTC midnight renders a day early
    // west of UTC, and an age computed from it is off by one everywhere.
    expect(ageInDays("2026-09-29", NOW)).toBe(0);
  });

  it("is null for a missing or unparseable value rather than NaN", () => {
    for (const bad of [null, undefined, "", "unknown", "Dec 2025"]) {
      expect(ageInDays(bad, NOW), String(bad)).toBeNull();
    }
  });
});

describe("freshness", () => {
  it("flags the real case: TIC frozen at December 2025", () => {
    const f = freshness("2025-12", TIC_TOLERANCE_DAYS, NOW);
    expect(f.age).toBe(302);
    expect(f.stale).toBe(true);
    expect(f.text).toBe("302 days old");
  });

  it("does not flag an ordinary monthly lag", () => {
    // TIC publishes monthly with roughly a two-month lag. That is the
    // source's cadence, not a fault, and colouring it red would train the
    // reader to ignore the colour.
    const f = freshness("2026-08", TIC_TOLERANCE_DAYS, NOW);
    expect(f.stale).toBe(false);
    expect(f.color).toBe("#1E2D3D");
  });

  it("turns failure-red only past the tolerance", () => {
    expect(freshness("2026-06-22", TIC_TOLERANCE_DAYS, NOW).stale).toBe(false);
    expect(freshness("2026-06-20", TIC_TOLERANCE_DAYS, NOW).stale).toBe(true);
  });

  it("agrees with the threshold the pipeline itself enforces", () => {
    // MAX_SOURCE_AGE_DAYS in pipelines/treasury_holdings.py. The UI and the
    // pipeline must mean the same thing by "too old", or the screen and the
    // log disagree about whether anything is wrong.
    expect(TIC_TOLERANCE_DAYS).toBe(100);
  });

  it("says nothing at all when there is no date", () => {
    const f = freshness(null, TIC_TOLERANCE_DAYS, NOW);
    expect(f.text).toBe("");
    expect(f.stale).toBe(false);
  });
});
