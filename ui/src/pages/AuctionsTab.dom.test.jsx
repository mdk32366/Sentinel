// @vitest-environment jsdom
/**
 * ORDER auction-demand §8b — the Auction Demand panel, as the user meets it.
 *
 * Each case is a step a reader takes. Every request is stubbed; the payloads
 * are the API's own shape (api/schemas.py AuctionRow), with values taken from
 * production on 2026-10-08 and two seeded defects: a `mismatch` row and a row
 * whose recomputed bid-to-cover is missing.
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AuctionsTab } from "./AuctionsTab";

function row(term, group, auction_date, over = {}) {
  return {
    cusip: `C${term}${auction_date}`, auction_date, security_type: term.endsWith("W") ? "Bill" : "Note",
    security_term: group, original_security_term: group, term_group: group, term,
    issue_date: null, maturity_date: null, reopening: false,
    offering_amt: 77e9, total_tendered: 218768419200, total_accepted: 83455419200,
    soma_tendered: 6455051600, soma_accepted: 6455051600, comp_accepted: 74980149000,
    b2c_reported: 2.76, b2c_recomputed: 2.7573, b2c_check: "ok", identity_check: "ok",
    b2c_z: -0.4, b2c_z_window: 26, b2c_z_reason: null,
    b2c_window_mean: 2.8, b2c_window_sd: 0.1,
    primary_dealer_share: 0.23327, direct_bidder_share: 0.06565, indirect_bidder_share: 0.70108,
    shares_check: "ok", bidder_gap: 0,
    dealer_z: 0.3, dealer_z_window: 26, dealer_z_reason: null,
    allocation_pct: 14.0, high_yield: null, high_discnt_rate: 3.68, high_investment_rate: 3.802,
    null_reasons: {},
    demand_signal: null, demand_signal_reason: null,
    ...over,
  };
}

const SUMMARY = {
  data_as_of: "2026-10-08",
  window_n: 26,
  min_observations: 8,
  terms: [
    row("4W", "4-Week", "2026-10-08", { b2c_z: -2.29 }),
    row("13W", "13-Week", "2026-10-05", { b2c_z: -2.4, dealer_z: 2.5, demand_signal: "alert" }),
    row("26W", "26-Week", "2026-10-05", { dealer_z: 2.7, demand_signal: "watch" }),
    row("2Y", "2-Year", "2026-09-22", {
      b2c_recomputed: null, b2c_check: "unverifiable", b2c_z: null, b2c_z_reason: "value_missing",
      null_reasons: { b2c_recomputed: "soma_not_reported", b2c_check: "soma_not_reported" },
    }),
    row("10Y", "10-Year", "2026-10-07", { b2c_check: "mismatch", b2c_reported: 2.62, b2c_z: 2.28 }),
  ],
};

const LIST_26W = {
  data_as_of: "2026-10-08",
  count: 3,
  auctions: [
    row("26W", "26-Week", "2026-10-05"),
    row("26W", "26-Week", "2026-09-29", { b2c_recomputed: 2.9 }),
    row("26W", "26-Week", "2026-09-22", { b2c_recomputed: 2.6 }),
  ],
};

const SIGNALS = {
  data_as_of: "2026-10-08", days: 365, since: "2025-10-08",
  counts: { alert: 2, watch: 1 },
  by_term: ["4W", "8W", "13W", "17W", "26W", "52W", "2Y", "5Y", "10Y", "30Y"].map((term) => ({
    term,
    alerts: term === "26W" ? 2 : 0,
    watches: term === "2Y" ? 1 : 0,
    last_signal_date: term === "26W" ? "2026-03-16" : term === "2Y" ? "2026-03-24" : null,
  })),
  signals: [
    row("26W", "26-Week", "2025-12-29", { demand_signal: "alert", b2c_z: -3.01, dealer_z: 4.76, weakness: 7.77 }),
    row("26W", "26-Week", "2026-03-16", { demand_signal: "alert", b2c_z: -2.40, dealer_z: 2.46, weakness: 4.86 }),
    row("2Y", "2-Year", "2026-03-24", { demand_signal: "watch", b2c_z: -1.86, dealer_z: 4.19, weakness: 6.05 }),
  ],
};

const REGIME = {
  data_as_of: "2026-10-08",
  frequency: {
    count: 14, alerts: 6, watches: 8, band: "high", window_days: 365,
    elevated_at: 8, high_at: 11, max_before: 11, record: true,
    history: [{ month: "2026-08", count: 13 }, { month: "2026-09", count: 14 }, { month: "2026-10", count: 14 }],
  },
  drift: ["4W", "8W", "13W", "17W", "26W", "52W", "2Y", "5Y", "10Y", "30Y"].map((term) => ({
    term, ratio: term === "17W" ? null : term === "5Y" ? 0.84 : 1.0,
    median_52w: 2.5, median_5y: 2.5, drifting: term === "5Y",
    reason: term === "17W" ? "insufficient_history" : null,
  })),
};

let requested;

beforeEach(() => {
  requested = [];
  vi.stubGlobal("fetch", vi.fn((url) => {
    const u = String(url);
    requested.push(u);
    let body = {};
    if (u.includes("/auctions/summary")) body = SUMMARY;
    else if (u.includes("/auctions?term=26W")) body = LIST_26W;
    else if (u.includes("/auctions/signals")) body = { ...SIGNALS, days: Number(u.split("days=")[1]) };
    else if (u.includes("/auctions/regime")) body = REGIME;
    else if (u.includes("/freshness")) body = { counts: {}, sources: [] };
    return Promise.resolve({ ok: true, status: 200, statusText: "OK", json: () => Promise.resolve(body) });
  }));
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const FRESH = new Date("2026-10-09T15:00:00Z");

async function open(today = FRESH) {
  render(<AuctionsTab today={today} />);
  await waitFor(() => expect(screen.queryAllByTestId("auction-row").length).toBeGreaterThan(0));
  return screen.getAllByTestId("auction-row");
}

describe("the user can", () => {
  it("1. open the panel and see the latest auction for each charted term, newest first", async () => {
    const rows = await open();
    expect(rows.map((r) => r.dataset.term)).toEqual(["4W", "10Y", "13W", "26W", "2Y"]);
    const dates = rows.map((r) => r.dataset.date);
    expect(dates).toEqual([...dates].sort().reverse());
  });

  it("2. filter to 26W and see only 26W rows and the 26W chart", async () => {
    await open();
    fireEvent.click(screen.getByRole("button", { name: "26W" }));
    await waitFor(() => expect(requested.some((u) => u.includes("/auctions?term=26W"))).toBe(true));
    await waitFor(() => expect(screen.getAllByTestId("auction-row")).toHaveLength(3));
    expect(new Set(screen.getAllByTestId("auction-row").map((r) => r.dataset.term))).toEqual(new Set(["26W"]));
    expect(screen.getByTestId("auction-chart").dataset.term).toBe("26W");
  });

  it("3. hover a row and see the bidder breakdown, with SOMA labelled as excluded", async () => {
    const rows = await open();
    fireEvent.mouseEnter(rows.find((r) => r.dataset.term === "26W"));
    const tip = await screen.findByRole("tooltip");
    expect(within(tip).getByText(/primary dealers/i)).toBeTruthy();
    expect(within(tip).getByText("23.3%")).toBeTruthy();
    expect(within(tip).getByText("70.1%")).toBeTruthy();
    expect(within(tip).getByText(/excluded from bid-to-cover/i)).toBeTruthy();
  });

  it("4. see a dash with its reason for a missing value, which does not sort as lowest", async () => {
    let rows = await open();
    const twoYear = rows.find((r) => r.dataset.term === "2Y");
    const cell = within(twoYear).getByTestId("cell-b2c_recomputed");
    expect(cell.textContent).toContain("—");
    expect(cell.getAttribute("title")).toMatch(/SOMA was not reported/i);

    fireEvent.click(screen.getByRole("button", { name: /^B2C$/ }));
    rows = screen.getAllByTestId("auction-row");
    expect(rows.at(-1).dataset.term).toBe("2Y");
    fireEvent.click(screen.getByRole("button", { name: /^B2C/ }));
    rows = screen.getAllByTestId("auction-row");
    expect(rows.at(-1).dataset.term).toBe("2Y");
  });

  it("5. see a marker on a row whose bid-to-cover paths disagree", async () => {
    const rows = await open();
    const tenYear = rows.find((r) => r.dataset.term === "10Y");
    expect(within(tenYear).getByLabelText(/bid-to-cover mismatch/i)).toBeTruthy();
    const thirteen = rows.find((r) => r.dataset.term === "13W");
    expect(within(thirteen).queryByLabelText(/bid-to-cover mismatch/i)).toBeNull();
  });

  it("6. see the stale banner when the data is over three business days old, and not otherwise", async () => {
    await open(new Date("2026-10-14T15:00:00Z")); // Thu 8th -> Wed 14th: 4 business days
    expect(screen.getByTestId("stale-banner")).toBeTruthy();
    cleanup();
    await open(FRESH);
    expect(screen.queryByTestId("stale-banner")).toBeNull();
  });

  it("7. see ALERT and WATCH on weak demand, and no colour on strong demand (D-0107)", async () => {
    // D-0107 is the ruling D-0102 waited for: §8b-7 asked for no colour while
    // thresholds were unruled, and now they are ruled.
    const rows = await open();
    const byTerm = (term) => rows.find((r) => r.dataset.term === term);
    expect(within(byTerm("13W")).getByLabelText(/demand alert/i).textContent).toMatch(/ALERT/);
    expect(within(byTerm("26W")).getByLabelText(/demand watch/i).textContent).toMatch(/WATCH/);
    for (const term of ["4W", "10Y", "2Y"]) {
      expect(within(byTerm(term)).queryByLabelText(/demand (alert|watch)/i)).toBeNull();
    }
    const z = (term) => within(byTerm(term)).getByTestId("cell-b2c_z");
    expect(z("4W").textContent).toContain("-2.29");      // one side at 2 sd: not flagged
    expect(z("10Y").style.color).toBe(z("4W").style.color);   // strong demand: neutral
    expect(z("13W").style.color).not.toBe(z("4W").style.color); // the alert's own z is coloured
    expect(screen.getByTestId("signal-count").textContent).toMatch(/1 alert · 1 watch/);
    expect(screen.queryByRole("alert")).toBeNull();
  });
});

describe("the user can also (D-0108)", () => {
  it("8. open Signals and see every flagged auction, alerts first and worst first", async () => {
    await open();
    fireEvent.click(screen.getByRole("button", { name: "Signals" }));
    await waitFor(() => expect(requested.some((u) => u.includes("/auctions/signals?days=365"))).toBe(true));
    await waitFor(() => expect(screen.getAllByTestId("auction-row")).toHaveLength(3));
    const rows = screen.getAllByTestId("auction-row");
    expect(rows.map((r) => r.dataset.date)).toEqual(["2025-12-29", "2026-03-16", "2026-03-24"]);
    expect(within(rows[0]).getByTestId("cell-weakness").textContent).toContain("7.77");
    expect(within(rows[2]).getByLabelText(/demand watch/i)).toBeTruthy();
  });

  it("9. see how many alerts and watches each term had in the window", async () => {
    await open();
    fireEvent.click(screen.getByRole("button", { name: "Signals" }));
    const tally = await screen.findByTestId("tally-26W");
    expect(tally.textContent).toMatch(/2 alerts?/);
    expect(screen.getByTestId("tally-2Y").textContent).toMatch(/1 watch/);
    expect(screen.getByTestId("tally-4W").textContent).toMatch(/none/i);
  });

  it("9b. see all ten terms on one row, so none wraps alone and stretches", async () => {
    await open();
    fireEvent.click(screen.getByRole("button", { name: "Signals" }));
    const tally = await screen.findByTestId("tally-26W");
    const grid = tally.parentElement;
    expect(grid.style.display).toBe("grid");
    expect(grid.style.gridTemplateColumns).toBe("repeat(10, minmax(0, 1fr))");
    expect(grid.children).toHaveLength(10);
  });

  it("10. widen the window to three years", async () => {
    await open();
    fireEvent.click(screen.getByRole("button", { name: "Signals" }));
    await screen.findByTestId("tally-26W");
    fireEvent.click(screen.getByRole("button", { name: "3Y" }));
    await waitFor(() => expect(requested.some((u) => u.includes("/auctions/signals?days=1095"))).toBe(true));
  });
});

describe("the user can read the regime (D-0109, D-0110)", () => {
  it("11. see the 12-month signal count, its band, and that it is a record", async () => {
    await open();
    const panel = await screen.findByTestId("signal-frequency");
    expect(within(panel).getByTestId("frequency-count").textContent).toBe("14");
    expect(within(panel).getByTestId("frequency-band").textContent).toMatch(/HIGH/);
    expect(panel.textContent).toMatch(/6 alerts · 8 watches/);
    expect(panel.textContent).toMatch(/highest/i);
  });

  it("12. see which terms' cover is drifting below their five-year level", async () => {
    await open();
    await screen.findByTestId("signal-frequency");
    expect(screen.getByTestId("drift-5Y").textContent).toMatch(/84%/);
    expect(within(screen.getByTestId("drift-5Y")).getByLabelText(/drifting/i)).toBeTruthy();
    expect(within(screen.getByTestId("drift-13W")).queryByLabelText(/drifting/i)).toBeNull();
    expect(screen.getByTestId("drift-17W").textContent).toMatch(/—/);
  });
});

describe("a link can open the Signals view (D-0109)", () => {
  it("13. arrive from the USA card straight on Signals", async () => {
    render(<AuctionsTab today={FRESH} initialView="signals" />);
    await waitFor(() => expect(requested.some((u) => u.includes("/auctions/signals?days=365"))).toBe(true));
    expect(screen.getByRole("button", { name: "Signals" }).style.color).toBe("rgb(200, 169, 110)");
  });
});

