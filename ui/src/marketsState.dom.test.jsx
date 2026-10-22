// @vitest-environment jsdom
/**
 * Sentinel D-0111 (vault:D-0057) review MUST-FIX: MARKETS keeps its chart
 * state across tab changes, as on master be64218.
 *
 * Moving the MARKETS block into pages/MarketsTab.jsx moved the series
 * selection, range and %-change state with it. MarketsTab unmounts when the
 * user opens another tab, so coming back reset all three. On master that
 * state lives in App and survives. This test toggles a series, a range and
 * % CHANGE, visits FOREIGN-BONDS, returns, and expects the same controls.
 */
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App";

/** Two deterministic observations per requested code, ~60 days apart. */
function timeseries(url) {
  const m = /metric_codes=([^&]*)/.exec(url);
  const codes = m ? decodeURIComponent(m[1]).split(",").filter(Boolean) : [];
  const out = [];
  codes.forEach((code, i) => {
    const base = 1 + i * 0.37;
    out.push({ metric_code: code, date: "2026-08-03T00:00:00", value: Number(base.toFixed(4)) });
    out.push({ metric_code: code, date: "2026-09-02T00:00:00", value: Number((base + 0.11).toFixed(4)) });
    out.push({ metric_code: code, date: "2026-10-02T00:00:00", value: Number((base + 0.05).toFixed(4)) });
  });
  return out;
}

function stubResponse(url) {
  if (url.includes("/timeseries")) return timeseries(url);
  if (url.includes("/health")) return { status: "healthy" };
  if (url.includes("/stats")) {
    return { timeseries_records: 64336, data_latest: "2026-10-02T00:00:00" };
  }
  if (url.includes("/freshness")) {
    const src = (key, status) => ({ key, label: key, status, age_days: 1, max_age_days: 5, note: "n" });
    return {
      counts: {},
      sources: [src("treasury_yields", "ok"), src("oil", "ok"), src("dollar_index", "stale"), src("gold_price", "ok")],
    };
  }
  return {};
}

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn((url) => Promise.resolve({
    ok: true, status: 200, statusText: "OK",
    json: () => Promise.resolve(stubResponse(String(url))),
    text: () => Promise.resolve(""),
  })));
  window.location.hash = "";
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.location.hash = "";
});

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn((url) => Promise.resolve({
    ok: true, status: 200, statusText: "OK",
    json: () => Promise.resolve(stubResponse(String(url))),
    text: () => Promise.resolve(""),
  })));
  window.location.hash = "";
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.location.hash = "";
});

/** The chart control bar: series toggles, % CHANGE and the range buttons. */
function controls() {
  return screen.getByText("% CHANGE").parentElement.parentElement.outerHTML;
}

function tabButton(label) {
  return screen.getAllByRole("button").find((b) => b.textContent === label);
}

describe("MARKETS keeps series, range and % CHANGE across a tab change", () => {
  it("toggle a series and a range, visit FOREIGN-BONDS, come back: unchanged", async () => {
    render(<App />);
    await waitFor(() => expect(screen.getByText("% CHANGE")).toBeTruthy());
    const initial = controls();

    fireEvent.click(screen.getByRole("button", { name: "30Y Treasury" }));
    fireEvent.click(screen.getByRole("button", { name: "2Y" }));
    fireEvent.click(screen.getByText("% CHANGE"));
    const chosen = controls();
    expect(chosen).not.toBe(initial);

    await act(async () => { fireEvent.click(tabButton("FOREIGN-BONDS")); });
    await waitFor(() => expect(screen.queryByText("% CHANGE")).toBeTruthy());
    expect(screen.queryByRole("button", { name: "30Y Treasury" })).toBeNull();

    await act(async () => { fireEvent.click(tabButton("MARKETS")); });
    await waitFor(() => expect(screen.getByRole("button", { name: "30Y Treasury" })).toBeTruthy());
    expect(controls()).toBe(chosen);
  });
});

describe("D-0113: opening and closing a country card does not reset MARKETS (#97 class)", () => {
  it("toggle MARKETS state, open DEU's card, come back: unchanged", async () => {
    render(<App />);
    await waitFor(() => expect(screen.getByText("% CHANGE")).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: "30Y Treasury" }));
    fireEvent.click(screen.getByText("% CHANGE"));
    const chosen = controls();

    await act(async () => {
      window.location.hash = "#/country/DEU";
      window.dispatchEvent(new HashChangeEvent("hashchange"));
    });
    await waitFor(() => expect(screen.getByText("COUNTRY DETAIL")).toBeTruthy());
    await waitFor(() => expect(screen.getByTestId("country-bond-chart")).toBeTruthy());

    await act(async () => { fireEvent.click(tabButton("MARKETS")); });
    await waitFor(() => expect(screen.getByRole("button", { name: "30Y Treasury" })).toBeTruthy());
    expect(controls()).toBe(chosen);
  });
});
