// @vitest-environment jsdom
/**
 * F-0113 - the CROSS-ASSET tab's exited countries, as a reader meets them.
 *
 * The "Exited Position" tile added up the cross-asset and Treasury-only lists,
 * which between them hold only the exited countries selling gold into a rising
 * price. The EXITED view showed the gold-only list. And an exited country not
 * selling gold was in no list, so neither ALL nor EXITED could show it.
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CrossAssetTab } from "./CrossAssetTab";

function row(iso, name, over = {}) {
  return {
    country_iso: iso, country_name: name, region: null, tic_holdings_bn: 50, tic_mom_pct: -1,
    tic_consecutive_months: 1, no_tic_holdings: false, tic_state: "reported",
    tic_last_reported_bn: null, gold_tonnes: 100, gold_mom_pct: 0, gold_consecutive_months: 0,
    treseg_signal: "NO_DATA", treseg_trend_pct: null, treseg_latest_bn: null,
    spot_gold_price: 4000, spot_gold_3m_pct: 1, spot_gold_rising: false,
    selling_treasuries: false, selling_gold: false, cross_asset_stress: false,
    divergence_signal: false, signal_tier: "T_ONLY", score_before_multiplier: 50,
    multiplier: 1, stress_score: 50, alert: false, tic_as_of: "2026-07", gold_as_of: "2026-07",
    ...over,
  };
}

const exited = (iso, name, over) => row(iso, name, {
  no_tic_holdings: true, tic_state: "exited", tic_holdings_bn: 0, signal_tier: "EXITED", alert: true, ...over,
});

const HOLDS = exited("AAA", "Alphaland");                                   // not selling gold
const SELLS = exited("BBB", "Bravoland", { selling_gold: true });           // gold-only list
const DIVERGES = exited("CCC", "Charlieland", { selling_gold: true, divergence_signal: true });
const TONLY = row("DDD", "Deltaland", { selling_treasuries: true });
const GOLD_ONLY_NOT_EXITED = row("EEE", "Echoland", { selling_gold: true });

const PAYLOAD = {
  cross_asset_stress: [DIVERGES],
  treasury_only_stress: [TONLY],
  gold_only_stress: [SELLS, GOLD_ONLY_NOT_EXITED],
  exited: [HOLDS, SELLS, DIVERGES],
  summary: { cross_asset_stressed: 1, treasury_only: 1, gold_only: 2, exited: 3, total_stressed: 5 },
  spot_gold_rising: false, spot_gold_price: 4000, spot_gold_3m_pct: 1, as_of: "2026-07",
};

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn((url) => Promise.resolve({
    ok: true, status: 200, statusText: "OK",
    json: () => Promise.resolve(String(url).includes("/freshness") ? { counts: {}, sources: [] } : PAYLOAD),
  })));
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

async function open() {
  render(<CrossAssetTab />);
  await screen.findByText("Exited Position");
}

describe("the reader can", () => {
  it("count every exited country on the tile", async () => {
    await open();
    const tile = screen.getByText("Exited Position").closest("div[style*='flex: 1 1']") ?? screen.getByText("Exited Position").parentElement.parentElement;
    expect(tile.textContent).toContain("3");
  });

  it("see exactly the exited countries under EXITED", async () => {
    await open();
    fireEvent.click(screen.getByRole("button", { name: "🚨 EXITED" }));
    await waitFor(() => expect(screen.queryByText("Alphaland")).not.toBeNull());
    expect(screen.getByText("Bravoland")).toBeTruthy();
    expect(screen.getByText("Charlieland")).toBeTruthy();
    expect(screen.queryByText("Echoland")).toBeNull();   // gold-only, not exited
    expect(screen.queryByText("Deltaland")).toBeNull();
  });

  it("find an exited country that is not selling gold under ALL", async () => {
    await open();
    expect(screen.getByText("Alphaland")).toBeTruthy();
    expect(screen.getAllByText("Bravoland")).toHaveLength(1);   // listed once, not twice
  });
});
