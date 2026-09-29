// @vitest-environment jsdom
/**
 * Render smoke tests for every tab — the net for ORDER-03 Part F.
 *
 * `F-0053` recorded that `App.jsx` had no coverage at all, and the order warns
 * that decomposing it is "the change most likely to break something silently".
 * These do not test behaviour. They assert something narrower and, for a
 * refactor, more useful: **each tab mounts without throwing, and renders
 * something.**
 *
 * That is exactly the class of breakage a move introduces — a missed import, a
 * helper left behind, a component referencing a constant that moved with it.
 * A typo in JSX that still compiles will not be caught by the build; it will be
 * caught here.
 *
 * Every network call is stubbed. Nothing reaches an API.
 *
 * These passed against App.jsx BEFORE the tabs were lifted into pages/,
 * and against pages/ after. Only the import paths below changed; every
 * assertion is identical, which is what makes them a net for the move
 * rather than a description of wherever the code ended up.
 */
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AboutTab } from "./pages/AboutTab";
import { AdminTab } from "./pages/AdminTab";
import { CDSTab } from "./pages/CDSTab";
import { CompositeTab } from "./pages/CompositeTab";
import { CountryTab } from "./pages/CountryTab";
import { CrossAssetTab } from "./pages/CrossAssetTab";
import { GoldReservesTab } from "./pages/GoldReservesTab";
import { HoldingsTab } from "./pages/HoldingsTab";
import { USADashboard } from "./pages/USADashboard";

/**
 * Shapes keyed loosely by URL. The tabs read different envelopes, and a stub
 * that returned `{}` for everything would exercise only each component's
 * empty-state branch — which is not where a refactor breaks.
 */
function stubResponse(url) {
  if (url.includes("/holdings/cross-asset-stress")) {
    return { cross_asset_stress: [], treasury_only_stress: [], gold_only_stress: [],
             summary: {}, spot_gold_rising: false, spot_gold_price: 4145,
             spot_gold_3m_pct: -9.1, as_of: "2026-09-28" };
  }
  if (url.includes("/holdings")) {
    return { date: "2025-12-01", total_billions_usd: 8558.9, holdings: [] };
  }
  if (url.includes("/gold-reserves")) {
    return { as_of: "2026-01-01", total_metric_tonnes: 36700, country_count: 0, reserves: [] };
  }
  if (url.includes("/stress/composite")) {
    return { crisis: [], stressed: [], elevated: [], watch: [], summary: {},
             as_of: "2026-09-28" };
  }
  if (url.includes("/cds/coverage")) return { covered: 0, missing: [] };
  if (url.includes("/cds")) return [];
  if (url.includes("/timeseries") || url.includes("/metric/")) return [];
  if (url.includes("/pipeline-logs")) return [];
  if (url.includes("/pipeline-status") || url.includes("/health")) {
    return { status: "healthy" };
  }
  if (url.includes("/stats")) {
    return { metrics: 87, countries: 105, timeseries_records: 64336,
             data_earliest: "1978-01-01T00:00:00", data_latest: "2026-09-29T00:00:00" };
  }
  if (url.includes("/freshness")) return { counts: {}, sources: [] };
  return {};
}

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn((url) =>
    Promise.resolve({
      ok: true,
      status: 200,
      statusText: "OK",
      json: () => Promise.resolve(stubResponse(String(url))),
      text: () => Promise.resolve(""),
    }),
  ));
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const TABS = [
  // USADashboard is the USA country view rendered inside COUNTRY, not the
  // MARKETS tab - MARKETS is composed inline in App.jsx from METRICS.
  ["USADashboard (inside COUNTRY)", USADashboard, {}],
  ["HOLDINGS", HoldingsTab, { onCountrySelect: () => {}, latestAll: {} }],
  ["CROSS-ASSET", CrossAssetTab, {}],
  ["GOLD", GoldReservesTab, { onCountrySelect: () => {}, latestAll: {} }],
  ["COMPOSITE", CompositeTab, { onCountrySelect: () => {} }],
  ["CDS", CDSTab, { onCountrySelect: () => {} }],
  ["COUNTRY", CountryTab, { onCountrySelect: () => {}, latestAll: {} }],
  ["ADMIN", AdminTab, {}],
  ["ABOUT", AboutTab, {}],
];

describe("every tab mounts", () => {
  for (const [label, Component, props] of TABS) {
    it(`${label} renders without throwing`, () => {
      const { container } = render(<Component {...props} />);
      expect(container.firstChild).not.toBeNull();
    });
  }
});

describe("the tabs that carry static content render it", () => {
  it("ABOUT names the project and the retired STRESS tab", () => {
    // D-0051 put the retired tab on ABOUT precisely so it would not be
    // forgotten. If a refactor drops that section, this says so.
    render(<AboutTab />);
    expect(screen.getByText(/Project Sentinel monitors/i)).toBeTruthy();
    expect(screen.getByText(/STRESS tab/i)).toBeTruthy();
  });

  it("ABOUT still lists data sources", () => {
    render(<AboutTab />);
    expect(screen.getByText(/DATA SOURCES/i)).toBeTruthy();
  });
});

describe("the stub is doing its job", () => {
  it("no tab reached a real network", () => {
    // Clause (c): if fetch were not stubbed these tests would pass anyway by
    // failing silently into catch blocks, and would prove nothing.
    render(<HoldingsTab onCountrySelect={() => {}} latestAll={{}} />);
    expect(fetch).toHaveBeenCalled();
    for (const call of fetch.mock.calls) {
      expect(String(call[0])).not.toMatch(/^https?:\/\/(?!localhost)/);
    }
  });
});

describe("F-0063: a failed load renders as a failure, not as an empty table", () => {
  /**
   * The five tabs used to do `.then(r => r.json())` with no `r.ok` check, so a
   * 500 carrying `{"detail": ...}` was installed as the resource. HOLDINGS and
   * GOLD then read `data.holdings || []` and rendered an empty table — a
   * server fault that looked like "no country holds US Treasuries".
   *
   * These assert the tab says it could not load. They go red against the
   * inline shape they replaced.
   */
  const FAILING = [
    ["HOLDINGS", HoldingsTab, { onCountrySelect: () => {}, latestAll: {} }, /TIC holdings/i],
    ["GOLD", GoldReservesTab, { onCountrySelect: () => {}, latestAll: {} }, /gold reserves/i],
    ["CROSS-ASSET", CrossAssetTab, {}, /cross-asset/i],
    ["COMPOSITE", CompositeTab, { onCountrySelect: () => {} }, /composite stress/i],
  ];

  for (const [label, Component, props, what] of FAILING) {
    it(`${label} says it could not load on a 500`, async () => {
      vi.stubGlobal("fetch", vi.fn(() => Promise.resolve({
        ok: false,
        status: 500,
        statusText: "Internal Server Error",
        json: () => Promise.resolve({ detail: "relation does not exist" }),
      })));

      render(<Component {...props} />);
      await waitFor(() => expect(screen.getByText(/Could not load/i)).toBeTruthy());
      expect(screen.getByText(what)).toBeTruthy();
      expect(screen.getByText(/500/)).toBeTruthy();
    });
  }

  it("and an empty-but-successful response still reads as empty, not as a failure", async () => {
    // The distinction this whole finding is about: zero rows is a fact about
    // the world, and it must not be dressed up as a fault either.
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve({
      ok: true,
      status: 200,
      statusText: "OK",
      json: () => Promise.resolve({ date: "2025-12-01", total_billions_usd: 0, holdings: [] }),
    })));

    render(<HoldingsTab onCountrySelect={() => {}} latestAll={{}} />);
    await waitFor(() => expect(screen.queryByText(/loading/i)).toBeNull());
    expect(screen.queryByText(/Could not load/i)).toBeNull();
  });
});
