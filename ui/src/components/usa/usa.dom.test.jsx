// @vitest-environment jsdom
/**
 * The pieces USADashboard was decomposed into.
 *
 * The dashboard is where the application states its thesis, and it had no
 * coverage at all. These assert the claims the page makes about its own
 * numbers, not the layout.
 */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { breakingPointRate, crisisRate } from "../../lib/fiscal";
import { SCENARIOS, scenarioOutcomes } from "../../lib/rateScenarios";
import { BreakingPointCalculator } from "./BreakingPointCalculator";
import { FeedbackLoop } from "./FeedbackLoop";
import { M2GrowthChart } from "./M2GrowthChart";
import { RateScenarios } from "./RateScenarios";
import { USAKeyMetrics } from "./USAKeyMetrics";
import { YieldCurveChart } from "./YieldCurveChart";

afterEach(cleanup);

describe("USAKeyMetrics", () => {
  it("F-0057: prices US gold at the live spot rate", () => {
    render(<USAKeyMetrics spotGold={4261} />);
    expect(screen.getByText("8,133t")).toBeTruthy();
    expect(screen.getByText(/\$1\.11T at \$4261\/oz/)).toBeTruthy();
  });

  it("says the spot price is unavailable rather than inventing one", () => {
    // There is deliberately no fallback constant. F-0057 was a hardcoded
    // 4587 against a live series - an $85bn overstatement that read as fact.
    render(<USAKeyMetrics spotGold={null} />);
    expect(screen.getByText("spot price unavailable")).toBeTruthy();
  });

  it("flags a negative real yield as financial repression", () => {
    render(<USAKeyMetrics realYield={-0.4} />);
    expect(screen.getByText(/Financial repression/)).toBeTruthy();
  });

  it("shows the 10Y-2Y spread beside the 10Y, signed", () => {
    render(<USAKeyMetrics dgs10={4.2} dgs2={4.5} />);
    expect(screen.getByText("Spread vs 2Y: -0.30pp")).toBeTruthy();
  });

  it("renders dashes rather than zeroes when nothing has loaded", () => {
    render(<USAKeyMetrics />);
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
  });
});

describe("BreakingPointCalculator", () => {
  it("states the same thresholds lib/fiscal computes", () => {
    render(<BreakingPointCalculator dgs10={4.2} customRate={null} onCustomRate={() => {}} />);
    expect(screen.getByText(`${breakingPointRate().toFixed(1)}% yield`)).toBeTruthy();
    expect(screen.getByText(`${crisisRate().toFixed(1)}% yield`)).toBeTruthy();
  });

  it("reports headroom while the 10Y is below the warning rate", () => {
    render(<BreakingPointCalculator dgs10={4.2} customRate={null} onCustomRate={() => {}} />);
    expect(screen.getByText(/headroom/)).toBeTruthy();
    expect(screen.queryByText(/BREACHED/)).toBeNull();
  });

  it("says BREACHED once the modelled rate is past it", () => {
    render(<BreakingPointCalculator dgs10={4.2} customRate={crisisRate()} onCustomRate={() => {}} />);
    expect(screen.getByText(/BREACHED/)).toBeTruthy();
  });

  it("models a rate the user names instead of the live one", () => {
    render(<BreakingPointCalculator dgs10={4.2} customRate={8} onCustomRate={() => {}} />);
    // 0.55 + 6.0 * 0.08 = 1.03
    expect(screen.getByText("$1.03T")).toBeTruthy();
  });

  it("hands the slider's value back to its owner", () => {
    const seen = [];
    render(<BreakingPointCalculator dgs10={4.2} customRate={null} onCustomRate={(v) => seen.push(v)} />);
    fireEvent.change(screen.getByRole("slider"), { target: { value: "6.5" } });
    expect(seen).toEqual([6.5]);
  });

  it("marks the row nearest the live yield as current", () => {
    render(<BreakingPointCalculator dgs10={4.0} customRate={null} onCustomRate={() => {}} />);
    expect(screen.getByText(/4\.0%\s*← current/)).toBeTruthy();
  });
});

describe("the charts", () => {
  it("YieldCurveChart renders nothing without rows", () => {
    const { container } = render(<YieldCurveChart rows={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it("YieldCurveChart names itself when it has rows", () => {
    render(<YieldCurveChart rows={[{ date: "2026-09-01", "10Y": 4.2 }]} />);
    expect(screen.getByText(/YIELD CURVE/)).toBeTruthy();
  });

  it("M2GrowthChart renders nothing without rows", () => {
    const { container } = render(<M2GrowthChart rows={[]} current={null} />);
    expect(container.firstChild).toBeNull();
  });

  it("M2GrowthChart shows the current reading in its badge", () => {
    render(<M2GrowthChart rows={[{ date: "2026-09-01", growth: 6.2 }]} current={6.2} />);
    expect(screen.getByText("6.2% current")).toBeTruthy();
  });
});

describe("RateScenarios", () => {
  it("asks for a selection before showing anything", () => {
    render(<RateScenarios />);
    expect(screen.getByText(/Select a scenario/)).toBeTruthy();
  });

  it("shows the consequences of a chosen path, and folds it away again", () => {
    render(<RateScenarios />);
    // By role, not by text: the open panel repeats the scenario's label as
    // its heading, so getByText finds two once it is showing.
    const button = screen.getByRole("button", { name: "Cut to 0% (ZIRP)" });
    fireEvent.click(button);
    expect(screen.getByText("CRISIS")).toBeTruthy();
    expect(screen.getByText("Rises 150-250bps")).toBeTruthy();

    fireEvent.click(button);
    expect(screen.queryByText("Rises 150-250bps")).toBeNull();
  });

  it("every scenario says the long end RISES as the Fed cuts", () => {
    // This is the panel's whole argument: the Fed controls the short end and
    // the bond market controls the long end. If an outcome table ever said a
    // cut relieves the long end, the page would be contradicting itself.
    for (const scenario of SCENARIOS.filter((s) => s.ff <= 2)) {
      const tenYear = scenarioOutcomes(scenario).find((o) => o.label === "Likely 10Y Response");
      expect(tenYear.val).toMatch(/^Rises/);
    }
  });
});

describe("FeedbackLoop", () => {
  it("lays out all five steps in order", () => {
    render(<FeedbackLoop />);
    for (const n of ["1", "2", "3", "4", "5"]) {
      expect(screen.getByText(`STEP ${n}`)).toBeTruthy();
    }
  });

  it("quotes the same thresholds the calculator does", () => {
    render(<FeedbackLoop />);
    expect(screen.getByText(new RegExp(`At ${breakingPointRate().toFixed(1)}% on the 10Y`))).toBeTruthy();
  });
});
