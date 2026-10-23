// @vitest-environment jsdom
/**
 * Sentinel D-0111 (vault:D-0057): FOREIGN-BONDS is MARKETS with other inputs.
 *
 * AC-3: same component, same section order (DataConfidence -> StatCard grid ->
 *       chart panel with toggles, % CHANGE and ranges -> spread strip ->
 *       source footer), same interactions, hash route and Back.
 * AC-5: FIT / CMT / MON named in the tips.
 * §7.7: a spread with a stale leg is hidden, not quoted.
 * D-0112: 20 cards, all daily: France from the Banque de France TEC replaces
 *       the four NO SOURCE cells; the footer reads "Source: Banque de France,
 *       updated <date>".
 * D-0112 amendment 1 (T-0112 addendum 2): the monthly OECD FR 10Y (FRED) is gone from
 *       this surface - no fallback card, no monthly OAT-Bund spread, and the
 *       tab does not request it. TEC10 is the only FR 10Y here.
 *
 * Every network call is stubbed.
 */
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "../App";
import * as constants from "../lib/constants";
import {
  FOREIGN_BOND_CODES, FOREIGN_BOND_METRICS, SOVEREIGN_YIELD_CODES, TABS, foreignBondSpreads,
  oatBundDailySpread,
} from "../lib/constants";
import { parseRoute } from "../lib/countryRoute";
import { ForeignBondsTab } from "./ForeignBondsTab";

let freshness;
let omit;
// Spelled through the shared map: constants.test.js forbids the literal codes
// anywhere but constants.js.
const FRA = SOVEREIGN_YIELD_CODES.FRA;
const DEU = SOVEREIGN_YIELD_CODES.DEU;

function timeseries(url) {
  const m = /metric_codes=([^&]*)/.exec(url);
  const codes = m ? decodeURIComponent(m[1]).split(",").filter(Boolean) : [];
  const level = (code) => ({
    FB_DE_02Y: 3.08, FB_DE_10Y: 3.47, FB_DE_30Y: 3.86,
    FB_GB_02Y: 4.72, FB_GB_10Y: 5.384, FB_JP_10Y: 2.927, FB_JP_30Y: 3.992,
    FB_FR_02Y: 2.22, FB_FR_10Y: 3.35, FB_FR_30Y: 4.26,
    DGS10: 4.1, DGS2: 3.6, [FRA]: 4.44, [DEU]: 3.5,
  }[code] ?? 2.5);
  return codes.filter((code) => !omit.has(code)).flatMap((code) => [
    { metric_code: code, date: "2026-09-21T00:00:00", value: level(code) - 0.1 },
    { metric_code: code, date: "2026-10-20T00:00:00", value: level(code) },
  ]);
}

function stubResponse(url) {
  if (url.includes("/timeseries")) return timeseries(url);
  if (url.includes("/health")) return { status: "healthy" };
  if (url.includes("/stats")) return { timeseries_records: 1, data_latest: "2026-10-20T00:00:00" };
  if (url.includes("/freshness")) return freshness;
  return {};
}

const src = (key, status = "ok") => ({ key, label: key, status, age_days: 1, max_age_days: 5, note: "" });
const allFresh = () => ({
  counts: {},
  sources: ["foreign_bonds_de", "foreign_bonds_gb", "foreign_bonds_jp", "foreign_bonds_fr", "sovereign_yields",
    "treasury_yields", "oil", "dollar_index", "gold_price"].map((k) => src(k)),
});

beforeEach(() => {
  freshness = allFresh();
  omit = new Set();
  vi.stubGlobal("fetch", vi.fn((url) => Promise.resolve({
    ok: true, status: 200, statusText: "OK",
    json: () => Promise.resolve(stubResponse(String(url))),
    text: () => Promise.resolve(""),
  })));
  window.location.hash = "";
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.location.hash = "";
});

const settle = (container) => waitFor(() => {
  expect(container.textContent).toContain("SPREAD");
  expect(container.textContent).toContain("DATA CONFIDENCE");
});

/** The tab body's top-level sections, named by what each one is. */
function sections(body) {
  return [...body.children].map((el) => {
    const t = el.textContent;
    if (el.dataset?.testid === "ea-benchmark-panel") return "ea";
    if (t.includes("DATA CONFIDENCE")) return "confidence";
    if (el.style.display === "grid") return "cards";
    if (t.includes("% CHANGE")) return "chart";
    if (t.startsWith("SPREAD")) return "spreads";
    if (t.startsWith("Source:")) return "footer";
    return `?${t.slice(0, 20)}`;
  });
}

const FR_DAILY = [2, 5, 7, 10, 30].map((t) => `FB_FR_${String(t).padStart(2, "0")}Y`);

describe("§8 / AC-5 / D-0112: the twenty cells", () => {
  it("renders 20 daily cards: DE, GB, JP and FR from the Banque de France", async () => {
    const { container } = render(<ForeignBondsTab />);
    await settle(container);
    const grid = [...container.querySelectorAll("div")].find((d) => d.style.display === "grid");
    // Sentinel D-0115: batch 2a adds CA (6), SE, AU, NO and ES (4 each) after FR.
    expect(grid.children.length).toBe(49);
    expect(FOREIGN_BOND_METRICS.length).toBe(49);
    expect(FOREIGN_BOND_METRICS.filter((m) => m.code?.startsWith("FB_")).length).toBe(49);
    expect(grid.style.gridTemplateColumns).toBe("repeat(5, 1fr)");

    const cards = [...grid.children];
    const label = (c) => c.querySelector("span").textContent;
    // Country rows in order DE, GB, JP, FR; tenors 2/5/7/10/30 across.
    expect(cards.map(label)).toEqual([
      "DE 2Y", "DE 5Y", "DE 7Y", "DE 10Y", "DE 30Y",
      "GB 2Y", "GB 5Y", "GB 7Y", "GB 10Y", "GB 30Y",
      "JP 2Y", "JP 5Y", "JP 7Y", "JP 10Y", "JP 30Y",
      "FR 2Y", "FR 5Y", "FR 7Y", "FR 10Y", "FR 30Y",
      "CA 2Y", "CA 3Y", "CA 5Y", "CA 7Y", "CA 10Y", "CA 30Y",
      "SE 2Y", "SE 5Y", "SE 7Y", "SE 10Y",
      "AU 2Y", "AU 3Y", "AU 5Y", "AU 10Y",
      "NO 3Y", "NO 5Y", "NO 7Y", "NO 10Y",
      "ES 3Y", "ES 5Y", "ES 10Y", "ES 15Y",
      // Sentinel D-0116: batch 2b-1 adds PL (auction) and IT (monthly BMK).
      "PL 2Y", "PL 5Y", "PL 10Y",
      "IT 3Y", "IT 5Y", "IT 10Y", "IT 30Y",
    ]);
    expect(cards[3].textContent).toContain("3.47%");
    expect(cards[13].textContent).toContain("2.93%");

    const fr = cards.slice(15, 20);
    // No NO SOURCE cell is left, and the daily French 10Y is shown, not the monthly.
    expect(fr.filter((c) => c.textContent.includes("—")).length).toBe(0);
    expect(fr[0].textContent).toContain("2.22%");
    expect(fr[3].textContent).toContain("3.35%");
    expect(fr[4].textContent).toContain("4.26%");
    expect(cards.filter((c) => c.textContent.includes("MONTHLY")).length).toBe(0);
    expect(container.textContent).toContain("Source: Banque de France, updated 2026-10-20");
  });

  it("with no daily French data, every FR cell is \u2014 and nothing monthly stands in", async () => {
    omit = new Set(FR_DAILY);
    const { container } = render(<ForeignBondsTab />);
    await settle(container);
    const grid = [...container.querySelectorAll("div")].find((d) => d.style.display === "grid");
    const cards = [...grid.children];
    expect(cards.length).toBe(49);
    const fr = cards.slice(15, 20);
    expect(fr[3].querySelector("span").textContent).toBe("FR 10Y");
    expect(fr.filter((c) => c.textContent.includes("\u2014")).length).toBe(5);
    expect(container.textContent).not.toContain("MONTHLY");
    expect(container.textContent).not.toContain("4.44%");
    expect(container.textContent).toContain("Source: Banque de France, not yet available");
  });

  it("T-0112 add. 2: the monthly OECD FR 10Y is not on this surface at all", () => {
    expect(constants.FR_10Y_MONTHLY_FALLBACK).toBeUndefined();
    expect(FOREIGN_BOND_CODES).not.toContain(FRA);
    expect(FOREIGN_BOND_METRICS.filter((m) => m.label === "FR 10Y").map((m) => m.code)).toEqual(["FB_FR_10Y"]);
    const labels = foreignBondSpreads({ [FRA]: 4.44, [DEU]: 3.5, FB_FR_10Y: 3.35, FB_DE_10Y: 3.47 }).map((s) => s.label);
    expect(labels).toEqual(["OAT\u2013Bund 10Y (daily, BdF TEC \u2212 Bundesbank)"]);
  });

  it("T-0112 add. 2: the tab never requests the monthly FR series", async () => {
    const { container } = render(<ForeignBondsTab />);
    await settle(container);
    const urls = fetch.mock.calls.map((c) => String(c[0])).filter((u) => u.includes("/timeseries"));
    expect(urls.length).toBeGreaterThan(0);
    for (const u of urls) expect(decodeURIComponent(u)).not.toContain(FRA);
  });

  it("every tip names what the number is and where it comes from", () => {
    for (const m of FOREIGN_BOND_METRICS) {
      expect(m.scored).toBe(false);
      if (m.code.startsWith("FB_DE_")) {
        expect(m.tip).toContain("FIT");
        expect(m.tip).toMatch(/BBSIS\/D\.I\.ZST\.ZI\.EUR\.S1311\.B\.A604\.R\d\dXX/);
      } else if (m.code.startsWith("FB_GB_")) {
        expect(m.tip).toContain("FIT");
        expect(m.tip).toContain("4. spot curve");
      } else if (m.code.startsWith("FB_JP_")) {
        expect(m.tip).toContain("CMT");
        expect(m.tip).toContain("jgbcm.csv");
      } else if (m.code.startsWith("FB_CA_")) {
        expect(m.tip).toContain("Bank of Canada");
        expect(m.tip).toMatch(/BD\.CDN\.(\d+YR|LONG)\.DQ\.YLD/);
      } else if (m.code.startsWith("FB_SE_")) {
        expect(m.tip).toMatch(/Riksbank SWEA series SEGVB\d+YC/);
      } else if (m.code.startsWith("FB_AU_")) {
        expect(m.kind).toBe("CMT");
        expect(m.tip).toMatch(/RBA statistical table F2.*FCMYGBAG\d+D/);
      } else if (m.code.startsWith("FB_NO_")) {
        expect(m.kind).toBe("CMT");
        expect(m.tip).toContain("Norges Bank");
      } else if (m.code.startsWith("FB_ES_")) {
        expect(m.tip).toContain("Banco de España");
        expect(m.tip).toMatch(/D_G0B1F0Z[NOPQ]/);
      } else if (m.code.startsWith("FB_PL_")) {
        // Sentinel D-0116 (T-0137): auction yields, labelled as such.
        expect(m.tip).toContain("Ministry of Finance");
        expect(m.tip).toMatch(/last auction/);
      } else if (m.code.startsWith("FB_IT_")) {
        // Sentinel D-0116 (T-0139): monthly benchmark BTP yields.
        expect(m.tip).toContain("Banca d'Italia");
        expect(m.tip).toMatch(/BMK0100/);
      } else {
        expect(m.code).toMatch(/^FB_FR_\d\dY$/);
        expect(m.kind).toBe("CMT");
        expect(m.tip).toContain("Banque de France");
        expect(m.tip).toMatch(/FM\.D\.FR\.EUR\.FR2\.BB\.FRMOYTEC\d+\.HSTA/);
      }
    }
  });

  it("every cell has a chart toggle", async () => {
    const { container } = render(<ForeignBondsTab />);
    await settle(container);
    const labels = [...container.querySelectorAll("button")].map((b) => b.textContent);
    expect(labels.filter((l) => /^(DE|GB|JP|FR) \d+Y$/.test(l)).length).toBe(20);
    expect(labels).toContain("FR 2Y");
    expect(labels).toContain("FR 10Y");
  });
});

describe("§7.7: the spread strip", () => {
  it("shows every spread when both legs are current", async () => {
    const { container } = render(<ForeignBondsTab />);
    await settle(container);
    for (const label of ["Bund–UST 10Y", "Gilt–UST 10Y", "JGB–UST 10Y", "Gilt–Bund 10Y",
      "Gilt–Bund 2Y", "DE 10Y–2Y", "GB 10Y–2Y", "JP 30Y–10Y", "OAT–Bund 10Y (daily, BdF TEC − Bundesbank)"]) {
      expect(screen.getByText(label)).toBeTruthy();
    }
    expect(screen.queryByText("OAT–Bund 10Y (monthly)")).toBeNull();
    // FB_DE_10Y 3.47 - DGS10 4.10
    expect(container.textContent).toContain("-0.63pp");
    // No monthly OAT-Bund (4.44 - 3.50) any more (D-0112 amendment 1).
    expect(container.textContent).not.toContain("+0.94pp");
    // OAT-Bund daily, in pp like the rest of the strip (D-0113 follow-up):
    // FB_FR_10Y 3.35 - FB_DE_10Y 3.47
    expect(container.textContent).toContain("-0.12pp");
    // The strip is in pp; only the EA benchmark panel's slopes are in bp.
    const strip = [...container.querySelectorAll("div")].find((d) => d.textContent.startsWith("SPREAD") && d.children.length > 1);
    expect(strip.textContent).not.toMatch(/\dbp/);
  });

  // D-0113 follow-up (Trinity): a stale leg keeps the spread in place and
  // shows "—", as the OAT–Bund already did; it no longer disappears.
  it("shows — for a spread whose leg is stale, and keeps the rest", async () => {
    freshness = allFresh();
    freshness.sources.find((s) => s.key === "foreign_bonds_gb").status = "stale";
    const { container } = render(<ForeignBondsTab />);
    await settle(container);
    // One strip entry: the strip's direct child that carries this label.
    const strip = () => [...container.querySelectorAll("div")].find((d) => d.textContent.startsWith("SPREAD") && d.children.length > 1);
    const cell = (label) => [...strip().children].find((c) => c.textContent.startsWith(label));
    await waitFor(() => expect(cell("Gilt–UST 10Y").textContent).toContain("—"));
    for (const label of ["Gilt–UST 10Y", "Gilt–Bund 10Y", "Gilt–Bund 2Y", "GB 10Y–2Y"]) {
      expect(cell(label).textContent).toContain("—");
      expect(cell(label).textContent).not.toMatch(/pp/);
    }
    expect(cell("Bund–UST 10Y").textContent).toContain("-0.63pp");
    expect(cell("JP 30Y–10Y").textContent).toMatch(/pp/);
  });

  it("foreignBondSpreads: a stale leg gives val null and display — for every spread", () => {
    const latest = { FB_DE_10Y: 3.47, FB_DE_02Y: 2.0, FB_GB_10Y: 4.4, FB_GB_02Y: 4.0, FB_JP_10Y: 1.6, FB_JP_30Y: 3.2, DGS10: 4.1 };
    const out = foreignBondSpreads(latest, (c) => c !== "DGS10", {});
    for (const label of ["Bund–UST 10Y", "Gilt–UST 10Y", "JGB–UST 10Y"]) {
      const s = out.find((x) => x.label === label);
      expect(s).toBeTruthy();
      expect(s.val).toBeNull();
      expect(s.display).toBe("—");
    }
    expect(out.find((x) => x.label === "Gilt–Bund 10Y").val).toBeCloseTo(0.93, 6);
  });
});

describe("AC-3: FOREIGN-BONDS has MARKETS' structure and interactions", () => {
  async function open(hash) {
    window.location.hash = hash;
    const view = render(<App />);
    await settle(view.container);
    const body = view.container.firstChild.children[3];
    return { ...view, body };
  }

  it("the same sections in the same order", async () => {
    const markets = await open("#/markets");
    const mSections = sections(markets.body);
    cleanup();
    const bonds = await open("#/foreign-bonds");
    const fSections = sections(bonds.body);
    expect(mSections).toEqual(["confidence", "cards", "chart", "spreads", "footer"]);
    // Sentinel D-0115: the EA benchmark panel heads the tab; the rest mirrors MARKETS.
    expect(fSections).toEqual(["ea", ...mSections]);
    expect(bonds.body.textContent).toContain("Source: Deutsche Bundesbank");
  });

  it("the same controls: series toggles, % CHANGE, the four ranges", async () => {
    for (const [hash, toggles] of [["#/markets", 12], ["#/foreign-bonds", 49]]) {
      const { body } = await open(hash);
      const chart = [...body.children].find((el) => el.textContent.includes("% CHANGE"));
      const buttons = [...chart.querySelectorAll("button")].map((b) => b.textContent);
      expect(buttons.slice(-5)).toEqual(["% CHANGE", "6M", "1Y", "2Y", "5Y"]);
      expect(buttons.length - 5).toBe(toggles);
      cleanup();
    }
  });

  it("the same interactions: toggle a series, change range, % CHANGE hides spreads", async () => {
    for (const [hash, series] of [["#/markets", "30Y Treasury"], ["#/foreign-bonds", "DE 30Y"]]) {
      const { body } = await open(hash);
      const chart = [...body.children].find((el) => el.textContent.includes("% CHANGE"));
      const toggle = within(chart).getByText(series);
      const before = toggle.style.background;
      fireEvent.click(toggle);
      expect(toggle.style.background).not.toBe(before);

      const calls = fetch.mock.calls.length;
      fireEvent.click(within(chart).getByText("2Y"));
      await waitFor(() => expect(fetch.mock.calls.length).toBeGreaterThan(calls));
      const last = String(fetch.mock.calls.at(-1)[0]);
      expect(last).toContain("/timeseries?metric_codes=");

      fireEvent.click(within(chart).getByText("% CHANGE"));
      expect(sections(body)).not.toContain("spreads");
      fireEvent.click(within(chart).getByText("% CHANGE"));
      expect(sections(body)).toContain("spreads");
      cleanup();
    }
  });

  it("#/foreign-bonds opens the tab, and Back returns", async () => {
    expect(TABS.indexOf("FOREIGN-BONDS")).toBe(TABS.indexOf("MARKETS") + 1);
    expect(parseRoute("#/foreign-bonds").tab).toBe("FOREIGN-BONDS");

    const { container } = await open("#/markets");
    expect(container.textContent).toContain("Source: FRED");
    const tabButton = screen.getByRole("button", { name: "FOREIGN-BONDS" });
    await act(async () => { fireEvent.click(tabButton); });
    expect(window.location.hash).toBe("#/foreign-bonds");
    await waitFor(() => expect(container.textContent).toContain("Source: Deutsche Bundesbank"));

    await act(async () => {
      window.history.back();
      await new Promise((r) => setTimeout(r, 50));
    });
    await waitFor(() => expect(window.location.hash).toBe("#/markets"));
    await waitFor(() => expect(container.textContent).toContain("Source: FRED"));
  });
});

const OAT_BUND = "OAT–Bund 10Y (daily, BdF TEC − Bundesbank)";
const pt = (date, value) => ({ date, value });

describe("D-0112 amendment 2 (T-0112 addendum 2): the daily OAT–Bund spread", () => {
  it("is FB_FR_10Y minus FB_DE_10Y in bp on fixture dates", () => {
    const fr = [pt("2026-10-19", 3.30), pt("2026-10-20", 3.35)];
    const de = [pt("2026-10-19", 3.45), pt("2026-10-20", 3.47)];
    const out = oatBundDailySpread(fr, de);
    expect(out.map((p) => p.date)).toEqual(["2026-10-19", "2026-10-20"]);
    expect(out[0].bp).toBeCloseTo(-15, 6);
    expect(out[1].bp).toBeCloseTo(-12, 6);
  });

  it("a date with one leg missing is a gap, never a forward fill", () => {
    const fr = [pt("2026-10-16", 3.20), pt("2026-10-19", 3.30), pt("2026-10-20", 3.35)];
    const de = [pt("2026-10-16", 3.40), pt("2026-10-20", 3.47)];
    const out = oatBundDailySpread(fr, de);
    expect(out.map((p) => p.date)).toEqual(["2026-10-16", "2026-10-20"]);
    expect(out[0].bp).toBeCloseTo(-20, 6);
    expect(oatBundDailySpread(fr, [])).toEqual([]);
    expect(oatBundDailySpread(undefined, de)).toEqual([]);
  });

  it("the current value comes from the last date BOTH legs share", () => {
    const series = {
      FB_FR_10Y: [pt("2026-10-19", 3.30), pt("2026-10-20", 3.35)],
      FB_DE_10Y: [pt("2026-10-19", 3.45)],
    };
    const s = foreignBondSpreads({ FB_FR_10Y: 3.35, FB_DE_10Y: 3.45 }, () => true, series)
      .find((x) => x.label === OAT_BUND);
    // D-0113 follow-up: pp like the rest of the strip; the meaning is the same.
    expect(s.unit).not.toBe("bp");
    expect(s.val).toBeCloseTo(-0.15, 6);
    expect(s.label).toBe(OAT_BUND);
    expect(s.tip).toMatch(/percentage points/);
    expect(s.tip).not.toMatch(/basis points/);
  });

  it("a stale leg shows a dash, not a number", () => {
    const series = {
      FB_FR_10Y: [pt("2026-10-20", 3.35)], FB_DE_10Y: [pt("2026-10-20", 3.47)],
    };
    for (const staleCode of ["FB_FR_10Y", "FB_DE_10Y"]) {
      const s = foreignBondSpreads({ FB_FR_10Y: 3.35, FB_DE_10Y: 3.47 }, (c) => c !== staleCode, series)
        .find((x) => x.label === OAT_BUND);
      expect(s.val).toBeNull();
      expect(s.display).toBe("—");
    }
  });

  it("on the tab: -0.12pp when fresh, — when the French leg is stale", async () => {
    const view = render(<ForeignBondsTab />);
    await settle(view.container);
    await waitFor(() => expect(screen.getByText(OAT_BUND)).toBeTruthy());
    const cell = () => screen.getByText(OAT_BUND).closest("div[style]").parentElement;
    await waitFor(() => expect(cell().textContent).toContain("-0.12pp"));
    cleanup();

    freshness = allFresh();
    freshness.sources.find((s) => s.key === "foreign_bonds_fr").status = "stale";
    const stale = render(<ForeignBondsTab />);
    await settle(stale.container);
    await waitFor(() => expect(screen.getByText(OAT_BUND)).toBeTruthy());
    await waitFor(() => expect(stale.container.textContent).not.toContain("-0.12pp"));
    const strip = [...stale.container.querySelectorAll("div")].find((d) => d.textContent.startsWith("SPREAD") && d.children.length > 1);
    const oat = [...strip.children].find((c) => c.textContent.includes(OAT_BUND));
    expect(oat.textContent).toContain("—");
  });
});
