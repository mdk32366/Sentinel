// @vitest-environment jsdom
/**
 * The pieces CountryDetail was decomposed into.
 *
 * These are narrower than the tab smoke tests: each asserts the one decision
 * its component makes, so a change to that decision fails here with a
 * sentence naming it rather than in a 270-line render.
 */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AnalystBrief } from "./AnalystBrief";
import { CountryStatCards } from "./CountryStatCards";
import { LiquidationBanner } from "./LiquidationBanner";
import { SeriesChart } from "./SeriesChart";

afterEach(cleanup);

const NO_CDS = { cds5y: null, cds10y: null, termSpread: null };

describe("LiquidationBanner", () => {
  const goldRows = [{ date: "2026-06-30", tonnes: 2332.7 }];

  it("fires when a country holds zero Treasuries and still holds gold", () => {
    render(<LiquidationBanner ticHistory={{ data_points: 0, country_name: "Russia" }} goldRows={goldRows} iso="RUS" />);
    expect(screen.getByText(/COMPLETED TREASURY LIQUIDATION/)).toBeTruthy();
    expect(screen.getByText(/2333t/)).toBeTruthy();
  });

  it("stays silent for a country that simply has holdings", () => {
    const { container } = render(
      <LiquidationBanner ticHistory={{ data_points: 12 }} goldRows={goldRows} iso="JPN" />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("stays silent when there is no gold position either", () => {
    // Zero Treasuries AND no gold is an absence of data, not a
    // de-dollarisation posture. Claiming the latter from the former would be
    // the application asserting a signal it cannot see.
    const { container } = render(
      <LiquidationBanner ticHistory={{ data_points: 0 }} goldRows={[]} iso="XXX" />,
    );
    expect(container.firstChild).toBeNull();
  });
});

describe("CountryStatCards", () => {
  it("shows EXITED rather than a dash when the position is genuinely zero", () => {
    render(<CountryStatCards ticHistory={{ data_points: 0 }} cds={NO_CDS} latestAll={{}} />);
    expect(screen.getByText("EXITED")).toBeTruthy();
    expect(screen.getByText("Zero US Treasuries held")).toBeTruthy();
  });

  it("shows a dash when the data is merely absent", () => {
    // The distinction the whole panel turns on: "holds none" is a finding,
    // "we do not know" is not.
    render(<CountryStatCards ticHistory={null} cds={NO_CDS} />);
    expect(screen.queryByText("EXITED")).toBeNull();
  });

  it("signs the spread and the term structure explicitly", () => {
    render(<CountryStatCards
      ticHistory={{ data_points: 3 }}
      latestTic={{ holdings: 1122.4 }}
      ticMom={-2.31}
      countryYield={1.05}
      us10y={4.2}
      cds={{ cds5y: 312, cds10y: 290, termSpread: -22 }}
    />);
    expect(screen.getByText("-315bps")).toBeTruthy();
    expect(screen.getByText("-2.31%")).toBeTruthy();
    expect(screen.getByText("312bps")).toBeTruthy();
    expect(screen.getByText(/inverted/)).toBeTruthy();
  });

  it("says 'No coverage' for CDS rather than implying a spread of zero", () => {
    render(<CountryStatCards ticHistory={null} cds={NO_CDS} />);
    expect(screen.getByText("No coverage")).toBeTruthy();
    expect(screen.getByText("Not factored into stress score")).toBeTruthy();
  });
});

describe("SeriesChart", () => {
  const rows = [{ date: "2026-07-01", holdings: 1000 }, { date: "2026-08-01", holdings: 1100 }];

  it("renders its title when it has rows", () => {
    render(<SeriesChart title="TREASURY HOLDINGS ($B)" rows={rows} dataKey="holdings"
      stroke="#C8A96E" tickFormat={(v) => `$${v}B`} tooltipFormat={(v) => `$${v}B`} tooltipLabel="Holdings" />);
    expect(screen.getByText("TREASURY HOLDINGS ($B)")).toBeTruthy();
  });

  it("renders nothing at all when there are no rows", () => {
    // Each of the three call sites used to guard with `length > 0` itself.
    // Now the component owns it, so a new caller cannot forget.
    const { container } = render(<SeriesChart title="EMPTY" rows={[]} dataKey="holdings"
      stroke="#C8A96E" tickFormat={(v) => v} tooltipFormat={(v) => v} tooltipLabel="x" />);
    expect(container.firstChild).toBeNull();
  });

  it("renders the footnote only when one is given", () => {
    const { rerender } = render(<SeriesChart title="A" rows={rows} dataKey="holdings"
      stroke="#7EB8C9" tickFormat={(v) => v} tooltipFormat={(v) => v} tooltipLabel="x"
      footnote="Source: IMF IFS" />);
    expect(screen.getByText("Source: IMF IFS")).toBeTruthy();

    rerender(<SeriesChart title="A" rows={rows} dataKey="holdings"
      stroke="#7EB8C9" tickFormat={(v) => v} tooltipFormat={(v) => v} tooltipLabel="x" />);
    expect(screen.queryByText("Source: IMF IFS")).toBeNull();
  });
});

describe("AnalystBrief", () => {
  it("offers to generate before anything has been generated", () => {
    render(<AnalystBrief narrative={null} loading={false} onGenerate={() => {}} />);
    expect(screen.getByText(/Generate Analysis/)).toBeTruthy();
  });

  it("calls back when asked, and disables the button while running", () => {
    const onGenerate = vi.fn();
    const { rerender } = render(<AnalystBrief narrative={null} loading={false} onGenerate={onGenerate} />);
    fireEvent.click(screen.getByText(/Generate Analysis/));
    expect(onGenerate).toHaveBeenCalledTimes(1);

    rerender(<AnalystBrief narrative={null} loading onGenerate={onGenerate} />);
    expect(screen.getByRole("button").disabled).toBe(true);
  });

  it("renders the three recognised headings apart from the body", () => {
    render(<AnalystBrief loading={false} onGenerate={() => {}}
      narrative={"SITUATION\nHoldings fell 4%.\n\nRISK FACTORS\nRollover in Q1."} />);
    expect(screen.getByText("SITUATION")).toBeTruthy();
    expect(screen.getByText("RISK FACTORS")).toBeTruthy();
    expect(screen.getByText("Holdings fell 4%.")).toBeTruthy();
  });

  it("still shows a brief whose shape it does not recognise", () => {
    // Degrading to an unformatted paragraph beats an empty panel: the text
    // is the product, the headings are decoration.
    render(<AnalystBrief loading={false} onGenerate={() => {}} narrative="Just one line, no headings." />);
    expect(screen.getByText("Just one line, no headings.")).toBeTruthy();
  });

  it("offers to REGENERATE once a brief exists", () => {
    render(<AnalystBrief narrative="Something." loading={false} onGenerate={() => {}} />);
    expect(screen.getByText(/Regenerate/)).toBeTruthy();
  });
});
