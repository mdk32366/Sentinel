// @vitest-environment jsdom
/**
 * Sentinel D-0115 (FB batch 2a, spec@0.3 §15): the new country cards and the
 * euro-area benchmark panel. Display only.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import {
  FB_CARD_COUNTRY, SOVEREIGN_YIELD_CODES, countryBond, eaBenchmark, fbCardCodes,
} from "../../lib/constants";
import { EaBenchmarkPanel } from "../foreignBonds/EaBenchmarkPanel";
import { CountryBondCurve } from "./CountryBondCurve";
import { CountryStatCards } from "./CountryStatCards";

afterEach(cleanup);

const NOW = new Date("2026-10-22T12:00:00Z");
const D = "2026-10-21";
const NO_CDS = { cds5y: null, cds10y: null, termSpread: null };

function fresh(iso, values) {
  const codes = fbCardCodes(iso);
  const latest = {}, dates = {};
  codes.forEach((c, i) => { latest[c] = values[i]; dates[c] = D; });
  return { latest, dates };
}

describe("T-0120: per-country slope chips", () => {
  it("NOR shows a 3s10s chip and no 2s10s", () => {
    const { latest, dates } = fresh("NOR", [4.0, 4.1, 4.2, 4.3]);
    const b = countryBond("NOR", latest, dates, NOW);
    expect(b.curve.map((c) => c.label)).toEqual(["3Y", "5Y", "7Y", "10Y"]);
    expect(b.slopes.map((s) => [s.label, s.bp])).toEqual([["3s10s", 30]]);
    render(<CountryBondCurve iso="NOR" bond={b} />);
    expect(screen.getByText("3s10s")).toBeTruthy();
    expect(screen.queryByText("2s10s")).toBeNull();
    expect(screen.queryByText("10s30s")).toBeNull();
  });

  it("only CAN shows 10s30s, with a tip saying it is 10s-long", () => {
    const withLong = Object.keys(FB_CARD_COUNTRY).filter((iso) => ["CAN", "SWE", "AUS", "NOR", "ESP"].includes(iso))
      .filter((iso) => {
        const { latest, dates } = fresh(iso, fbCardCodes(iso).map((_, i) => 3 + i / 10));
        return countryBond(iso, latest, dates, NOW).slopes.some((s) => s.label === "10s30s");
      });
    expect(withLong).toEqual(["CAN"]);
    const { latest, dates } = fresh("CAN", [3.0, 3.1, 3.2, 3.3, 3.5, 3.9]);
    const b = countryBond("CAN", latest, dates, NOW);
    expect(b.slopes.map((s) => [s.label, s.bp])).toEqual([["2s10s", 50], ["10s30s", 40]]);
    expect(b.slopes[1].tip).toContain("10s-long");
  });

  it("SWE and AUS show 2s10s only", () => {
    for (const iso of ["SWE", "AUS"]) {
      const { latest, dates } = fresh(iso, [2.0, 2.2, 2.4, 2.5]);
      expect(countryBond(iso, latest, dates, NOW).slopes.map((s) => s.label)).toEqual(["2s10s"]);
    }
  });

  it("the daily 10Y headline renders", () => {
    const { latest, dates } = fresh("NOR", [4.0, 4.1, 4.2, 4.3]);
    const b = countryBond("NOR", latest, dates, NOW);
    expect(b.tenYear.daily).toBe(true);
    expect(b.tenYear.code).toBe("FB_NO_10Y");
    render(<CountryStatCards ticHistory={null} cds={NO_CDS} countryYield={b.tenYear.value} yieldSource={b.tenYear} />);
    expect(screen.getByText("DAILY · CMT")).toBeTruthy();
    expect(screen.getAllByText(/4\.30/).length).toBeGreaterThan(0);
  });

  it("AUS tolerates the RBA's weekly lag (12 days), others go stale after 4", () => {
    const old = "2026-10-12";
    const au = fresh("AUS", [3.4, 3.5, 3.6, 4.1]);
    Object.keys(au.dates).forEach((k) => { au.dates[k] = old; });
    expect(countryBond("AUS", au.latest, au.dates, NOW).tenYear.daily).toBe(true);
    const se = fresh("SWE", [2.0, 2.2, 2.4, 2.5]);
    Object.keys(se.dates).forEach((k) => { se.dates[k] = old; });
    expect(countryBond("SWE", se.latest, se.dates, NOW).tenYear.daily).toBe(false);
  });
});

describe("T-0132: ESP card", () => {
  it("falls back to the monthly OECD ES 10Y with the MONTHLY badge, 3s10s, no 10s30s", () => {
    const b = countryBond("ESP", { [SOVEREIGN_YIELD_CODES.ESP]: 3.2 }, {}, NOW);
    expect(b.tenYear.code).toBe(SOVEREIGN_YIELD_CODES.ESP); // the OECD monthly ES 10Y, pinned by T-0122
    expect(b.tenYear.badge).toBe("MONTHLY");
    expect(b.slopes.map((s) => s.label)).toEqual(["3s10s"]);
    expect(b.slopes[0].bp).toBeNull();
    render(<CountryStatCards ticHistory={null} cds={NO_CDS} countryYield={3.2} yieldSource={b.tenYear} />);
    expect(screen.getAllByText(/MONTHLY/).length).toBeGreaterThan(0);
  });

  it("daily ES: 3/5/10/15Y curve and a 3s10s in bp", () => {
    const { latest, dates } = fresh("ESP", [2.4, 2.8, 3.3, 3.7]);
    const b = countryBond("ESP", latest, dates, NOW);
    expect(b.curve.map((c) => c.code)).toEqual(["FB_ES_03Y", "FB_ES_05Y", "FB_ES_10Y", "FB_ES_15Y"]);
    expect(b.slopes.map((s) => [s.label, s.bp])).toEqual([["3s10s", 90]]);
    expect(b.tenYear.daily).toBe(true);
  });
});

describe("T-0131: EA is a benchmark panel, not a country", () => {
  const codes = (k) => [2, 5, 7, 10, 30].map((t) => `FB_EA_${k}_${String(t).padStart(2, "0")}Y`);

  it("never a card country", () => {
    expect(Object.values(FB_CARD_COUNTRY)).not.toContain("EA");
    expect(Object.keys(FB_CARD_COUNTRY)).not.toContain("EA");
    expect(Object.keys(FB_CARD_COUNTRY)).not.toContain("EMU");
  });

  it("renders both curves and the AAA 2s10s / 10s30s", () => {
    const latest = {}, dates = {};
    codes("AAA").forEach((c, i) => { latest[c] = [2.0, 2.2, 2.4, 2.6, 3.0][i]; dates[c] = D; });
    codes("ALL").forEach((c, i) => { latest[c] = [2.1, 2.4, 2.7, 3.0, 3.5][i]; dates[c] = D; });
    const ea = eaBenchmark(latest, dates, NOW);
    expect(ea.curves.map((c) => c.points.map((p) => p.code))).toEqual([codes("AAA"), codes("ALL")]);
    expect(ea.slopes.map((s) => [s.label, s.bp])).toEqual([["AAA 2s10s", 60], ["AAA 10s30s", 40]]);
    expect(ea.attribution).toBe(`Source: ECB, updated ${D}`);
    render(<EaBenchmarkPanel ea={ea} />);
    expect(screen.getByTestId("ea-curve-AAA")).toBeTruthy();
    expect(screen.getByTestId("ea-curve-ALL")).toBeTruthy();
    expect(screen.getByTestId("ea-slope-AAA 2s10s").textContent).toBe("+60bp");
    expect(screen.getByTestId("ea-slope-AAA 10s30s").textContent).toBe("+40bp");
  });

  it("a stale or missing leg dashes the slope", () => {
    const latest = { FB_EA_AAA_02Y: 2.0, FB_EA_AAA_10Y: 2.6 };
    const dates = { FB_EA_AAA_02Y: "2026-10-10", FB_EA_AAA_10Y: D };
    const ea = eaBenchmark(latest, dates, NOW);
    expect(ea.slopes.map((s) => s.bp)).toEqual([null, null]);
    render(<EaBenchmarkPanel ea={ea} />);
    expect(screen.getByTestId("ea-slope-AAA 2s10s").textContent).toBe("—");
  });
});
