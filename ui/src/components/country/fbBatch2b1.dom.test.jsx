// @vitest-environment jsdom
/**
 * Sentinel D-0116 (FB batch 2b-1): Poland (auction yields), Italy (BMK monthly)
 * and the ECB IRS monthly 10Y fallback, with GR/PT cards that have no curve.
 * Display only.
 */
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { SOVEREIGN_YIELD_CODES, countryBond, fbCardCodes, fbCardFetchCodes } from "../../lib/constants";
import { CountryBondCurve } from "./CountryBondCurve";

afterEach(cleanup);

const NOW = new Date("2026-10-22T12:00:00Z");

function fresh(iso, values, date) {
  const latest = {}, dates = {};
  fbCardCodes(iso).forEach((c, i) => { latest[c] = values[i]; dates[c] = date; });
  return { latest, dates };
}

describe("T-0145: monthly badges, no-curve cards", () => {
  it("GRC and PRT: 10Y from ECB IRS, MONTHLY, no curve, no slopes", () => {
    for (const [iso, cc] of [["GRC", "GR"], ["PRT", "PT"]]) {
      expect(fbCardCodes(iso)).toEqual([]);
      expect(fbCardFetchCodes(iso)).toContain(`FB_${cc}_10Y_ECB_M`);
      const code = `FB_${cc}_10Y_ECB_M`;
      const b = countryBond(iso, { [code]: 3.8 }, { [code]: "2026-09-30" }, NOW);
      expect(b.tenYear).toMatchObject({ value: 3.8, badge: "MONTHLY", daily: false, code });
      expect(b.showCurve).toBe(false);
      expect(b.slopes).toEqual([]);
      expect(b.sourceKey).toBe("ecb_irs_monthly");
      const { container } = render(<CountryBondCurve iso={iso} bond={b} />);
      expect(container.innerHTML).toBe("");
      cleanup();
    }
  });

  it("GRC with a stale IRS shows a dash, never zero", () => {
    const b = countryBond("GRC", { FB_GR_10Y_ECB_M: 3.8 }, { FB_GR_10Y_ECB_M: "2026-07-31" }, NOW);
    expect(b.tenYear.value).toBeNull();
  });

  it("ITA: BMK monthly is MONTHLY with 3s10s and 10s30s", () => {
    const { latest, dates } = fresh("ITA", [3.1, 3.3, 3.9, 4.6], "2026-09-30");
    const b = countryBond("ITA", latest, dates, NOW);
    expect(b.curve.map((c) => c.label)).toEqual(["3Y", "5Y", "10Y", "30Y"]);
    expect(b.tenYear).toMatchObject({ value: 3.9, badge: "MONTHLY", code: "FB_IT_10Y" });
    expect(b.slopes.map((s) => [s.label, s.bp])).toEqual([["3s10s", 80], ["10s30s", 70]]);
    expect(b.showCurve).toBe(true);
  });

  it("ITA past 45 days falls to ECB IRS, then to IRLTLT", () => {
    const { latest, dates } = fresh("ITA", [3.1, 3.3, 3.9, 4.6], "2026-08-31");
    const irs = countryBond("ITA", { ...latest, FB_IT_10Y_ECB_M: 4.0 }, { ...dates, FB_IT_10Y_ECB_M: "2026-09-30" }, NOW);
    expect(irs.tenYear).toMatchObject({ value: 4.0, code: "FB_IT_10Y_ECB_M", badge: "MONTHLY" });
    const oecd = countryBond("ITA", { ...latest, [SOVEREIGN_YIELD_CODES.ITA]: 3.7 }, dates, NOW);
    expect(oecd.tenYear).toMatchObject({ value: 3.7, code: SOVEREIGN_YIELD_CODES.ITA });
  });

  it("POL: AS OF LAST AUCTION badge with the auction date, 2s10s only", () => {
    const { latest, dates } = fresh("POL", [5.0, 5.8, 6.2], "2026-10-08");
    const b = countryBond("POL", latest, dates, NOW);
    expect(b.tenYear.badge).toBe("AS OF LAST AUCTION 2026-10-08");
    expect(b.tenYear.daily).toBe(false);
    expect(b.slopes.map((s) => [s.label, s.bp])).toEqual([["2s10s", 120]]);
  });

  it("POL past 40 days uses ECB IRS", () => {
    const { latest, dates } = fresh("POL", [5.0, 5.8, 6.2], "2026-09-01");
    const b = countryBond("POL", { ...latest, FB_PL_10Y_ECB_M: 5.6 }, { ...dates, FB_PL_10Y_ECB_M: "2026-09-30" }, NOW);
    expect(b.tenYear).toMatchObject({ value: 5.6, code: "FB_PL_10Y_ECB_M", badge: "MONTHLY" });
  });

  it("ESP: stale BdE daily falls to ECB IRS before IRLTLT", () => {
    const { latest, dates } = fresh("ESP", [3.0, 3.1, 3.2, 3.6], "2026-10-01");
    const b = countryBond("ESP", { ...latest, FB_ES_10Y_ECB_M: 3.5, [SOVEREIGN_YIELD_CODES.ESP]: 3.4 },
      { ...dates, FB_ES_10Y_ECB_M: "2026-09-30" }, NOW);
    expect(b.tenYear).toMatchObject({ value: 3.5, code: "FB_ES_10Y_ECB_M" });
    const fresh10 = fresh("ESP", [3.0, 3.1, 3.2, 3.6], "2026-10-21");
    expect(countryBond("ESP", { ...fresh10.latest, FB_ES_10Y_ECB_M: 3.5 }, fresh10.dates, NOW).tenYear.code)
      .toBe("FB_ES_10Y");
  });
});
