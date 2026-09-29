// @vitest-environment jsdom
import { renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { METRICS, SOVEREIGN_YIELD_CODES } from "../lib/constants";
import { CHANGE_WINDOW_DAYS, TRACKED_CODES, useMarketSeries } from "./useMarketSeries";

afterEach(() => vi.unstubAllGlobals());

const stub = (raw) => vi.fn(() => Promise.resolve({
  ok: true, status: 200, statusText: "OK", json: () => Promise.resolve(raw),
}));

/** A daily DGS10 run of `n` days ending 2026-09-28, rising 0.01 a day. */
const dailyRun = (n, code = "DGS10") =>
  Array.from({ length: n }, (_, i) => {
    const d = new Date("2026-09-28T00:00:00Z");
    d.setUTCDate(d.getUTCDate() - (n - 1 - i));
    return { date: `${d.toISOString().slice(0, 10)}T00:00:00`, value: 4 + i / 100, metric_code: code };
  });

describe("TRACKED_CODES", () => {
  it("is every ticker metric plus every sovereign yield, with no duplicates", () => {
    expect(TRACKED_CODES).toHaveLength(METRICS.length + Object.keys(SOVEREIGN_YIELD_CODES).length);
    expect(new Set(TRACKED_CODES).size).toBe(TRACKED_CODES.length);
  });

  it("includes GOLD_SPOT_USD, which D-0053 put on the ticker", () => {
    expect(TRACKED_CODES).toContain("GOLD_SPOT_USD");
  });
});

describe("useMarketSeries", () => {
  it("asks for every tracked code in one request", async () => {
    const fetchStub = stub([]);
    vi.stubGlobal("fetch", fetchStub);

    renderHook(() => useMarketSeries());
    await waitFor(() => expect(fetchStub).toHaveBeenCalledTimes(1));

    const url = String(fetchStub.mock.calls[0][0]);
    for (const code of TRACKED_CODES) expect(url).toContain(code);
  });

  it("returns the latest value per code", async () => {
    vi.stubGlobal("fetch", stub(dailyRun(40)));
    const { result } = renderHook(() => useMarketSeries());

    await waitFor(() => expect(result.current.latest.DGS10).toBeDefined());
    expect(result.current.latest.DGS10).toBeCloseTo(4.39, 10);
  });

  it("F-0055: prior is found by DATE and reports the gap it actually found", async () => {
    // 40 daily points, so an observation 30 days back exists and is exactly
    // 30 days back. The defect this replaced returned points.at(-2) - one day.
    vi.stubGlobal("fetch", stub(dailyRun(40)));
    const { result } = renderHook(() => useMarketSeries());

    await waitFor(() => expect(result.current.prior.DGS10).toBeDefined());
    expect(result.current.prior.DGS10.actualDays).toBe(CHANGE_WINDOW_DAYS);
    expect(result.current.prior.DGS10.actualDays).not.toBe(1);
  });

  it("omits prior entirely when the series is too short to look back", async () => {
    // Rather than quietly comparing against the oldest point it has and
    // labelling that "vs 30d".
    vi.stubGlobal("fetch", stub(dailyRun(5)));
    const { result } = renderHook(() => useMarketSeries());

    await waitFor(() => expect(result.current.latest.DGS10).toBeDefined());
    expect(result.current.prior.DGS10).toBeUndefined();
  });

  it("a failed request leaves the ticker empty instead of throwing", async () => {
    // The ticker is furniture. It must not take the open tab with it.
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve({
      ok: false, status: 503, statusText: "Service Unavailable",
      json: () => Promise.resolve({}),
    })));
    const { result } = renderHook(() => useMarketSeries());

    await waitFor(() => expect(result.current.latest).toEqual({}));
    expect(result.current.prior).toEqual({});
  });

  it("always returns usable shapes, so a caller can index before the load lands", async () => {
    vi.stubGlobal("fetch", stub([]));
    const { result } = renderHook(() => useMarketSeries());

    expect(result.current.latest).toEqual({});
    expect(result.current.prior).toEqual({});
    expect(() => result.current.latest.DGS10).not.toThrow();
  });
});
