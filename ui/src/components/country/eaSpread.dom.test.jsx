// @vitest-environment jsdom
/**
 * Sentinel D-0117: "Spread to EA AAA 10Y" readout on the six euro-area member
 * cards (T-0153..T-0160). Display only; nothing here is scored.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { EaBenchmarkPanel } from "../foreignBonds/EaBenchmarkPanel";
import { FB_CARD_COUNTRY, SOVEREIGN_YIELD_CODES, countryBond, eaBenchmark, fbCardCodes } from "../../lib/constants";
import { parseRoute } from "../../lib/countryRoute";
import {
  EA_AAA_10Y, EA_BENCHMARK_HREF, EA_SPREAD_MEMBERS, eaSpreadBp, eaSpreadFetchCodes, eaSpreadReadout,
} from "../../lib/eaSpread";
import { EaSpreadLine } from "./EaSpreadLine";

afterEach(cleanup);

const NOW = new Date("2026-10-22T12:00:00Z");
const D = "2026-10-21";
const ALL = "FB_EA_ALL_10Y";

/** TARGET-ish business days (Mon-Fri) from `from` to `to`, inclusive. */
function days(from, to) {
  const out = [];
  for (let t = Date.parse(`${from}T00:00:00Z`); t <= Date.parse(`${to}T00:00:00Z`); t += 86400000) {
    const wd = new Date(t).getUTCDay();
    if (wd !== 0 && wd !== 6) out.push(new Date(t).toISOString().slice(0, 10));
  }
  return out;
}
const pts = (dateList, f) => dateList.map((date, i) => ({ date, value: f(i, date) }));

/** A card plus its series map: every code dated `date` with `values`. */
function card(iso, values, date, extra = {}) {
  const latest = {}, dates = {}, series = {};
  fbCardCodes(iso).forEach((c, i) => { latest[c] = values[i]; dates[c] = date; series[c] = [{ date, value: values[i] }]; });
  for (const [code, list] of Object.entries(extra)) {
    if (!list.length) continue;
    series[code] = list;
    latest[code] = list.at(-1).value;
    dates[code] = list.at(-1).date;
  }
  return { bond: countryBond(iso, latest, dates, NOW), series };
}
const FR = (ten) => [2.1, 2.5, 2.8, ten, 3.9];
const DE = (ten) => [1.9, 2.1, 2.3, ten, 3.0];
const ES = (ten) => [2.2, 2.6, ten, 3.6];
const IT = (ten) => [2.3, 2.8, ten, 4.4];

// A fresh AAA series: every business day of Sep and Oct to 10-21.
const AAA_SEP = pts(days("2026-09-01", "2026-09-30"), (i) => 2.60 + (i % 5) * 0.01);
const AAA_OCT = pts(days("2026-10-01", D), () => 2.705);
const AAA = [...AAA_SEP, ...AAA_OCT];
const sepMean = AAA_SEP.reduce((s, p) => s + p.value, 0) / AAA_SEP.length;

describe("T-0153: formula", () => {
  it("FR 3.412 against AAA 2.705 on the same date is +71 bp", () => {
    const { bond, series } = card("FRA", FR(3.412), D, { [EA_AAA_10Y]: AAA });
    const r = eaSpreadReadout("FRA", bond, series, NOW);
    expect(r).toMatchObject({ bp: 71, asOf: D, monthly: false });
    render(<EaSpreadLine readout={r} />);
    expect(screen.getByTestId("ea-spread").textContent).toContain("Spread to EA AAA 10Y: +71 bp (as of 2026-10-21)");
  });

  it("DEU below AAA carries a minus sign", () => {
    const { bond, series } = card("DEU", DE(2.60), D, { [EA_AAA_10Y]: AAA });
    const r = eaSpreadReadout("DEU", bond, series, NOW);
    expect(r.bp).toBe(-11);
    render(<EaSpreadLine readout={r} />);
    expect(screen.getByTestId("ea-spread-value").textContent).toBe("\u221211 bp");
    expect(r.tip).toMatch(/DEU is itself in the AAA basket/);
  });

  it("a half bp rounds away from zero, on both signs", () => {
    expect(eaSpreadBp(3.41, 2.705)).toBe(71);   // +70.5
    expect(eaSpreadBp(2.65, 2.705)).toBe(-6);   // -5.5
    expect(eaSpreadBp(2.705, 2.705)).toBe(0);
  });
});

describe("T-0154: daily alignment", () => {
  const at = (aaa) => {
    const { bond, series } = card("FRA", FR(3.412), D, { [EA_AAA_10Y]: aaa });
    return eaSpreadReadout("FRA", bond, series, NOW);
  };
  it("a 0-day and a 3-day gap render", () => {
    expect(at([{ date: D, value: 2.705 }]).bp).toBe(71);
    expect(at([{ date: "2026-10-18", value: 2.705 }, { date: "2026-10-22", value: 2.0 }])).toMatchObject({ bp: 71, asOf: D });
  });
  it("a 4-day gap is a dash", () => {
    const r = at([{ date: "2026-10-17", value: 2.705 }, { date: "2026-10-22", value: 2.0 }]);
    expect(r.bp).toBeNull();
    render(<EaSpreadLine readout={r} />);
    expect(screen.getByTestId("ea-spread-value").textContent).toBe("—");
  });
  it("uses the latest AAA on or before the member date, not a later point", () => {
    expect(at([{ date: "2026-10-20", value: 2.70 }, { date: "2026-10-22", value: 2.90 }]).bp).toBe(71);
  });
});

describe("T-0155: monthly alignment", () => {
  it("GRC Sep pairs with the September AAA mean, never the daily latest", () => {
    const { bond, series } = card("GRC", [], D, { FB_GR_10Y_ECB_M: [{ date: "2026-09-30", value: 3.80 }], [EA_AAA_10Y]: AAA });
    const r = eaSpreadReadout("GRC", bond, series, NOW);
    const expected = Math.round((3.80 - sepMean) * 100);
    const naive = Math.round((3.80 - 2.705) * 100);
    expect(Math.abs(expected - naive)).toBeGreaterThanOrEqual(5);
    expect(r).toMatchObject({ bp: expected, monthly: true, asOf: "Sep 2026" });
    render(<EaSpreadLine readout={r} />);
    expect(screen.getByTestId("ea-spread-badge").textContent).toBe("MONTHLY");
    expect(screen.getByTestId("ea-spread").textContent).toContain("(as of Sep 2026)");
  });
  it("a month with 9 AAA observations is a dash", () => {
    const nine = [...AAA_SEP.slice(0, 9), ...AAA_OCT];
    const { bond, series } = card("GRC", [], D, { FB_GR_10Y_ECB_M: [{ date: "2026-09-30", value: 3.80 }], [EA_AAA_10Y]: nine });
    expect(eaSpreadReadout("GRC", bond, series, NOW).bp).toBeNull();
  });
});

describe("T-0156: fallback switch (ESP)", () => {
  const irs = { FB_ES_10Y_ECB_M: [{ date: "2026-09-30", value: 3.30 }] };
  it("daily fresh: a daily readout, no badge", () => {
    const { bond, series } = card("ESP", ES(3.10), D, { ...irs, [EA_AAA_10Y]: AAA });
    const r = eaSpreadReadout("ESP", bond, series, NOW);
    expect(r).toMatchObject({ bp: 40, monthly: false, asOf: D });
    render(<EaSpreadLine readout={r} />);
    expect(screen.queryByTestId("ea-spread-badge")).toBeNull();
  });
  it("daily stale: the ECB_M fallback, MONTHLY", () => {
    const { bond, series } = card("ESP", ES(3.10), "2026-10-01", { ...irs, [EA_AAA_10Y]: AAA });
    expect(bond.tenYear.code).toBe("FB_ES_10Y_ECB_M");
    expect(eaSpreadReadout("ESP", bond, series, NOW)).toMatchObject({ bp: Math.round((3.30 - sepMean) * 100), monthly: true, asOf: "Sep 2026" });
  });
  it("then the OECD monthly IRLTLT, MONTHLY", () => {
    const oecd = SOVEREIGN_YIELD_CODES.ESP;
    expect(eaSpreadFetchCodes("ESP")).toEqual([EA_AAA_10Y, oecd]);
    const { bond, series } = card("ESP", ES(3.10), "2026-10-01",
      { FB_ES_10Y_ECB_M: [{ date: "2026-07-31", value: 3.3 }], [oecd]: [{ date: "2026-09-01", value: 3.25 }], [EA_AAA_10Y]: AAA });
    expect(bond.tenYear.code).toBe(oecd);
    expect(eaSpreadReadout("ESP", bond, series, NOW)).toMatchObject({ bp: Math.round((3.25 - sepMean) * 100), monthly: true, asOf: "Sep 2026" });
  });
  it("everything stale: a dash", () => {
    const { bond, series } = card("ESP", ES(3.10), "2026-10-01", { FB_ES_10Y_ECB_M: [{ date: "2026-07-31", value: 3.3 }], [EA_AAA_10Y]: AAA });
    const r = eaSpreadReadout("ESP", bond, series, NOW);
    expect(r.bp).toBeNull();
    expect(r.reason).toBe("member 10Y unavailable");
  });
});

describe("T-0157: a stale benchmark dashes all six", () => {
  const stale = AAA.filter((p) => p.date <= "2026-10-14");
  const fixtures = {
    FRA: card("FRA", FR(3.4), D, { [EA_AAA_10Y]: stale }),
    DEU: card("DEU", DE(2.6), D, { [EA_AAA_10Y]: stale }),
    ESP: card("ESP", ES(3.1), D, { [EA_AAA_10Y]: stale }),
    ITA: card("ITA", IT(3.9), "2026-09-30", { [EA_AAA_10Y]: stale }),
    GRC: card("GRC", [], D, { FB_GR_10Y_ECB_M: [{ date: "2026-09-30", value: 3.8 }], [EA_AAA_10Y]: stale }),
    PRT: card("PRT", [], D, { FB_PT_10Y_ECB_M: [{ date: "2026-09-30", value: 3.2 }], [EA_AAA_10Y]: stale }),
  };
  for (const [iso, { bond, series }] of Object.entries(fixtures)) {
    it(`${iso}: dash, "benchmark unavailable"`, () => {
      expect(bond.tenYear.value).not.toBeNull();
      expect(eaSpreadReadout(iso, bond, series, NOW)).toMatchObject({ bp: null, reason: "benchmark unavailable" });
    });
  }
  it("fresh again: ITA (monthly, BdI) reads against the Sep mean", () => {
    const { bond, series } = card("ITA", IT(3.9), "2026-09-30", { [EA_AAA_10Y]: AAA });
    expect(eaSpreadReadout("ITA", bond, series, NOW)).toMatchObject({ bp: Math.round((3.9 - sepMean) * 100), monthly: true });
  });
});

describe("T-0158: membership", () => {
  it("exactly the six members", () => {
    expect([...EA_SPREAD_MEMBERS].sort()).toEqual(["DEU", "ESP", "FRA", "GRC", "ITA", "PRT"]);
  });
  it("CAN, GBR, JPN, SWE, NOR and AUS get no line and no link", () => {
    for (const iso of ["CAN", "GBR", "JPN", "SWE", "NOR", "AUS"]) {
      const { bond, series } = card(iso, [2, 2, 2, 2, 2], D, { [EA_AAA_10Y]: AAA });
      expect(eaSpreadReadout(iso, bond, series, NOW)).toBeNull();
      expect(eaSpreadFetchCodes(iso)).toEqual([]);
      const { container } = render(<EaSpreadLine readout={null} />);
      expect(container.innerHTML).toBe("");
      cleanup();
    }
  });
  it("EA is still not a country (T-0131)", () => {
    expect(Object.keys(FB_CARD_COUNTRY)).not.toContain("EA");
    expect(EA_SPREAD_MEMBERS).not.toContain("EA");
  });
});

describe("T-0159: the benchmark is AAA, never all-issuer", () => {
  it("ALL differs; the readout matches AAA", () => {
    const allSeries = AAA.map((p) => ({ ...p, value: p.value + 0.5 }));
    const { bond, series } = card("FRA", FR(3.412), D, { [EA_AAA_10Y]: AAA, [ALL]: allSeries });
    expect(eaSpreadReadout("FRA", bond, series, NOW).bp).toBe(71);
    expect(eaSpreadFetchCodes("FRA")).not.toContain(ALL);
  });
});

describe("T-0160: the EA benchmark link", () => {
  it("resolves to the Foreign Bonds tab, and #ea-benchmark exists there", () => {
    expect(parseRoute(EA_BENCHMARK_HREF)).toMatchObject({ tab: "FOREIGN-BONDS", view: "ea-benchmark" });
    const { container } = render(<EaBenchmarkPanel ea={eaBenchmark({}, {}, NOW)} />);
    expect(container.querySelector("#ea-benchmark")).not.toBeNull();
  });
  it("shows on all six member cards, even when the readout is a dash", () => {
    for (const iso of EA_SPREAD_MEMBERS) {
      const { bond, series } = card(iso, [], D, {});
      const r = eaSpreadReadout(iso, bond, series, NOW);
      expect(r.bp).toBeNull();
      render(<EaSpreadLine readout={r} />);
      expect(screen.getByTestId("ea-spread-link").getAttribute("href")).toBe(EA_BENCHMARK_HREF);
      cleanup();
    }
  });
});
