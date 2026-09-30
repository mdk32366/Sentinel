// @vitest-environment jsdom
/**
 * `D-0079` / `A-0019` option 2 — the aggregate, and the claim it must not make.
 *
 * All Other covers roughly a hundred holders including the 28 scored countries
 * outside SLT Table 5's twenty. A move says *someone* reduced. The whole risk of
 * showing it is that a reader takes it as a finding about one of them, which is
 * `F-0097` — the defect that cost 1,050 points across 32 countries.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { AllOtherStrip } from "./AllOtherStrip";

afterEach(cleanup);

/** The real production figures for 2026-07. */
const SIGNAL = {
  as_of: "2026-07-01",
  level_bn: 1842.4,
  share_pct: 19.92,
  mom_pct: -0.43,
  three_month_pct: -1.0,
  twelve_month_pct: 2.74,
  share_move_3m_points: -0.04,
  consecutive_declines: 3,
  points: 13,
  notable: false,
  note:
    "Combined holdings of every foreign holder too small to be named in SLT " +
    "Table 5. A move here says something happened among them; it does not say " +
    "who, and it is not attributed to any country.",
};

describe("AllOtherStrip", () => {
  it("renders nothing before the aggregate has been imported", () => {
    // The row is new; a first deploy will not have it. An empty strip is honest,
    // a zero would not be.
    const { container } = render(<AllOtherStrip signal={null} />);
    expect(container.firstChild).toBeNull();
  });

  it("shows the level, the share and the moves", () => {
    render(<AllOtherStrip signal={SIGNAL} />);
    expect(screen.getByText("$1.84T")).toBeTruthy();
    expect(screen.getByText("19.92%")).toBeTruthy();
    expect(screen.getByText("-0.43%")).toBeTruthy();
    expect(screen.getByText("-1.00%")).toBeTruthy();
    expect(screen.getByText("+2.74%")).toBeTruthy();
  });

  it("states in words that it is not about any one country", () => {
    // The limit has to be on the surface, not only in the register.
    render(<AllOtherStrip signal={SIGNAL} />);
    expect(screen.getByText(/does not say who/)).toBeTruthy();
    expect(screen.getByText(/not attributed to any country/)).toBeTruthy();
  });

  it("names no country at all", () => {
    const { container } = render(<AllOtherStrip signal={SIGNAL} />);
    for (const iso of ["Germany", "DEU", "Turkey", "TUR", "Russia", "RUS"]) {
      expect(container.textContent).not.toContain(iso);
    }
  });

  it("stays neutral on ordinary drift", () => {
    // -1.00% over three months with the share moving 0.04 points is normal. A
    // brand-new signal that alarms on its first real reading is the cry-wolf
    // shape of F-0089, F-0091 and F-0095.
    const { container } = render(<AllOtherStrip signal={SIGNAL} />);
    expect(container.innerHTML).not.toMatch(/rgb\(232, 197, 71\)/);
    expect(screen.queryByText(/something changed among the holders/)).toBeNull();
  });

  it("speaks up when the share really moves, and still names nobody", () => {
    const rotation = { ...SIGNAL, share_move_3m_points: -1.4, notable: true };
    render(<AllOtherStrip signal={rotation} />);
    expect(screen.getByText(/something changed among the holders/)).toBeTruthy();
    // And immediately says what it cannot tell you.
    expect(screen.getByText(/not knowable from this row/)).toBeTruthy();
  });

  it("reports the consecutive-decline run when there is one", () => {
    render(<AllOtherStrip signal={SIGNAL} />);
    expect(screen.getByText(/3mo consecutive/)).toBeTruthy();
  });

  it("omits the run when the series last rose", () => {
    render(<AllOtherStrip signal={{ ...SIGNAL, consecutive_declines: 0 }} />);
    expect(screen.queryByText(/consecutive/)).toBeNull();
  });

  it("survives a partial signal rather than printing undefined", () => {
    // Fewer than 13 months of history leaves the longer windows null.
    const thin = {
      as_of: "2026-07-01", level_bn: 1842.4, share_pct: null,
      mom_pct: null, three_month_pct: null, twelve_month_pct: null,
      share_move_3m_points: null, consecutive_declines: 0, notable: false,
      note: "x",
    };
    const { container } = render(<AllOtherStrip signal={thin} />);
    expect(container.textContent).not.toMatch(/undefined|NaN/);
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
  });
});
