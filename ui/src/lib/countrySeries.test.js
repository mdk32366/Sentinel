import { describe, expect, it } from "vitest";

import { goldSeries, momChange, reservesSeries, ticSeries } from "./countrySeries";

describe("ticSeries", () => {
  it("truncates the timestamp and keys the value as `holdings`", () => {
    expect(ticSeries({ holdings: [{ date: "2026-08-01T00:00:00", holdings_billions_usd: 1122.4 }] }))
      .toEqual([{ date: "2026-08-01", holdings: 1122.4 }]);
  });

  it("returns [] for a missing envelope rather than throwing", () => {
    // /holdings/{iso} fails soft to null for a country with no TIC row, and
    // "no TIC row" is the ordinary case, not a fault.
    expect(ticSeries(null)).toEqual([]);
    expect(ticSeries({})).toEqual([]);
    expect(ticSeries({ holdings: [] })).toEqual([]);
  });
});

describe("goldSeries", () => {
  it("truncates the timestamp and keys the value as `tonnes`", () => {
    expect(goldSeries({ reserves: [{ date: "2026-06-30T00:00:00", metric_tonnes: 846.2 }] }))
      .toEqual([{ date: "2026-06-30", tonnes: 846.2 }]);
  });

  it("returns [] for a missing envelope", () => {
    expect(goldSeries(null)).toEqual([]);
  });
});

describe("reservesSeries", () => {
  it("parses the string values the /timeseries endpoint returns", () => {
    // The reserves-ex-gold series arrives as strings.
    expect(reservesSeries([{ date: "2026-07-01T00:00:00", value: "1234567.89" }]))
      .toEqual([{ date: "2026-07-01", value: 1234567.89 }]);
  });

  it("drops a value that does not parse rather than putting NaN on the chart", () => {
    // NaN renders as a gap, with nothing to say a value was present and
    // unreadable.
    const rows = reservesSeries([
      { date: "2026-07-01T00:00:00", value: "1000" },
      { date: "2026-08-01T00:00:00", value: "n/a" },
      { date: "2026-09-01T00:00:00", value: null },
    ]);
    expect(rows).toEqual([{ date: "2026-07-01", value: 1000 }]);
  });

  it("returns [] when the endpoint answered with anything but an array", () => {
    expect(reservesSeries(null)).toEqual([]);
    expect(reservesSeries({ detail: "not found" })).toEqual([]);
  });
});

describe("momChange", () => {
  it("is the percentage change between the last two observations", () => {
    expect(momChange([
      { date: "2026-07-01", holdings: 1000 },
      { date: "2026-08-01", holdings: 1100 },
    ])).toBeCloseTo(10, 10);
  });

  it("is signed the way a decline should be", () => {
    expect(momChange([
      { date: "2026-07-01", holdings: 1000 },
      { date: "2026-08-01", holdings: 900 },
    ])).toBeCloseTo(-10, 10);
  });

  it("F-0066: a country re-entering from a fully exited position is null, not Infinity", () => {
    // The inline version divided by the earlier observation unguarded, and
    // the card prints `${v.toFixed(2)}%`. A country that held zero Treasuries
    // and then bought some rendered as "+Infinity%" — which is exactly the
    // event this application exists to notice, displayed as a glitch.
    const reentry = momChange([
      { date: "2026-07-01", holdings: 0 },
      { date: "2026-08-01", holdings: 12.5 },
    ]);
    expect(reentry).toBeNull();
    expect(Number.isFinite(reentry)).toBe(false);
  });

  it("is null when there is nothing to compare against", () => {
    expect(momChange([])).toBeNull();
    expect(momChange([{ date: "2026-08-01", holdings: 100 }])).toBeNull();
    expect(momChange(null)).toBeNull();
  });

  it("is null when either observation is missing its value", () => {
    expect(momChange([
      { date: "2026-07-01", holdings: null },
      { date: "2026-08-01", holdings: 100 },
    ])).toBeNull();
  });
});
