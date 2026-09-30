// @vitest-environment jsdom
/**
 * `D-0083` / `A-0021` option 1 — the holdings move, decomposed.
 *
 * Dimension 1 scores month-on-month change in **holdings**, which moves with
 * transactions and with price. Japan's July 2026: holdings -$12.7bn (-1.15%),
 * net transactions **+$0.9bn**, long-term valuation **-$12.1bn**. A net buyer,
 * scored as a seller.
 *
 * Option 1 was chosen over switching the scorer's input because the position
 * change and the published flows disagree by more than 10% of the move in 65%
 * of country-months. So this shows and does not score.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { TreasuryFlow } from "./TreasuryFlow";

afterEach(cleanup);

/** Japan, July 2026, as production serves it. */
const JAPAN = {
  country_iso: "JPN",
  tic_mom_pct: -1.15,
  tic_net_1m_bn: 0.9,
  tic_valuation_1m_bn: -12.1,
  tic_net_3m_bn: -88.6,
  tic_flow_months: 3,
};

/** China: genuinely sold, so holdings and transactions agree. */
const CHINA = {
  country_iso: "CHN",
  tic_mom_pct: -2.43,
  tic_net_1m_bn: -12.6,
  tic_valuation_1m_bn: -1.7,
  tic_net_3m_bn: -30.2,
  tic_flow_months: 3,
};

describe("TreasuryFlow", () => {
  it("renders nothing for a country with no flow data", () => {
    // 16 reporters publish no total, and Table 3 predates 2020. An empty panel
    // is honest; zeros would not be.
    const { container } = render(<TreasuryFlow row={{ country_iso: "QAT" }} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders nothing without a row at all", () => {
    const { container } = render(<TreasuryFlow row={null} />);
    expect(container.firstChild).toBeNull();
  });

  it("shows the holdings move beside what it was made of", () => {
    render(<TreasuryFlow row={JAPAN} />);
    expect(screen.getByText("-1.15%")).toBeTruthy();
    expect(screen.getByText("+$0.9bn")).toBeTruthy();
    expect(screen.getByText("−$12.1bn")).toBeTruthy();
  });

  it("shows the three-month transaction total", () => {
    // The figure that answers "did they actually sell": Japan's -$88.6bn over
    // three months is real selling that a 1.15% monthly move hides.
    render(<TreasuryFlow row={JAPAN} />);
    expect(screen.getByText("−$88.6bn")).toBeTruthy();
  });

  it("says so when holdings and transactions point opposite ways", () => {
    // The Japan case. Without this the reader sees -1.15% and +$0.9bn side by
    // side and has to notice the contradiction themselves.
    render(<TreasuryFlow row={JAPAN} />);
    expect(screen.getByText(/transactions went the other way/)).toBeTruthy();
    expect(screen.getByText(/reading price rather than posture/)).toBeTruthy();
  });

  it("stays quiet when they agree", () => {
    // China genuinely sold: 88% of its decline was transactions. Flagging that
    // would make the flag meaningless.
    render(<TreasuryFlow row={CHINA} />);
    expect(screen.queryByText(/transactions went the other way/)).toBeNull();
  });

  it("does not flag a rounding-sized transaction", () => {
    // A country whose holdings fell on price with $0.01bn of transactions has
    // no meaningful contradiction to report.
    const tiny = { ...JAPAN, tic_net_1m_bn: 0.01 };
    render(<TreasuryFlow row={tiny} />);
    expect(screen.queryByText(/transactions went the other way/)).toBeNull();
  });

  it("states that the split is shown and not scored", () => {
    // A-0021 option 1 changes no number, and the surface has to say so or a
    // reader will assume the score already accounts for it.
    render(<TreasuryFlow row={JAPAN} />);
    expect(screen.getByText(/shown rather than scored/)).toBeTruthy();
  });

  it("renders a dash rather than undefined for a missing component", () => {
    const partial = { ...JAPAN, tic_valuation_1m_bn: null };
    const { container } = render(<TreasuryFlow row={partial} />);
    expect(container.textContent).not.toMatch(/undefined|NaN/);
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
  });
});
