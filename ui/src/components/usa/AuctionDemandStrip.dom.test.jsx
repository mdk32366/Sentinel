// @vitest-environment jsdom
/**
 * D-0108 - auction demand on the USA card.
 *
 * The card says US stress is whether the market will accept the terms as
 * foreign demand weakens. Auction demand is the direct measure, so the card
 * shows the last 90 days of weak-demand signals and links to AUCTIONS.
 * Display only: the composite excludes the US, and whether auction demand
 * feeds any score is an owner ruling not made (ORDER auction-demand §11).
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AuctionDemandStrip } from "./AuctionDemandStrip";

let payload;

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn(() => Promise.resolve({
    ok: true, status: 200, statusText: "OK", json: () => Promise.resolve(payload),
  })));
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const FLAGGED = {
  data_as_of: "2026-10-08", days: 90, since: "2026-07-10",
  counts: { alert: 1, watch: 2 },
  by_term: [],
  signals: [
    { term: "8W", auction_date: "2026-07-23", demand_signal: "alert", weakness: 6.99 },
    { term: "4W", auction_date: "2026-09-24", demand_signal: "watch", weakness: 3.76 },
    { term: "17W", auction_date: "2026-08-12", demand_signal: "watch", weakness: 3.1 },
  ],
};

describe("the USA card shows auction demand", () => {
  it("asks for the last 90 days", async () => {
    payload = FLAGGED;
    render(<AuctionDemandStrip />);
    await screen.findByTestId("usa-auction-demand");
    expect(String(fetch.mock.calls[0][0])).toContain("/auctions/signals?days=90");
  });

  it("counts alerts and watches and names the most recent signal", async () => {
    payload = FLAGGED;
    render(<AuctionDemandStrip />);
    const strip = await screen.findByTestId("usa-auction-demand");
    expect(strip.textContent).toMatch(/1 alert/);
    expect(strip.textContent).toMatch(/2 watches/);
    expect(strip.textContent).toMatch(/4W.*2026-09-24/);       // most recent, not the worst
  });

  it("says so plainly when there is nothing", async () => {
    payload = { ...FLAGGED, counts: { alert: 0, watch: 0 }, signals: [] };
    render(<AuctionDemandStrip />);
    const strip = await screen.findByTestId("usa-auction-demand");
    expect(strip.textContent).toMatch(/no weak-demand signal/i);
  });

  it("links to the AUCTIONS tab", async () => {
    payload = FLAGGED;
    render(<AuctionDemandStrip />);
    await screen.findByTestId("usa-auction-demand");
    expect(screen.getByRole("link", { name: /auctions/i }).getAttribute("href")).toBe("#/auctions");
  });
});
