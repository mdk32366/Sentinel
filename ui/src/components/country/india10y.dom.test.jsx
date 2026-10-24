// @vitest-environment jsdom
/**
 * Sentinel D-0118: the IND card's 10Y. Daily CCIL FB_IN_10Y while within 7
 * days, else the monthly OECD INDIRLTLT01STM (via FRED, badged MONTHLY) while
 * within 75, else a dash. India is never in SOVEREIGN_YIELD_CODES. Display only.
 * The Python halves are in tests/test_india_10y.py.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import * as constants from "../../lib/constants";
import { MARKET_REQUEST_CODES, TRACKED_CODES } from "../../hooks/useMarketSeries";
import { CountryBondCurve } from "./CountryBondCurve";
import { CountryStatCards } from "./CountryStatCards";

const { SOVEREIGN_YIELD_CODES, countryBond, fbCardFetchCodes } = constants;
const MONTHLY_10Y_EXTRA_CODES = constants.MONTHLY_10Y_EXTRA_CODES ?? {};
const CCIL_ATTRIBUTION = constants.CCIL_ATTRIBUTION;

afterEach(cleanup);

const NOW = new Date("2026-10-22T12:00:00Z");
const M = "INDIRLTLT01STM";
const DAILY = { FB_IN_02Y: 6.6982, FB_IN_05Y: 7.2097, FB_IN_10Y: 7.4553, FB_IN_30Y: 7.8616 };
const at = (codes, date) => Object.fromEntries(codes.map((c) => [c, date]));
const NO_CDS = { cds5y: null, cds10y: null, termSpread: null };

function monthly(date, value = 7.06) {
  return countryBond("IND", { [M]: value }, { [M]: date }, NOW);
}

describe("T-0161: the IND card shows the latest INDIRLTLT01STM, MONTHLY", () => {
  it("resolves through MONTHLY_10Y_EXTRA_CODES, not SOVEREIGN_YIELD_CODES", () => {
    expect(MONTHLY_10Y_EXTRA_CODES).toEqual({ IND: M });
    expect(SOVEREIGN_YIELD_CODES.IND).toBeUndefined();
    const b = monthly("2026-09-01");
    expect(b?.tenYear).toMatchObject({ value: 7.06, badge: "MONTHLY", daily: false, code: M });
    render(<CountryStatCards ticHistory={null} cds={NO_CDS} countryYield={b?.tenYear.value ?? null} yieldSource={b?.tenYear ?? null} />);
    expect(screen.getByText("7.06%")).toBeTruthy();
    expect(screen.getAllByText("MONTHLY").length).toBeGreaterThan(0);
  });
});

describe("T-0162: monthly fresh at 75 days, stale at 76, dash with no rows", () => {
  it("75 / 76 / none", () => {
    // NOW is 2026-10-22: 2026-08-08 is 75 days old, 2026-08-07 is 76.
    expect(monthly("2026-08-08")?.tenYear).toMatchObject({ value: 7.06, badge: "MONTHLY" });
    expect(monthly("2026-08-07")?.tenYear).toMatchObject({ value: null, badge: "STALE" });
    const none = countryBond("IND", {}, {}, NOW);
    expect(none?.tenYear.value).toBeNull();
    render(<CountryStatCards ticHistory={null} cds={NO_CDS} countryYield={none?.tenYear.value ?? null} yieldSource={none?.tenYear ?? null} />);
    expect(screen.queryByText("0.00%")).toBeNull();
  });
});

describe("T-0166: requested, and no curve or slopes in monthly mode", () => {
  it("useMarketSeries requests INDIRLTLT01STM; TRACKED_CODES does not carry it", () => {
    expect(MARKET_REQUEST_CODES).toContain(M);
    expect(TRACKED_CODES).not.toContain(M);
    expect(fbCardFetchCodes("IND")).toContain(M);
  });

  it("monthly mode renders no curve row and no slopes", () => {
    const b = monthly("2026-09-01");
    expect(b?.showCurve).toBe(false);
    expect(b?.slopes).toEqual([]);
    const { container } = render(<CountryBondCurve iso="IND" bond={b ?? { showCurve: false }} />);
    expect(container.innerHTML).toBe("");
  });
});

describe("T-0173: daily CCIL, then monthly, then a dash", () => {
  it("daily within 7 days: 10Y, DAILY, 2/5/10/30 curve, 2s10s and 10s30s, attribution", () => {
    const b = countryBond("IND", { ...DAILY, [M]: 7.06 }, { ...at(Object.keys(DAILY), "2026-10-15"), [M]: "2026-09-01" }, NOW);
    expect(b?.tenYear).toMatchObject({ value: 7.4553, daily: true, code: "FB_IN_10Y" });
    expect(b?.curve.map((c) => c.label)).toEqual(["2Y", "5Y", "10Y", "30Y"]);
    expect(b?.slopes.map((s) => [s.label, s.bp])).toEqual([["2s10s", 75.71], ["10s30s", 40.63]]);
    expect(b?.showCurve).toBe(true);
    expect(CCIL_ATTRIBUTION).toBe("Source: The Clearing Corporation of India Ltd. (CCIL), Tenorwise Indicative Yields, https://www.ccilindia.com/tenorwise-indicative-yields");
    render(<CountryBondCurve iso="IND" bond={b} />);
    const link = screen.getByRole("link");
    expect(link.getAttribute("href")).toBe("https://www.ccilindia.com/tenorwise-indicative-yields");
    expect(screen.getByTestId("ccil-attribution").textContent).toContain("The Clearing Corporation of India Ltd. (CCIL)");
    expect(screen.getByTestId("curve-10Y").getAttribute("data-tip")).toContain("9Y-10Y");
  });

  it("a slope never spans dates", () => {
    const dates = { ...at(Object.keys(DAILY), "2026-10-15"), FB_IN_02Y: "2026-10-14" };
    const b = countryBond("IND", DAILY, dates, NOW);
    expect(b?.slopes.map((s) => [s.label, s.bp])).toEqual([["2s10s", null], ["10s30s", 40.63]]);
  });

  it("at 8 days: the monthly fallback, no curve, no attribution", () => {
    const b = countryBond("IND", { ...DAILY, [M]: 7.06 }, { ...at(Object.keys(DAILY), "2026-10-14"), [M]: "2026-09-01" }, NOW);
    expect(b?.tenYear).toMatchObject({ value: 7.06, code: M, badge: "MONTHLY", daily: false });
    expect(b?.showCurve).toBe(false);
    const { container } = render(<CountryBondCurve iso="IND" bond={b ?? { showCurve: false }} />);
    expect(container.innerHTML).toBe("");
  });

  it("both stale: a dash", () => {
    const b = countryBond("IND", { ...DAILY, [M]: 7.06 }, { ...at(Object.keys(DAILY), "2026-10-14"), [M]: "2026-08-01" }, NOW);
    expect(b?.tenYear.value).toBeNull();
    expect(b?.showCurve).toBe(false);
  });
});
