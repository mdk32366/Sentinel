import { describe, expect, it } from "vitest";
import {
  formatValue,
  scoreColor,
  spreadBasisPoints,
  spreadColor,
  tierColor,
  tierLabel,
} from "./format";

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
