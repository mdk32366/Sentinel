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

describe("the CDS tile explains an absence", () => {
  it("F-0078: shows the spread once the ISO code actually resolves", () => {
    // /cds?country=TUR built "TUR_CDS_5Y", which does not exist, so this tile
    // read "No coverage" for every country from the day it shipped.
    render(<CountryStatCards ticHistory={null} cds={{ cds5y: 248.08, cds10y: null, termSpread: null, coverage: "quoted" }} />);
    expect(screen.getByText("248bps")).toBeTruthy();
  });

  it("gives the refusal reason rather than a generic line", () => {
    render(<CountryStatCards ticHistory={null}
      cds={{ ...NO_CDS, coverage: "not quoted as a running spread" }} />);
    expect(screen.getByText("not quoted as a running spread")).toBeTruthy();
  });

  it("reports a stale quote with its age", () => {
    render(<CountryStatCards ticHistory={null} cds={{ ...NO_CDS, coverage: "stale (75d old)" }} />);
    expect(screen.getByText("stale (75d old)")).toBeTruthy();
  });

  it("falls back to the generic line when there is genuinely no coverage", () => {
    render(<CountryStatCards ticHistory={null} cds={{ ...NO_CDS, coverage: "no coverage" }} />);
    expect(screen.getByText("no coverage")).toBeTruthy();
  });

  it("says 5Y only when there is no paired 10Y", () => {
    // Every 10Y on this board was the ISDA coupon and is now refused, so this
    // is the ordinary case rather than an edge one.
    render(<CountryStatCards ticHistory={null}
      cds={{ cds5y: 129.6, cds10y: null, termSpread: null, coverage: "quoted" }} />);
    expect(screen.getByText(/5Y only — no paired 10Y/)).toBeTruthy();
  });
});

describe("D-0073: every country tile explains itself", () => {
  const LABELS = ["T-Bill Holdings", "MoM Change", "Gold Reserves",
                  "Sovereign Yield", "Spread vs US 10Y", "5Y CDS"];

  function openTile(container, label) {
    const cell = [...container.querySelectorAll("div")]
      .find((d) => d.textContent.trim().startsWith(label));
    fireEvent.mouseEnter(cell.closest("[tabindex]") ?? cell);
    return screen.queryByRole("tooltip");
  }

  it("all six tiles are rendered", () => {
    render(<CountryStatCards ticHistory={{ data_points: 3 }} cds={NO_CDS} />);
    for (const label of LABELS) {
      expect(screen.getByText(label), label).toBeTruthy();
    }
  });

  it("each tile is focusable, so the explanation is not mouse-only", () => {
    const { container } = render(<CountryStatCards ticHistory={{ data_points: 3 }} cds={NO_CDS} />);
    const focusable = container.querySelectorAll('[tabindex="0"]');
    expect(focusable.length).toBe(6);
  });

  it("the CDS tip quotes the live scoring ladder, not a copy of it", () => {
    // F-0081's lesson: a threshold written into prose drifts the moment the
    // constant moves. This tip is generated from CDS_BANDS.
    const { container } = render(<CountryStatCards ticHistory={null} cds={NO_CDS} />);
    const tip = openTile(container, "5Y CDS");
    expect(tip.textContent).toMatch(/>200bps = 5 pts/);
    expect(tip.textContent).toMatch(/>350bps = 10 pts/);
    expect(tip.textContent).toMatch(/>600bps = 15 pts/);
  });

  it("the spread tip says it is measured and not scored", () => {
    const { container } = render(<CountryStatCards ticHistory={null} cds={NO_CDS} countryYield={1.05} us10y={4.2} />);
    const tip = openTile(container, "Spread vs US 10Y");
    expect(tip.textContent).toMatch(/MEASURED ONLY/);
    expect(tip.textContent).toMatch(/zero points to zero countries/);
  });

  it("the CDS colour follows the scoring ladder", () => {
    // 248bps is above 200 and below 350 - the first rung. It read as the
    // SECOND rung's colour while the tile used the retired 100/250 numbers.
    const { container } = render(<CountryStatCards ticHistory={null}
      cds={{ cds5y: 248, cds10y: null, termSpread: null, coverage: "quoted" }} />);
    const value = [...container.querySelectorAll("div")].find((d) => d.textContent === "248bps");
    expect(value.style.color).toBe("rgb(200, 169, 110)");
  });
});

// ── Sentinel D-0113 (Trinity ruling 2026-10-22): FB daily bonds on the cards ──
import {
  FB_CARD_COUNTRY, FB_MAX_AGE_DAYS, SOVEREIGN_YIELD_CODES, countryBond, fbCardCodes,
} from "../../lib/constants";
import { TRACKED_CODES } from "../../hooks/useMarketSeries";
import { CountryBondCurve } from "./CountryBondCurve";

const NOW = new Date("2026-10-22T12:00:00Z");
const D = "2026-10-21";
function deLatest(over = {}) {
  return {
    latest: { FB_DE_02Y: 2.1, FB_DE_05Y: 2.3, FB_DE_07Y: 2.4, FB_DE_10Y: 2.6, FB_DE_30Y: 3.05,
      [SOVEREIGN_YIELD_CODES.DEU]: 2.9, DGS10: 4.2, ...(over.latest || {}) },
    dates: { FB_DE_02Y: D, FB_DE_05Y: D, FB_DE_07Y: D, FB_DE_10Y: D, FB_DE_30Y: D, ...(over.dates || {}) },
  };
}

describe("D-0113: the FB card mapping", () => {
  it("maps exactly the four FB countries to their FB codes", () => {
    // Sentinel D-0115 adds CAN/SWE/AUS/NOR/ESP; never EA (T-0131).
    expect(FB_CARD_COUNTRY).toEqual({ DEU: "DE", GBR: "GB", JPN: "JP", FRA: "FR",
      CAN: "CA", SWE: "SE", AUS: "AU", NOR: "NO", ESP: "ES",
      ITA: "IT", POL: "PL", GRC: "GR", PRT: "PT" }); // D-0116
    expect(Object.values(FB_CARD_COUNTRY)).not.toContain("EA");
    expect(fbCardCodes("JPN")).toEqual(["FB_JP_02Y", "FB_JP_05Y", "FB_JP_07Y", "FB_JP_10Y", "FB_JP_30Y"]);
    expect(fbCardCodes("BEL")).toEqual([]);
  });

  it("mirrors the watchdog's per-source freshness limits (freshness_watchdog.py)", () => {
    expect(FB_MAX_AGE_DAYS).toEqual({ DE: 4, GB: 5, JP: 7, FR: 4,
      CA: 4, SE: 4, AU: 12, NO: 4, ES: 4, EA: 4, PL: 40, IT: 45 });
  });

  it("returns null for a non-FB country, so BEL is unchanged (ITA joined in D-0116)", () => {
    expect(countryBond("BEL", {}, {}, NOW)).toBeNull();
  });
});

describe("D-0113: the 10Y on the Sovereign Yield and Spread cards", () => {
  it("uses the daily FB 10Y and names the source in the tip", () => {
    const { latest, dates } = deLatest();
    const b = countryBond("DEU", latest, dates, NOW);
    expect(b.tenYear.value).toBe(2.6);
    expect(b.tenYear.daily).toBe(true);
    expect(b.tenYear.badge).toBeNull();
    expect(b.tenYear.tip).toMatch(/FIT/);
    expect(b.tenYear.tip).toMatch(/daily/);
    const jp = countryBond("JPN", { FB_JP_10Y: 1.6 }, { FB_JP_10Y: D }, NOW);
    expect(jp.tenYear.tip).toMatch(/CMT/);
  });

  it("FRA falls back to the monthly OECD series with a MONTHLY badge when no daily 10Y", () => {
    const b = countryBond("FRA", { [SOVEREIGN_YIELD_CODES.FRA]: 3.4 }, {}, NOW);
    expect(b.tenYear.value).toBe(3.4);
    expect(b.tenYear.daily).toBe(false);
    expect(b.tenYear.badge).toBe("MONTHLY");
    expect(b.tenYear.code).toBe(SOVEREIGN_YIELD_CODES.FRA);
    expect(b.tenYear.tip).toMatch(/monthly OECD/);
  });

  it("falls back too when the daily 10Y is stale beyond its limit", () => {
    const { latest, dates } = deLatest({ dates: { FB_DE_10Y: "2026-10-10" } });
    const b = countryBond("DEU", latest, dates, NOW);
    expect(b.tenYear.badge).toBe("MONTHLY");
    expect(b.tenYear.value).toBe(2.9);
  });

  it("renders the daily value with a DAILY sub-line and the spread from the daily 10Y", () => {
    const { latest, dates } = deLatest();
    const b = countryBond("DEU", latest, dates, NOW);
    render(<CountryStatCards ticHistory={null} cds={NO_CDS} countryYield={b.tenYear.value}
      yieldSource={b.tenYear} us10y={4.2} />);
    expect(screen.getByText("2.60%")).toBeTruthy();
    expect(screen.getByText(/DAILY · FIT/)).toBeTruthy();
    expect(screen.getByText("-160bps")).toBeTruthy();
  });

  it("renders the MONTHLY badge on the FRA fallback", () => {
    const b = countryBond("FRA", { [SOVEREIGN_YIELD_CODES.FRA]: 3.4 }, {}, NOW);
    render(<CountryStatCards ticHistory={null} cds={NO_CDS} countryYield={b.tenYear.value}
      yieldSource={b.tenYear} us10y={4.2} />);
    expect(screen.getAllByText(/MONTHLY/).length).toBeGreaterThan(0);
    expect(screen.getByText("-80bps")).toBeTruthy();
  });
});

describe("D-0113: the curve row and slopes", () => {
  it("shows NO SOURCE for a tenor with no observation", () => {
    const { latest, dates } = deLatest();
    delete latest.FB_DE_07Y; delete dates.FB_DE_07Y;
    render(<CountryBondCurve iso="DEU" bond={countryBond("DEU", latest, dates, NOW)} />);
    expect(screen.getByText("2.10%")).toBeTruthy();
    expect(screen.getAllByText("NO SOURCE")).toHaveLength(1);
  });

  it("slopes are in bp: 2s10s and 10s30s", () => {
    const { latest, dates } = deLatest();
    const b = countryBond("DEU", latest, dates, NOW);
    expect(b.slopes.map((s) => [s.label, s.bp])).toEqual([["2s10s", 50], ["10s30s", 45]]);
    render(<CountryBondCurve iso="DEU" bond={b} />);
    expect(screen.getByText("+50bp")).toBeTruthy();
    expect(screen.getByText("+45bp")).toBeTruthy();
  });

  it("a stale leg makes the slope a dash", () => {
    const { latest, dates } = deLatest({ dates: { FB_DE_30Y: "2026-10-01" } });
    const b = countryBond("DEU", latest, dates, NOW);
    expect(b.slopes[0].bp).toBe(50);
    expect(b.slopes[1].bp).toBeNull();
    render(<CountryBondCurve iso="DEU" bond={b} />);
    expect(screen.getByTestId("slope-10s30s").textContent).toMatch(/—/);
  });

  it("legs on different observation dates never make a slope", () => {
    const { latest, dates } = deLatest({ dates: { FB_DE_02Y: "2026-10-20" } });
    const b = countryBond("DEU", latest, dates, NOW);
    expect(b.slopes[0].bp).toBeNull();
    render(<CountryBondCurve iso="DEU" bond={b} />);
    expect(screen.getByTestId("slope-2s10s").textContent).toMatch(/—/);
  });
});

// Pinned through a mask: constants.test.js forbids the literal FRED codes
// outside constants.js, and the mask keeps every country letter exact.
const mask = (x) => x.replace(/IRLTLT01([A-Z]{2})M156N/g, "SOV_$1");
const SOVEREIGN_BASELINE = '{"JPN":"SOV_JP","DEU":"SOV_DE","ITA":"SOV_IT","FRA":"SOV_FR","ESP":"SOV_ES","GBR":"SOV_GB","AUS":"SOV_AU","CAN":"SOV_CA","NLD":"SOV_NL","NOR":"SOV_NO","SWE":"SOV_SE","CHE":"SOV_CH","BEL":"SOV_BE","KOR":"SOV_KR"}';
const TRACKED_BASELINE = "DGS30,DGS10,DGS7,DGS5,DGS2,DFF,DFII10,DCOILWTICO,DTWEXBGS,CPIAUCSL,WM2NS,GOLD_SPOT_USD,SOV_JP,SOV_DE,SOV_IT,SOV_FR,SOV_ES,SOV_GB,SOV_AU,SOV_CA,SOV_NL,SOV_NO,SOV_SE,SOV_CH,SOV_BE,SOV_KR";

describe("D-0113 hard invariants", () => {
  it("SOVEREIGN_YIELD_CODES is exactly unchanged", () => {
    expect(mask(JSON.stringify(SOVEREIGN_YIELD_CODES))).toBe(SOVEREIGN_BASELINE);
    for (const c of Object.values(SOVEREIGN_YIELD_CODES)) expect(c).toMatch(/^IRLTLT01[A-Z]{2}M156N$/);
  });

  it("MARKETS TRACKED_CODES is exactly unchanged and holds no FB_ code", () => {
    expect(mask(TRACKED_CODES.join(","))).toBe(TRACKED_BASELINE);
    expect(TRACKED_CODES.some((c) => c.startsWith("FB_"))).toBe(false);
  });
});
