import { describe, expect, it } from "vitest";
import {
  changeBetween,
  changeSuffix,
  changeWindowLabel,
  latestByCode,
  priorObservation,
  seriesByCode,
} from "./series";

/** `n` consecutive daily points ending 2026-09-28. */
const dailyRun = (n) =>
  Array.from({ length: n }, (_, i) => {
    const d = new Date("2026-09-28T00:00:00Z");
    d.setUTCDate(d.getUTCDate() - (n - 1 - i));
    return { date: d.toISOString().slice(0, 10), value: 4 + i / 100 };
  });

describe("priorObservation", () => {
  it("looks back by DATE, not by one row", () => {
    // F-0055 stated directly. The old code took points.at(-2) - the previous
    // day - and the card called it "vs 30d".
    const prior = priorObservation(dailyRun(60), 30);
    expect(prior.actualDays).toBeGreaterThanOrEqual(30);
    expect(prior.date).not.toBe("2026-09-27");
  });

  it("reports the gap it actually found", () => {
    // A weekly series cannot land exactly on 30 days; the label must say what
    // was used rather than claim thirty.
    const weekly = ["2026-07-06", "2026-08-03", "2026-08-31", "2026-09-28"].map(
      (date, i) => ({ date, value: i }),
    );
    const prior = priorObservation(weekly, 30);
    expect(prior.date).toBe("2026-08-03");
    expect(prior.actualDays).toBe(56);
  });

  it("returns null rather than the oldest point it happens to have", () => {
    // Silently comparing against "whatever I've got" and calling it 30 days is
    // the defect, not a graceful fallback.
    expect(priorObservation(dailyRun(5), 30)).toBeNull();
  });

  it("handles a series with exactly two points", () => {
    expect(priorObservation(dailyRun(2), 30)).toBeNull();
    expect(priorObservation(dailyRun(2), 0)).not.toBeNull();
  });

  it("returns null for empty or single-point input", () => {
    expect(priorObservation([], 30)).toBeNull();
    expect(priorObservation([{ date: "2026-09-28", value: 1 }], 30)).toBeNull();
    expect(priorObservation(undefined, 30)).toBeNull();
  });

  it("picks the LAST point at or before the cutoff, not the first", () => {
    const points = dailyRun(90);
    const prior = priorObservation(points, 30);
    // 30 days back from 2026-09-28 is 2026-08-29; a daily run has that exact day.
    expect(prior.date).toBe("2026-08-29");
    expect(prior.actualDays).toBe(30);
  });
});

describe("changeBetween", () => {
  it("gives percentage POINTS for a percent series", () => {
    expect(changeBetween(5.18, 4.96, "%")).toBeCloseTo(0.22, 10);
  });

  it("gives percent change for a priced series", () => {
    expect(changeBetween(110, 100, "$/bbl")).toBeCloseTo(10, 10);
  });

  it("treats an index (empty unit) as points, not percent", () => {
    // DTWEXBGS is an index; a 1.5 move is 1.5 points, not 1.5%.
    expect(changeBetween(121, 119.5, "")).toBeCloseTo(1.5, 10);
  });

  it("is null when either side is missing", () => {
    expect(changeBetween(null, 4, "%")).toBeNull();
    expect(changeBetween(4, null, "%")).toBeNull();
  });

  it("does not divide by zero", () => {
    expect(changeBetween(5, 0, "$/bbl")).toBeNull();
  });

  it("keeps the sign", () => {
    expect(changeBetween(4.9, 5.1, "%")).toBeLessThan(0);
  });
});

describe("changeSuffix", () => {
  it("is pp for a percent series and % otherwise", () => {
    expect(changeSuffix("%")).toBe("pp");
    expect(changeSuffix("$/bbl")).toBe("%");
    expect(changeSuffix("")).toBe("%");
  });
});

describe("changeWindowLabel", () => {
  it("names the real gap", () => {
    expect(changeWindowLabel(30)).toBe("vs 30d");
    expect(changeWindowLabel(56)).toBe("vs 56d");
  });

  it("says nothing when there is no comparison", () => {
    expect(changeWindowLabel(null)).toBe("");
  });

  it("never claims 30 days for a 3-day gap", () => {
    // The production symptom: eight of eleven tickers said "vs 30d" over a
    // one-to-three-day move.
    expect(changeWindowLabel(3)).not.toContain("30");
  });
});

describe("seriesByCode / latestByCode", () => {
  const rows = [
    { date: "2026-09-25", DGS10: 5.18, M2SL: null },
    { date: "2026-09-28", DGS10: 5.15 },
    { date: "2026-08-01", M2SL: 23342.8 },
  ];

  it("splits rows into ascending per-code series", () => {
    const s = seriesByCode(rows, ["DGS10", "M2SL"]);
    expect(s.DGS10.map((p) => p.date)).toEqual(["2026-09-25", "2026-09-28"]);
    expect(s.M2SL.map((p) => p.date)).toEqual(["2026-08-01"]);
  });

  it("drops nulls rather than carrying them as values", () => {
    expect(seriesByCode(rows, ["M2SL"]).M2SL).toHaveLength(1);
  });

  it("gives an empty series for an unknown code rather than throwing", () => {
    expect(seriesByCode(rows, ["NOPE"]).NOPE).toEqual([]);
  });

  it("takes the last point per code", () => {
    const latest = latestByCode(seriesByCode(rows, ["DGS10", "M2SL", "NOPE"]));
    expect(latest.DGS10).toBe(5.15);
    expect(latest.M2SL).toBe(23342.8);
    expect(latest.NOPE).toBeUndefined();
  });
});
