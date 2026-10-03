// @vitest-environment jsdom
/**
 * D-0091 guard (c), G10a: the route resolves to the card.
 *
 * Red if App stops reading the hash, or CountryTab goes back to holding its
 * own selection (the URL and the card shown would disagree again).
 */
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App";

/** Shapes keyed by URL, as in pages.dom.test.jsx. Nothing reaches a network. */
function stubResponse(url) {
  if (url.includes("/holdings/cross-asset-stress")) {
    return { cross_asset_stress: [], treasury_only_stress: [], gold_only_stress: [], summary: {} };
  }
  if (url.includes("/holdings")) return { date: "2025-12-01", total_billions_usd: 0, holdings: [] };
  if (url.includes("/gold-reserves")) return { as_of: "2026-01-01", total_metric_tonnes: 0, country_count: 0, reserves: [] };
  if (url.includes("/stress/composite")) return { crisis: [], stressed: [], elevated: [], watch: [], summary: {} };
  if (url.includes("/cds/coverage")) return { covered: 0, missing: [] };
  if (url.includes("/cds")) return [];
  if (url.includes("/countries")) return [{ iso_code: "JPN", name: "Japan", region: "Asia" }];
  if (url.includes("/timeseries") || url.includes("/metric/")) return [];
  if (url.includes("/health")) return { status: "healthy" };
  if (url.includes("/stats")) return { timeseries_records: 1 };
  if (url.includes("/freshness")) return { counts: {}, sources: [] };
  return {};
}

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn((url) => Promise.resolve({
    ok: true, status: 200, statusText: "OK",
    json: () => Promise.resolve(stubResponse(String(url))),
    text: () => Promise.resolve(""),
  })));
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.location.hash = "";
});

async function go(hash) {
  await act(async () => {
    window.location.hash = hash;
    window.dispatchEvent(new HashChangeEvent("hashchange"));
  });
}

describe("G10a: #/country/<ISO3> opens that country's card", () => {
  it("#/country/JPN renders COUNTRY DETAIL for JPN", async () => {
    window.location.hash = "#/country/JPN";
    render(<App />);
    await waitFor(() => expect(screen.getByText("COUNTRY DETAIL")).toBeTruthy());
    expect(screen.getAllByText("JPN").length).toBeGreaterThan(0);
  });

  it("#/country/USA renders the USA dashboard (Card B)", async () => {
    window.location.hash = "#/country/USA";
    render(<App />);
    await waitFor(() => expect(screen.getByText(/Treasury Issuer/)).toBeTruthy());
    expect(screen.queryByText("COUNTRY DETAIL")).toBeNull();
  });

  it("a hashchange moves to another card without a remount", async () => {
    window.location.hash = "#/country/JPN";
    const { container } = render(<App />);
    await waitFor(() => expect(screen.getByText("COUNTRY DETAIL")).toBeTruthy());
    const shell = container.firstChild;

    await go("#/country/DEU");
    await waitFor(() => expect(screen.getAllByText("DEU").length).toBeGreaterThan(0));
    expect(screen.queryByText("JPN")).toBeNull();
    // Same App instance: the route is read, not re-mounted into.
    expect(container.firstChild).toBe(shell);
  });

  it("#/holdings shows the HOLDINGS tab", async () => {
    window.location.hash = "#/holdings";
    render(<App />);
    await waitFor(() => expect(screen.getByText(/FOREIGN TREASURY HOLDINGS/)).toBeTruthy());
    expect(screen.queryByText("COUNTRY DETAIL")).toBeNull();
  });

  it("#/country/RUSSIA shows the picker, not an empty card", async () => {
    window.location.hash = "#/country/RUSSIA";
    render(<App />);
    await waitFor(() => expect(screen.getByPlaceholderText(/Search country name/)).toBeTruthy());
    expect(screen.queryByText("COUNTRY DETAIL")).toBeNull();
  });

  it("a tab button writes the tab into the hash", async () => {
    window.location.hash = "";
    render(<App />);
    await act(async () => { screen.getByRole("button", { name: "GOLD" }).click(); });
    expect(window.location.hash).toBe("#/gold");
  });
});
