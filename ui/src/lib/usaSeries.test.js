import { describe, expect, it } from "vitest";

import { byMetric, latestValue, yearAgo, yoyPercent, yoySeries } from "./usaSeries";

/** `n` monthly points ending 2026-09-01, each `step` above the last. */
const monthly = (n, start = 100, step = 1) =>
  Array.from({ length: n }, (_, i) => {
    const d = new Date(Date.UTC(2026, 8, 1));
    d.setUTCMonth(d.getUTCMonth() - (n - 1 - i));
    return { date: d.toISOString().slice(0, 10), value: start + i * step };
  });

describe("byMetric", () => {
  it("groups by code, parses the string values, and sorts ascending", () => {
    const out = byMetric([
      { date: "2026-09-01T00:00:00", value: "4.2", metric_code: "DGS10" },
      { date: "2026-08-01T00:00:00", value: "4.0", metric_code: "DGS10" },
      { date: "2026-09-01T00:00:00", value: "21000", metric_code: "M2SL" },
    ]);
    expect(out.DGS10).toEqual([
      { date: "2026-08-01", value: 4.0 },
      { date: "2026-09-01", value: 4.2 },
    ]);
    expect(out.M2SL).toEqual([{ date: "2026-09-01", value: 21000 }]);
  });

  it("drops points that cannot become a number", () => {
    // Otherwise NaN reaches the chart as a gap, with nothing saying a value
    // was present and unreadable.
    expect(byMetric([{ date: "2026-09-01T00:00:00", value: "n/a", metric_code: "DGS10" }]))
      .toEqual({});
  });

  it("survives an empty or absent payload", () => {
    expect(byMetric([])).toEqual({});
    expect(byMetric()).toEqual({});
    expect(byMetric(null)).toEqual({});
  });
});

describe("latestValue", () => {
  it("is the last observation, or null for a series that is not there", () => {
    expect(latestValue(monthly(3))).toBe(102);
    expect(latestValue([])).toBeNull();
    expect(latestValue(undefined)).toBeNull();
  });
});

describe("yearAgo", () => {
  it("finds the observation inside the 340-400 day window", () => {
    const series = monthly(24);
    const found = yearAgo(series);
    expect(found).toBeTruthy();
    const gap = (Date.parse(series[series.length - 1].date) - Date.parse(found.date)) / 86400000;
    expect(gap).toBeGreaterThanOrEqual(340);
    expect(gap).toBeLessThanOrEqual(400);
  });

  it("is null when the series does not reach back a year", () => {
    // Rather than reaching for the oldest point it has and reporting that as
    // a year-on-year change (F-0055).
    expect(yearAgo(monthly(6))).toBeNull();
  });

  it("is null for a missing series rather than throwing", () => {
    // The default parameter `series.length - 1` is evaluated BEFORE the body,
    // so the guard has to come first. The USA dashboard calls this for
    // CPIAUCSL, which is simply absent whenever that pipeline has not run,
    // and the tab render test caught it:
    //   TypeError: Cannot read properties of undefined (reading 'length')
    expect(() => yearAgo(undefined)).not.toThrow();
    expect(yearAgo(undefined)).toBeNull();
    expect(yearAgo(null)).toBeNull();
    expect(yearAgo([])).toBeNull();
  });
});

describe("yoyPercent", () => {
  it("is the percentage change against a year ago", () => {
    // 24 monthly points rising 1 a month: 123 now, 111 a year back.
    const series = monthly(24);
    expect(yoyPercent(series)).toBeCloseTo(((123 - 111) / 111) * 100, 10);
  });

  it("is null when there is no observation a year back", () => {
    expect(yoyPercent(monthly(6))).toBeNull();
    expect(yoyPercent(undefined)).toBeNull();
  });

  it("is null rather than Infinity when the year-ago value is zero", () => {
    const series = monthly(24, 0, 0);
    series[series.length - 1].value = 5;
    expect(yoyPercent(series)).toBeNull();
  });
});

describe("yoySeries", () => {
  it("F-0067: it looks back BY DATE, like the tile beside it", () => {
    // This used to be `m2Data[i - 12]` — right only while the series is
    // exactly monthly with no gaps — while the M2 stat card next to it used
    // a date window. Two methods for one number on one screen.
    const series = monthly(24);
    const rows = yoySeries(series);

    expect(rows.length).toBeGreaterThan(0);
    const last = rows[rows.length - 1];
    expect(last.date).toBe(series[series.length - 1].date);
    expect(last.growth).toBeCloseTo(yoyPercent(series), 10);
  });

  it("omits points with nothing to compare against, rather than emitting null", () => {
    const rows = yoySeries(monthly(24));
    expect(rows.every((r) => r.growth != null)).toBe(true);
    // The first eleven months have no year-ago point.
    expect(rows.length).toBeLessThan(24);
  });

  it("does not silently shift when the series has a gap", () => {
    // Drop one month out of the middle. The index-based version compared
    // against thirteen months back from that point onwards and said nothing.
    const full = monthly(24);
    const gapped = [...full.slice(0, 12), ...full.slice(13)];

    const fromFull = yoySeries(full);
    const fromGapped = yoySeries(gapped);
    const lastFull = fromFull[fromFull.length - 1];
    const lastGapped = fromGapped[fromGapped.length - 1];

    expect(lastGapped.date).toBe(lastFull.date);
    expect(lastGapped.growth).toBeCloseTo(lastFull.growth, 10);
  });

  it("is [] for a series that is not there", () => {
    expect(yoySeries(undefined)).toEqual([]);
    expect(yoySeries([])).toEqual([]);
  });
});
