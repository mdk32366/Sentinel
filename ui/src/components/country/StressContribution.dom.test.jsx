// @vitest-environment jsdom
/**
 * `D-0060` — the country panel is where the surfaces meet.
 *
 * The COMPOSITE tab ranked countries and the CDS tab listed spreads, and
 * nothing said how the two related. This panel answers "what is this score
 * made of?" for one country, with CDS among the parts.
 */
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { StressContribution } from "./StressContribution";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

function stubComposite(payload) {
  vi.stubGlobal("fetch", vi.fn(() => Promise.resolve({
    ok: true, status: 200, statusText: "OK",
    json: () => Promise.resolve(payload),
  })));
}

const BRAZIL = {
  country_iso: "BRA", country_name: "Brazil", tier: "WATCH",
  composite_score: 5.0, multiplier: 1.0,
  tic_score: 0, gold_score: 0, monetary_score: 0,
  spread_score: 0, petro_score: 0, cds_score: 5,
  cds_coverage: "quoted",
};

const TURKEY = {
  country_iso: "TUR", country_name: "Turkey", tier: "CRISIS",
  composite_score: 178.0, multiplier: 1.5,
  tic_score: 50, gold_score: 40, monetary_score: 35,
  spread_score: 20, petro_score: 0, cds_score: 5,
  cds_coverage: "quoted",
};

const RUSSIA = {
  country_iso: "RUS", country_name: "Russia", tier: "CRISIS",
  composite_score: 139.7, multiplier: 2.0,
  tic_score: 50, gold_score: 20, monetary_score: 0,
  spread_score: 0, petro_score: 0, cds_score: 0,
  cds_coverage: "not quoted as a running spread",
};

describe("StressContribution", () => {
  it("shows the tier and the score", async () => {
    stubComposite({ crisis: [TURKEY], stressed: [], elevated: [], watch: [] });
    render(<StressContribution iso="TUR" />);
    await waitFor(() => expect(screen.getByText("CRISIS")).toBeTruthy());
    expect(screen.getByText("178.0")).toBeTruthy();
    expect(screen.getByText(/× 1.5 applied/)).toBeTruthy();
  });

  it("breaks the score into the dimensions that contributed", async () => {
    stubComposite({ crisis: [TURKEY], stressed: [], elevated: [], watch: [] });
    render(<StressContribution iso="TUR" />);
    await waitFor(() => expect(screen.getByText("Treasury")).toBeTruthy());
    expect(screen.getByText("Gold Reserves")).toBeTruthy();
    expect(screen.getByText("Sovereign CDS")).toBeTruthy();
    // Petrodollar contributed nothing and must not be drawn as an empty part.
    expect(screen.queryByText("Petrodollar")).toBeNull();
  });

  it("names CDS as the sole driver when it is", async () => {
    // Brazil is on the COMPOSITE tab because of its CDS spread and nothing
    // else. Before D-0060 there was no surface that said so.
    stubComposite({ crisis: [], stressed: [], elevated: [], watch: [BRAZIL] });
    render(<StressContribution iso="BRA" />);
    await waitFor(() => expect(screen.getByText("Sovereign CDS")).toBeTruthy());
    expect(screen.getByText(/100%/)).toBeTruthy();
  });

  it("explains a refused CDS quote instead of leaving a blank", async () => {
    // F-0074. "No coverage" and "we threw the quote away" are different
    // facts, and Russia is the second one.
    stubComposite({ crisis: [RUSSIA], stressed: [], elevated: [], watch: [] });
    render(<StressContribution iso="RUS" />);
    await waitFor(() => expect(screen.getByText(/not quoted as a running spread/i)).toBeTruthy());
    expect(screen.getByText(/points-upfront/i)).toBeTruthy();
  });

  it("explains a stale quote with its age", async () => {
    stubComposite({
      crisis: [], stressed: [], elevated: [], watch: [
        { ...BRAZIL, country_iso: "SAU", country_name: "Saudi Arabia",
          cds_score: 0, cds_coverage: "stale (75d old)" },
      ],
    });
    render(<StressContribution iso="SAU" />);
    await waitFor(() => expect(screen.getByText(/75d old/)).toBeTruthy());
  });

  it("says nothing at all for a country the scorer does not rank", async () => {
    // 48 of 105 countries score. An empty panel on the other 57 is noise.
    stubComposite({ crisis: [TURKEY], stressed: [], elevated: [], watch: [] });
    const { container } = render(<StressContribution iso="CHE" />);
    await waitFor(() => expect(screen.queryByText("CRISIS")).toBeNull());
    expect(container.firstChild).toBeNull();
  });

  it("renders nothing rather than throwing while the score is loading", () => {
    stubComposite({ crisis: [], stressed: [], elevated: [], watch: [] });
    const { container } = render(<StressContribution iso="TUR" />);
    expect(container.firstChild).toBeNull();
  });

  it("does not show a multiplier note when there is no multiplier", async () => {
    stubComposite({ crisis: [], stressed: [], elevated: [], watch: [BRAZIL] });
    render(<StressContribution iso="BRA" />);
    await waitFor(() => expect(screen.getByText("WATCH")).toBeTruthy());
    expect(screen.queryByText(/applied/)).toBeNull();
  });
});
