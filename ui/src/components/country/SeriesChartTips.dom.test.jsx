// @vitest-environment jsdom
/**
 * T-0073b (D-0073: the country panel explains itself). The four chart panels
 * under the stress contribution block each carry a title tooltip saying what
 * the number is, its source, its cadence and its units. A SeriesChart given
 * no `tip` renders exactly as before.
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CountryDetail } from "../CountryDetail";
import { SeriesChart } from "./SeriesChart";

beforeEach(() => {
  vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });
  vi.stubGlobal("fetch", vi.fn((url) => {
    const href = String(url);
    const body = href.includes("/gold-reserves/") ? { country_name: "Japan", data_points: 2, reserves: [
        { date: "2026-07-01", metric_tonnes: 846 }, { date: "2026-08-01", metric_tonnes: 846 }] }
      : href.includes("/holdings/") ? { country_name: "Japan", data_points: 2, holdings: [
        { date: "2026-07-01", holdings_billions_usd: 1100 }, { date: "2026-08-01", holdings_billions_usd: 1110 }] }
      : href.includes("/cds") ? { "5Y": { value: 30 }, history: [{ date: "2026-10-20", value: 30 }, { date: "2026-10-21", value: 31 }] }
      : href.includes("/timeseries") ? [{ date: "2026-07-01", value: "1200000" }, { date: "2026-08-01", value: "1210000" }]
      : [];
    return Promise.resolve({ ok: true, status: 200, statusText: "OK", json: () => Promise.resolve(body) });
  }));
});

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

const PANELS = [
  [/^TREASURY HOLDINGS/, [/TIC/, /monthly/i, /billions of US dollars/]],
  [/^GOLD RESERVES/, [/IMF/, /IRFCL/, /monthly/i, /metric tonnes/]],
  [/^5Y SOVEREIGN CDS/, [/World Government Bonds/, /daily/i, /basis points/]],
  [/^TOTAL RESERVES EX-GOLD/, [/IMF International Financial Statistics/, /FRED/, /monthly/i, /millions of US dollars/]],
];

describe("country chart panels: title tooltips", () => {
  it.each(PANELS)("%s exposes its tooltip text on focus", async (title, phrases) => {
    render(<CountryDetail iso="JPN" latestAll={{}} />);
    const label = await waitFor(() => screen.getByText(title));
    const anchor = label.closest("[data-tip]");
    expect(anchor).toBeTruthy();
    expect(anchor.getAttribute("tabindex")).toBe("0");
    fireEvent.focus(anchor);
    const bubble = await waitFor(() => screen.getByRole("tooltip"));
    for (const p of phrases) expect(bubble.textContent).toMatch(p);
    fireEvent.blur(anchor);
    expect(screen.queryByRole("tooltip")).toBeNull();
  });

  it("a SeriesChart with no tip is unchanged: plain title, no tip anchor, not focusable", () => {
    const { container } = render(
      <SeriesChart title="PLAIN" rows={[{ date: "2026-01-01", v: 1 }]} dataKey="v" stroke="#fff"
        tickFormat={String} tooltipFormat={String} tooltipLabel="v" />,
    );
    const label = screen.getByText("PLAIN");
    expect(label.closest("[data-tip]")).toBeNull();
    expect(container.querySelector("[data-tip]")).toBeNull();
    expect(container.querySelector("[tabindex]")).toBeNull();
  });
});
