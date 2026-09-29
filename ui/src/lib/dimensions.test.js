import { describe, expect, it } from "vitest";

import {
  MAX_RAW_SCORE,
  STRESS_DIMENSIONS,
  STRESS_MULTIPLIERS,
  scoreBreakdown,
} from "./dimensions";

/** A composite row shaped like the API's, with only the fields that matter. */
const row = (parts) => ({ composite_score: 0, ...parts });

describe("STRESS_DIMENSIONS", () => {
  it("covers all six scored dimensions", () => {
    // F-0076: the panel listed four. tests/test_composite_dimensions.py
    // cross-checks these keys against the Python scorer, which is the half
    // that cannot be asserted from here.
    expect(STRESS_DIMENSIONS).toHaveLength(6);
    expect(STRESS_DIMENSIONS.map((d) => d.key)).toContain("cds_score");
    expect(STRESS_DIMENSIONS.map((d) => d.key)).toContain("monetary_score");
  });

  it("gives every dimension a label, a cap, a colour and a description", () => {
    for (const d of STRESS_DIMENSIONS) {
      expect(d.label, d.key).toBeTruthy();
      expect(d.max, d.key).toBeGreaterThan(0);
      expect(d.color, d.key).toMatch(/^#[0-9A-Fa-f]{6}$/);
      expect(d.desc.length, d.key).toBeGreaterThan(15);
    }
  });

  it("has no duplicate keys or colours", () => {
    const keys = STRESS_DIMENSIONS.map((d) => d.key);
    const colors = STRESS_DIMENSIONS.map((d) => d.color);
    expect(new Set(keys).size).toBe(keys.length);
    // Shared colours would make the segmented bar unreadable.
    expect(new Set(colors).size).toBe(colors.length);
  });

  it("MAX_RAW_SCORE is the sum of the caps", () => {
    expect(MAX_RAW_SCORE).toBe(185);
    expect(MAX_RAW_SCORE).toBe(STRESS_DIMENSIONS.reduce((s, d) => s + d.max, 0));
  });

  it("lists the multipliers separately from the points", () => {
    // Dimension 6 is a multiplier, not points — which is exactly why it was
    // easy to omit from a panel headed "SCORE =".
    expect(STRESS_MULTIPLIERS.length).toBeGreaterThanOrEqual(3);
    for (const m of STRESS_MULTIPLIERS) expect(m.label).toMatch(/^×/);
  });
});

describe("scoreBreakdown", () => {
  it("returns only the dimensions that contributed, largest first", () => {
    const parts = scoreBreakdown(row({ tic_score: 30, cds_score: 10, gold_score: 0 }));
    expect(parts.map((p) => p.key)).toEqual(["tic_score", "cds_score"]);
  });

  it("computes each share of the raw total", () => {
    const parts = scoreBreakdown(row({ tic_score: 30, cds_score: 10 }));
    expect(parts[0].share).toBeCloseTo(75, 10);
    expect(parts[1].share).toBeCloseTo(25, 10);
    expect(parts.reduce((s, p) => s + p.share, 0)).toBeCloseTo(100, 10);
  });

  it("reports a sole driver as 100%", () => {
    // The case the CDS work exists for: Brazil is ranked on CDS alone, and
    // the surface should say so rather than leave it to be inferred.
    const parts = scoreBreakdown(row({ cds_score: 5 }));
    expect(parts).toHaveLength(1);
    expect(parts[0].key).toBe("cds_score");
    expect(parts[0].share).toBe(100);
  });

  it("ignores dimensions that are absent or zero rather than drawing empty segments", () => {
    const parts = scoreBreakdown(row({ tic_score: 10, gold_score: 0, petro_score: null }));
    expect(parts).toHaveLength(1);
  });

  it("survives a missing or empty row", () => {
    expect(scoreBreakdown(null)).toEqual([]);
    expect(scoreBreakdown(undefined)).toEqual([]);
    expect(scoreBreakdown(row({}))).toEqual([]);
  });

  it("does not divide by zero when nothing contributed", () => {
    expect(() => scoreBreakdown(row({ tic_score: 0 }))).not.toThrow();
    expect(scoreBreakdown(row({ tic_score: 0 }))).toEqual([]);
  });

  it("coerces string values the API may send", () => {
    const parts = scoreBreakdown(row({ tic_score: "30", cds_score: "10" }));
    expect(parts.map((p) => p.value)).toEqual([30, 10]);
  });
});
