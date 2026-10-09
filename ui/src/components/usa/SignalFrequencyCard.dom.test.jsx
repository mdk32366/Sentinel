// @vitest-environment jsdom
/**
 * D-0109 on the USA card - the signal spikes as a card of their own.
 *
 * Owner, 2026-10-08: "Signals spikes should show up on the USA baseball card
 * as its own card with a tool tip and a reference to the auctions signals UI
 * surface." The number of signals is the signal; this card carries it.
 */
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SignalFrequencyCard } from "./SignalFrequencyCard";

let regime;

const HIGH = {
  data_as_of: "2026-10-08",
  frequency: {
    count: 14, alerts: 6, watches: 8, band: "high", window_days: 365,
    elevated_at: 8, high_at: 11, max_before: 11, record: true,
    history: [
      { month: "2025-10", count: 4 }, { month: "2026-02", count: 7 },
      { month: "2026-06", count: 12 }, { month: "2026-10", count: 14 },
    ],
  },
  drift: [],
};

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn(() => Promise.resolve({
    ok: true, status: 200, statusText: "OK", json: () => Promise.resolve(regime),
  })));
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("the signal-frequency card", () => {
  it("is a card of its own, fed by the regime endpoint", async () => {
    regime = HIGH;
    render(<SignalFrequencyCard />);
    await screen.findByTestId("usa-signal-frequency");
    expect(String(fetch.mock.calls[0][0])).toContain("/auctions/regime");
  });

  it("shows the 12-month count, the band, and that it is a record", async () => {
    regime = HIGH;
    render(<SignalFrequencyCard />);
    const card = await screen.findByTestId("usa-signal-frequency");
    expect(within(card).getByTestId("usa-frequency-count").textContent).toBe("14");
    expect(within(card).getByTestId("usa-frequency-band").textContent).toBe("HIGH");
    expect(card.textContent).toMatch(/6 alerts · 8 watches/);
    expect(card.textContent).toMatch(/highest since 2008/i);
    expect(card.textContent).toMatch(/previous peak 11/i);
  });

  it("carries a tooltip that explains the count and its bands", async () => {
    regime = HIGH;
    render(<SignalFrequencyCard />);
    const card = await screen.findByTestId("usa-signal-frequency");
    expect(card.querySelector("[data-tip='yes']")).not.toBeNull();
  });

  it("links to the Signals view on AUCTIONS", async () => {
    regime = HIGH;
    render(<SignalFrequencyCard />);
    await screen.findByTestId("usa-signal-frequency");
    expect(screen.getByRole("link", { name: /signals/i }).getAttribute("href")).toBe("#/auctions/signals");
  });

  it("draws the 12-month history against the bands", async () => {
    regime = HIGH;
    render(<SignalFrequencyCard />);
    const card = await screen.findByTestId("usa-signal-frequency");
    expect(card.querySelector("svg [data-series='count']")).not.toBeNull();
    expect(card.querySelectorAll("svg [data-band-line]")).toHaveLength(2);
  });

  it("explains each band line on hover", async () => {
    regime = HIGH;
    render(<SignalFrequencyCard />);
    const card = await screen.findByTestId("usa-signal-frequency");
    for (const [band, label, at] of [["elevated", "ELEVATED", "8"], ["high", "HIGH", "11"]]) {
      const target = card.querySelector(`[data-band-tip='${band}']`);
      expect(target, `${band} line has no hover target`).not.toBeNull();
      expect(target.dataset.tip).toBe("yes");
      fireEvent.mouseEnter(target);
      const tip = await screen.findByRole("tooltip");
      expect(tip.textContent).toContain(label);
      expect(tip.textContent).toContain(`${at} signals`);
      expect(tip.textContent).toMatch(/today: 14/i);
      fireEvent.mouseLeave(target);
    }
  });

  it("says which years reached the high line, from the history", async () => {
    regime = HIGH;
    render(<SignalFrequencyCard />);
    const card = await screen.findByTestId("usa-signal-frequency");
    fireEvent.mouseEnter(card.querySelector("[data-band-tip='high']"));
    const tip = await screen.findByRole("tooltip");
    expect(tip.textContent).toMatch(/2 months/);   // 2026-06 (12) and 2026-10 (14)
    expect(tip.textContent).toContain("2026");
  });

  it("says plainly when the count is normal, and claims no record", async () => {
    regime = { ...HIGH, frequency: { ...HIGH.frequency, count: 3, alerts: 1, watches: 2, band: "normal", record: false } };
    render(<SignalFrequencyCard />);
    const card = await screen.findByTestId("usa-signal-frequency");
    expect(within(card).getByTestId("usa-frequency-band").textContent).toBe("NORMAL");
    expect(card.textContent).not.toMatch(/highest/i);
  });
});
