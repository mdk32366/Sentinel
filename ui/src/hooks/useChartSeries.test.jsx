// @vitest-environment jsdom
import { renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { normalizeRows, useChartSeries } from "./useChartSeries";

describe("normalizeRows", () => {
  const rows = [
    { date: "2026-09-01", DGS10: 4.0, DGS2: 3.0 },
    { date: "2026-09-02", DGS10: 4.4, DGS2: 3.3 },
  ];

  it("rebases each code to its own first observation", () => {
    const out = normalizeRows(rows, ["DGS10", "DGS2"]);
    expect(out[0]).toEqual({ date: "2026-09-01", DGS10: 0, DGS2: 0 });
    // 4.4/4.0 is 10.000000000000009 in binary floating point. The chart
    // formats to one decimal, so the assertion is on the number, not on its
    // representation.
    expect(out[1].DGS10).toBeCloseTo(10, 10);
    expect(out[1].DGS2).toBeCloseTo(10, 10);
  });

  it("takes the first NON-NULL observation as the base", () => {
    const withHole = [
      { date: "2026-09-01", DGS10: null },
      { date: "2026-09-02", DGS10: 4.0 },
      { date: "2026-09-03", DGS10: 4.2 },
    ];
    const out = normalizeRows(withHole, ["DGS10"]);
    expect(out[0]).toEqual({ date: "2026-09-01" });
    expect(out[1].DGS10).toBe(0);
    expect(out[2].DGS10).toBeCloseTo(5, 10);
  });

  it("drops a series whose base is zero rather than dividing by it", () => {
    // FEDFUNDS sat at 0.00 through 2020-2021. Rebasing on it is a division by
    // zero, and Infinity plotted against yields makes the chart unreadable.
    const out = normalizeRows(
      [{ date: "2026-09-01", FEDFUNDS: 0 }, { date: "2026-09-02", FEDFUNDS: 0.25 }],
      ["FEDFUNDS"],
    );
    expect(out.every((r) => r.FEDFUNDS === undefined)).toBe(true);
  });

  it("keeps the date on every row so the axis does not collapse", () => {
    expect(normalizeRows(rows, ["DGS10"]).map((r) => r.date))
      .toEqual(["2026-09-01", "2026-09-02"]);
  });

  it("returns an empty input untouched", () => {
    expect(normalizeRows([], ["DGS10"])).toEqual([]);
  });
});

describe("useChartSeries", () => {
  const RANGE = { label: "1Y", days: 365 };

  const okStub = (raw) => vi.fn(() => Promise.resolve({
    ok: true, status: 200, statusText: "OK", json: () => Promise.resolve(raw),
  }));

  beforeEach(() => vi.stubGlobal("fetch", okStub([])));
  afterEach(() => vi.unstubAllGlobals());

  it("pivots the API's flat list into chart rows", async () => {
    vi.stubGlobal("fetch", okStub([
      { date: "2026-09-01T00:00:00", value: 4.0, metric_code: "DGS10" },
      { date: "2026-09-01T00:00:00", value: 3.0, metric_code: "DGS2" },
    ]));

    const { result } = renderHook(() => useChartSeries({
      activeMetrics: ["DGS10", "DGS2"], range: RANGE, normalized: false,
    }));

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.rows).toEqual([{ date: "2026-09-01", DGS10: 4.0, DGS2: 3.0 }]);
  });

  it("does not call the API when nothing is selected", async () => {
    const fetchStub = okStub([]);
    vi.stubGlobal("fetch", fetchStub);

    const { result } = renderHook(() => useChartSeries({
      activeMetrics: [], range: RANGE, normalized: false,
    }));

    await waitFor(() => expect(result.current.rows).toEqual([]));
    expect(fetchStub).not.toHaveBeenCalled();
  });

  it("refetches when the range changes", async () => {
    const fetchStub = okStub([]);
    vi.stubGlobal("fetch", fetchStub);

    const { rerender } = renderHook(
      ({ range }) => useChartSeries({ activeMetrics: ["DGS10"], range, normalized: false }),
      { initialProps: { range: RANGE } },
    );
    await waitFor(() => expect(fetchStub).toHaveBeenCalledTimes(1));

    rerender({ range: { label: "5Y", days: 1825 } });
    await waitFor(() => expect(fetchStub).toHaveBeenCalledTimes(2));
  });

  it("F-0065: a caller passing fresh literals each render does not loop", async () => {
    // The version that listed [activeMetrics, range] as dependencies re-armed
    // its effect on every render, because a new array is never === the old
    // one. It set state, which rendered, which made a new array. The first
    // run of this file killed the worker outright:
    //
    //     Worker exited unexpectedly with exit code 134
    //
    // App.jsx holds both in useState, so production never tripped it. That is
    // precisely what makes it worth a test: a hook whose correctness rests on
    // the caller's memoisation is a trap with no signal.
    const fetchStub = okStub([]);
    vi.stubGlobal("fetch", fetchStub);

    const { rerender, result } = renderHook(() => useChartSeries({
      activeMetrics: ["DGS10", "DGS2"],      // a NEW array every render
      range: { label: "1Y", days: 365 },     // a NEW object every render
      normalized: false,
    }));

    await waitFor(() => expect(result.current.loading).toBe(false));
    rerender();
    rerender();
    rerender();
    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(fetchStub).toHaveBeenCalledTimes(1);
  });

  it("a failed request empties the chart rather than leaving the last range on screen", async () => {
    // Otherwise switching 1Y -> 5Y against a broken API leaves the 1Y data
    // under a 5Y label, which is a wrong chart rather than a missing one.
    const errors = vi.spyOn(console, "error").mockImplementation(() => {});
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve({
      ok: false, status: 500, statusText: "Internal Server Error",
      json: () => Promise.resolve({ detail: "boom" }),
    })));

    const { result } = renderHook(() => useChartSeries({
      activeMetrics: ["DGS10"], range: RANGE, normalized: false,
    }));

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.rows).toEqual([]);
    expect(errors).toHaveBeenCalled();
    errors.mockRestore();
  });
});
