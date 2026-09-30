import { describe, expect, it } from "vitest";
import { asLocalDate, formatDate, formatValue, scoreColor, spreadBasisPoints, spreadColor, tierColor, tierLabel, trillions } from "./format";

describe("formatValue", () => {
  it("renders a percent to two places", () => {
    expect(formatValue(5.18, "%")).toBe("5.18%");
    expect(formatValue(5.1, "%")).toBe("5.10%");
  });

  it("rounds via toFixed, which is not half-up on binary boundaries", () => {
    // 5.175 is 5.17499... in IEEE-754, so toFixed(2) gives "5.17". Recorded
    // rather than worked around: the display is a display, and a half-cent on
    // a yield is not worth a rounding library. Written down so the next person
    // to see it does not "fix" it.
    expect(formatValue(5.175, "%")).toBe("5.17%");
  });

  it("renders a price with a leading dollar", () => {
    expect(formatValue(96.4123, "$/bbl")).toBe("$96.41");
  });

  it("converts billions to trillions for B$", () => {
    // M2 arrives as 23342.8 (billions). The division and the "T" must agree;
    // changing one without the other misstates money by 1000x.
    expect(formatValue(23342.8, "B$")).toBe("$23.3T");
  });

  it("falls back to two decimals for an index", () => {
    expect(formatValue(119.5133, "")).toBe("119.51");
  });

  it("renders gold in whole dollars with a separator", () => {
    // Four figures. Cents are noise and the separator is what makes it
    // readable at a glance in a ticker row.
    expect(formatValue(4261.05, "$/oz")).toBe("$4,261");
    expect(formatValue(987.4, "$/oz")).toBe("$987");
  });

  it("rounds gold rather than truncating", () => {
    expect(formatValue(4261.6, "$/oz")).toBe("$4,262");
  });

  it("does not confuse $/oz with $/bbl", () => {
    // Oil keeps its cents; gold does not. Sharing a branch would print
    // "$4261.05" in a column sized for five characters.
    expect(formatValue(96.41, "$/bbl")).toBe("$96.41");
    expect(formatValue(96.41, "$/oz")).toBe("$96");
  });

  it("returns null for a missing value rather than printing 0", () => {
    // A zero yield is plausible on its face, which is what makes it dangerous.
    expect(formatValue(null, "%")).toBeNull();
    expect(formatValue(undefined, "%")).toBeNull();
  });

  it("renders a genuine zero rather than swallowing it", () => {
    expect(formatValue(0, "%")).toBe("0.00%");
  });

  it("keeps negative values, which are real for yields", () => {
    expect(formatValue(-0.45, "%")).toBe("-0.45%");
  });
});

describe("scoreColor", () => {
  it("escalates at the documented thresholds", () => {
    expect(scoreColor(49.9)).toBe(scoreColor(25));
    expect(scoreColor(50)).not.toBe(scoreColor(49.9));
    expect(scoreColor(24.9)).not.toBe(scoreColor(25));
  });

  it("is inclusive at each boundary", () => {
    expect(scoreColor(50)).toBe("#E07B5A");
    expect(scoreColor(25)).toBe("#E8C547");
    expect(scoreColor(0)).toBe("#5A6878");
  });
});

describe("tierColor / tierLabel", () => {
  const tiers = ["DIVERGENCE", "CROSS_ASSET", "TREASURY_ONLY", "GOLD_ONLY"];

  it("gives every known tier its own colour", () => {
    const colors = tiers.map(tierColor);
    expect(new Set(colors).size).toBe(tiers.length);
  });

  it("handles the EXITED tiers the live table renders", () => {
    // These two were the gap: the extracted helpers covered four tiers while
    // the component that actually renders them had an inline six-tier ternary.
    // The tested copy was the dead one.
    expect(tierLabel("EXITED")).toBe("🚨 EXITED");
    expect(tierLabel("EXITED+GOLD_SELL")).toBe("🚨 EXITED+Au↓");
    expect(tierColor("EXITED")).toBe("#FF8C00");
  });

  it("gives both EXITED variants the same colour, deliberately", () => {
    // They share a colour because they are the same alert at different
    // severities; the LABEL is what distinguishes them.
    expect(tierColor("EXITED")).toBe(tierColor("EXITED+GOLD_SELL"));
    expect(tierLabel("EXITED")).not.toBe(tierLabel("EXITED+GOLD_SELL"));
  });

  it("keeps EXITED distinct from every other tier's colour", () => {
    for (const tier of tiers) {
      expect(tierColor("EXITED")).not.toBe(tierColor(tier));
    }
  });

  it("falls back rather than throwing on an unknown tier", () => {
    expect(tierColor("SOMETHING_NEW")).toBe("#5A6878");
    expect(tierLabel("SOMETHING_NEW")).toBe("SOMETHING_NEW");
  });

  it("labels the two alerting tiers distinctly", () => {
    expect(tierLabel("DIVERGENCE")).not.toBe(tierLabel("CROSS_ASSET"));
  });
});

describe("spreadBasisPoints", () => {
  it("converts a percentage-point difference to basis points", () => {
    expect(spreadBasisPoints(6.18, 5.18)).toBeCloseTo(100, 10);
  });

  it("keeps a negative spread negative", () => {
    expect(spreadBasisPoints(4.18, 5.18)).toBeCloseTo(-100, 10);
  });

  it("is null when either yield is missing", () => {
    expect(spreadBasisPoints(null, 5.18)).toBeNull();
    expect(spreadBasisPoints(5.18, null)).toBeNull();
  });
});

describe("spreadColor", () => {
  it("escalates with the spread", () => {
    expect(spreadColor(200)).toBe("#FF4444");
    expect(spreadColor(100)).toBe("#E07B5A");
    expect(spreadColor(10)).toBe("#E8C547");
    expect(spreadColor(-10)).toBe("#7EB8C9");
  });

  it("distinguishes 'no data' from 'negative spread'", () => {
    // Both are calm-looking; only one means we know something.
    expect(spreadColor(null)).not.toBe(spreadColor(-10));
  });
});

describe("asLocalDate / formatDate — F-0071", () => {
  it("the suite is running west of UTC, so this guard is actually armed", () => {
    // Clause (c). At UTC the old code and the new code are IDENTICAL, so no
    // assertion below can tell them apart there. CI runners default to UTC.
    // vite.config.js pins TZ=America/New_York; if that ever stops taking
    // effect, this says so instead of the rest quietly becoming decoration.
    expect(new Date("2026-08-01").getTimezoneOffset()).toBeGreaterThan(0);
  });

  /**
   * These assert the DATE COMPONENTS, not the rendered string.
   *
   * A test asserting `formatDate("2026-08-01")` contains "Aug 1" passes under
   * UTC and every positive offset even with the bug present — so on a CI
   * runner set to UTC it would have gone green throughout. Asserting the
   * components bites in every timezone, including the one CI happens to use.
   */
  it("takes the calendar day from the string, not from a timezone conversion", () => {
    const d = asLocalDate("2026-08-01");
    expect(d.getFullYear()).toBe(2026);
    expect(d.getMonth()).toBe(7);   // August
    expect(d.getDate()).toBe(1);
  });

  it("treats a bare date and a midnight timestamp as the same day", () => {
    // pivotByDate strips the time, so both forms reach formatDate.
    for (const form of ["2026-08-01", "2026-08-01T00:00:00"]) {
      expect(asLocalDate(form).getDate(), form).toBe(1);
      expect(asLocalDate(form).getMonth(), form).toBe(7);
    }
  });

  it("does not roll a month boundary backwards", () => {
    // The case the user hit: FRED dates a monthly average to the 1st, so the
    // bug turned August's fed funds figure into "Jul 31" on screen.
    expect(formatDate("2026-08-01")).toMatch(/Aug 1/);
    expect(formatDate("2026-08-01")).not.toMatch(/Jul/);
  });

  it("does not roll a year boundary backwards either", () => {
    expect(formatDate("2026-01-01")).toMatch(/Jan 1, 26/);
    expect(formatDate("2026-01-01")).not.toMatch(/25/);
  });

  it("still handles a Date object and a full ISO instant", () => {
    expect(asLocalDate(new Date(2026, 7, 1)).getDate()).toBe(1);
    // A Z-suffixed instant keeps its calendar day, because every date in this
    // application IS a calendar date - the API stamps observations at
    // midnight, it does not record the moment they were taken.
    expect(asLocalDate("2026-08-01T00:00:00Z").getDate()).toBe(1);
  });
});

describe("trillions", () => {
  it("rounds a midpoint away from zero rather than down", () => {
    // (5475.0 / 1000).toFixed(2) is "5.47": 5.475 has no exact binary
    // representation and lands just below the midpoint. The real Foreign
    // Official private side is $5,475.0bn, so the screen read $5.47T while the
    // payload said 5.475 — small, and still a number the code did not mean.
    expect(trillions(5475.0)).toBe("5.48");
  });

  it("agrees with toFixed where there is no midpoint", () => {
    expect(trillions(1842.4)).toBe("1.84");
    expect(trillions(3773.1)).toBe("3.77");
    expect(trillions(9248.1)).toBe("9.25");
  });

  it("returns null rather than NaN for a missing value", () => {
    expect(trillions(null)).toBeNull();
    expect(trillions(undefined)).toBeNull();
    expect(trillions(NaN)).toBeNull();
  });

  it("handles zero and negatives", () => {
    expect(trillions(0)).toBe("0.00");
    expect(trillions(-5475.0)).toBe("-5.48");
  });
});
