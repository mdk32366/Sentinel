// @vitest-environment jsdom
/**
 * `F-0064` — the sovereign spread tile depended on which tab opened the panel.
 *
 * `CountryDetail` reads `latestAll[SOVEREIGN_YIELD_CODES[iso]]` and
 * `latestAll["DGS10"]`. Three call sites passed three different things:
 * COUNTRY passed the flat `{code: value}` map, HOLDINGS passed the
 * `{latest, prior}` wrapper and unwrapped it itself, and GOLD passed a
 * hardcoded `{}`.
 *
 * So opening Japan from GOLD showed "Spread vs US 10Y —", while opening the
 * same country from COUNTRY showed "+37bps". A dash, not an error: exactly
 * what a country FRED genuinely does not cover looks like.
 */
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SOVEREIGN_YIELD_CODES } from "../lib/constants";
import { CountryDetail } from "./CountryDetail";
import { GoldReservesTab } from "../pages/GoldReservesTab";

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn((url) => {
    const href = String(url);
    const body = href.includes("/gold-reserves/") ? { country_name: "Japan", reserves: [] }
      : href.includes("/gold-reserves") ? {
          as_of: "2026-01-01", total_metric_tonnes: 36700, country_count: 1,
          reserves: [{ country_code: "JPN", country_name: "Japan", metric_tonnes: 846, percent_of_total: 2.3 }],
        }
      : href.includes("/holdings/") ? { country_name: "Japan", holdings: [] }
      : href.includes("/cds") ? {}
      : [];
    return Promise.resolve({ ok: true, status: 200, statusText: "OK", json: () => Promise.resolve(body) });
  }));
});

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

/** JPN at 1.05% against a US 10Y of 4.20% is a spread of -315bps. */
const JPN_YIELDS = { [SOVEREIGN_YIELD_CODES.JPN]: 1.05, DGS10: 4.2 };

describe("CountryDetail: the spread tile", () => {
  it("prints bps when it is given the flat latest-value map", async () => {
    render(<CountryDetail iso="JPN" latestAll={JPN_YIELDS} />);
    await waitFor(() => expect(screen.getByText("-315bps")).toBeTruthy());
  });

  it("prints a dash when the country genuinely has no FRED yield series", async () => {
    // CHN has no SOVEREIGN_YIELD_CODES entry. The dash is correct here, and
    // this is the case F-0064's dash was indistinguishable from.
    expect(SOVEREIGN_YIELD_CODES.CHN).toBeUndefined();
    render(<CountryDetail iso="CHN" latestAll={{ DGS10: 4.2 }} />);
    await waitFor(() => expect(screen.getByText("Spread vs US 10Y")).toBeTruthy());
    expect(screen.queryByText(/bps$/)).toBeNull();
  });

  it("prints a dash when handed the WRAPPER shape instead of the flat map", async () => {
    // This is what HOLDINGS used to pass before it unwrapped, and what any
    // new call site would naturally pass given the prop's name. It yields a
    // blank tile rather than an error, which is why the prop now has one
    // shape at every call site.
    render(<CountryDetail iso="JPN" latestAll={{ latest: JPN_YIELDS, prior: {} }} />);
    await waitFor(() => expect(screen.getByText("Spread vs US 10Y")).toBeTruthy());
    expect(screen.queryByText("-315bps")).toBeNull();
  });
});

describe("GOLD threads the yields through to the country panel", () => {
  it("a country opened from GOLD gets the same spread as one opened from COUNTRY", async () => {
    // The regression test for F-0064 proper: GoldReservesTab passed {}.
    const { container } = render(<GoldReservesTab onCountrySelect={() => {}} latestAll={JPN_YIELDS} />);
    await waitFor(() => expect(screen.getByText("Japan")).toBeTruthy());

    const row = [...container.querySelectorAll("tr")].find((tr) => tr.textContent.includes("Japan"));
    expect(row).toBeTruthy();
    row.click();

    await waitFor(() => expect(screen.getByText("-315bps")).toBeTruthy());
  });

  it("D-0091: the NAME in that row opens the card, and does not open the inline panel", async () => {
    // G11. The row keeps the inline history panel (F-0064, the test above);
    // the country name inside it is a link to #/country/<ISO3>. The link
    // stops propagation, so the two never both fire.
    window.location.hash = "";
    const { container } = render(<GoldReservesTab latestAll={JPN_YIELDS} />);
    await waitFor(() => expect(screen.getByText("Japan")).toBeTruthy());

    const row = [...container.querySelectorAll("tr")].find((tr) => tr.textContent.includes("Japan"));
    const link = row.querySelector('a[href="#/country/JPN"]');
    expect(link).toBeTruthy();
    link.click();

    await waitFor(() => expect(window.location.hash).toBe("#/country/JPN"));
    expect(screen.queryByText("COUNTRY DETAIL")).toBeNull();
    expect(screen.queryByText("-315bps")).toBeNull();
    window.location.hash = "";
  });
});

// ── Sentinel D-0113: the Foreign Bonds chart, embedded per country ──────────
import { fireEvent } from "@testing-library/react";
import { fbCardCodes } from "../lib/constants";

const D0113_NOW = new Date("2026-10-22T12:00:00Z");
function fbTimeseries(href) {
  const m = /metric_codes=([^&]*)/.exec(href);
  const codes = m ? decodeURIComponent(m[1]).split(",").filter(Boolean) : [];
  return codes.flatMap((code, i) => [
    { metric_code: code, date: "2026-10-20T00:00:00", value: 2 + i * 0.2 },
    { metric_code: code, date: "2026-10-21T00:00:00", value: 2.05 + i * 0.2 },
  ]);
}

describe("D-0113: the country card embeds the Foreign Bonds chart", () => {
  let requested;
  beforeEach(() => {
    requested = [];
    const base = globalThis.fetch;
    vi.stubGlobal("fetch", vi.fn((url) => {
      const href = String(url);
      if (href.includes("/timeseries")) {
        requested.push(href);
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(fbTimeseries(href)) });
      }
      return base(url);
    }));
  });

  for (const [iso, cc] of [["DEU", "DE"], ["GBR", "GB"], ["JPN", "JP"], ["FRA", "FR"]]) {
    it(`${iso}: renders the chart with its five ${cc} FB codes`, async () => {
      render(<CountryDetail iso={iso} latestAll={{ DGS10: 4.2 }} now={D0113_NOW} />);
      await waitFor(() => expect(screen.getByTestId("country-bond-chart")).toBeTruthy());
      for (const t of [2, 5, 7, 10, 30]) {
        expect(screen.getByRole("button", { name: `${cc} ${t}Y` })).toBeTruthy();
      }
      expect(requested.some((h) => fbCardCodes(iso).every((c) => decodeURIComponent(h).includes(c)))).toBe(true);
    });
  }

  it("% CHANGE works on the card", async () => {
    render(<CountryDetail iso="DEU" latestAll={{ DGS10: 4.2 }} now={D0113_NOW} />);
    await waitFor(() => expect(screen.getByText("% CHANGE")).toBeTruthy());
    const btn = screen.getByText("% CHANGE");
    expect(btn.getAttribute("aria-pressed")).toBe("false");
    fireEvent.click(btn);
    expect(screen.getByText("% CHANGE").getAttribute("aria-pressed")).toBe("true");
  });

  it("BEL has no chart and no FB request (ITA joined in D-0116)", async () => {
    render(<CountryDetail iso="BEL" latestAll={{ DGS10: 4.2 }} now={D0113_NOW} />);
    await waitFor(() => expect(screen.getByText("Spread vs US 10Y")).toBeTruthy());
    expect(screen.queryByTestId("country-bond-chart")).toBeNull();
    expect(screen.queryByText("% CHANGE")).toBeNull();
    expect(requested.some((h) => h.includes("FB_"))).toBe(false);
  });

  it("chart state is per country: % CHANGE on DEU does not leak to GBR", async () => {
    const { rerender } = render(<CountryDetail iso="DEU" latestAll={{ DGS10: 4.2 }} now={D0113_NOW} />);
    await waitFor(() => expect(screen.getByText("% CHANGE")).toBeTruthy());
    fireEvent.click(screen.getByText("% CHANGE"));
    expect(screen.getByText("% CHANGE").getAttribute("aria-pressed")).toBe("true");
    rerender(<CountryDetail iso="GBR" latestAll={{ DGS10: 4.2 }} now={D0113_NOW} />);
    await waitFor(() => expect(screen.getByRole("button", { name: "GB 10Y" })).toBeTruthy());
    expect(screen.getByText("% CHANGE").getAttribute("aria-pressed")).toBe("false");
  });
});
