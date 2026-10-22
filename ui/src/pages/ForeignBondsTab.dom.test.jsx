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
 *       the four NO SOURCE cells. With no daily French 10Y the FR 10Y card
 *       falls back to the monthly OECD series, badged MONTHLY and labelled a
 *       fallback; the footer reads "Source: Banque de France, updated <date>".
 *
 * Every network call is stubbed.
 */
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "../App";
import {
  FOREIGN_BOND_METRICS, FR_10Y_MONTHLY_FALLBACK, SOVEREIGN_YIELD_CODES, TABS, foreignBondCells,
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
    expect(grid.children.length).toBe(20);
    expect(FOREIGN_BOND_METRICS.length).toBe(20);
    expect(FOREIGN_BOND_METRICS.filter((m) => m.code?.startsWith("FB_")).length).toBe(20);
    expect(grid.style.gridTemplateColumns).toBe("repeat(5, 1fr)");

    const cards = [...grid.children];
    const label = (c) => c.querySelector("span").textContent;
    // Country rows in order DE, GB, JP, FR; tenors 2/5/7/10/30 across.
    expect(cards.map(label)).toEqual([
      "DE 2Y", "DE 5Y", "DE 7Y", "DE 10Y", "DE 30Y",
      "GB 2Y", "GB 5Y", "GB 7Y", "GB 10Y", "GB 30Y",
      "JP 2Y", "JP 5Y", "JP 7Y", "JP 10Y", "JP 30Y",
      "FR 2Y", "FR 5Y", "FR 7Y", "FR 10Y", "FR 30Y",
    ]);
    expect(cards[3].textContent).toContain("3.47%");
    expect(cards[13].textContent).toContain("2.93%");

    const fr = cards.slice(15);
    // No NO SOURCE cell is left, and the daily French 10Y is shown, not the monthly.
    expect(fr.filter((c) => c.textContent.includes("—")).length).toBe(0);
    expect(fr[0].textContent).toContain("2.22%");
    expect(fr[3].textContent).toContain("3.35%");
    expect(fr[4].textContent).toContain("4.26%");
    expect(cards.filter((c) => c.textContent.includes("MONTHLY")).length).toBe(0);
    expect(container.textContent).toContain("Source: Banque de France, updated 2026-10-20");
  });

  it("with no daily French 10Y, FR 10Y falls back to the monthly OECD series, labelled", async () => {
    omit = new Set(FR_DAILY);
    const { container } = render(<ForeignBondsTab />);
    await settle(container);
    const grid = [...container.querySelectorAll("div")].find((d) => d.style.display === "grid");
    const cards = [...grid.children];
    expect(cards.length).toBe(20);
    const fr = cards.slice(15);
    expect(fr[3].querySelector("span").textContent).toBe("FR 10Y");
    expect(fr[3].textContent).toContain("MONTHLY");
    expect(fr[3].textContent).toContain("4.44%");
    expect(cards.filter((c) => c.textContent.includes("MONTHLY")).length).toBe(1);
    // The other four French cells have no fallback: "—", never a monthly number.
    expect(fr.filter((c) => c.textContent.includes("—")).length).toBe(4);
    expect(container.textContent).not.toContain("Source: Banque de France, updated");
    expect(container.textContent).toContain("Source: Banque de France, not yet available");
  });

  it("the fallback is only the 10Y, and only while the daily 10Y is missing", () => {
    expect(foreignBondCells({ FB_FR_10Y: 3.35 }).find((m) => m.label === "FR 10Y").code).toBe("FB_FR_10Y");
    const fb = foreignBondCells({}).find((m) => m.label === "FR 10Y");
    expect(fb).toBe(FR_10Y_MONTHLY_FALLBACK);
    expect(fb.code).toBe(FRA);
    expect(fb.badge).toBe("MONTHLY");
    expect(fb.tip).toMatch(/^FALLBACK\./);
    expect(foreignBondCells({}).filter((m) => m.code === FRA).length).toBe(1);
    expect(foreignBondCells({}).length).toBe(20);
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
      } else {
        expect(m.code).toMatch(/^FB_FR_\d\dY$/);
        expect(m.kind).toBe("CMT");
        expect(m.tip).toContain("Banque de France");
        expect(m.tip).toMatch(/FM\.D\.FR\.EUR\.FR2\.BB\.FRMOYTEC\d+\.HSTA/);
      }
    }
    expect(FR_10Y_MONTHLY_FALLBACK.kind).toBe("MON");
    expect(FR_10Y_MONTHLY_FALLBACK.scored).toBe(false);
    expect(FR_10Y_MONTHLY_FALLBACK.tip).toContain(FRA);
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
      "Gilt–Bund 2Y", "DE 10Y–2Y", "GB 10Y–2Y", "JP 30Y–10Y", "OAT–Bund 10Y", "OAT–Bund 10Y (monthly)"]) {
      expect(screen.getByText(label)).toBeTruthy();
    }
    // FB_DE_10Y 3.47 - DGS10 4.10
    expect(container.textContent).toContain("-0.63pp");
    // OAT-Bund monthly: 4.44 - 3.50
    expect(container.textContent).toContain("+0.94pp");
    // OAT-Bund daily (D-0112): FB_FR_10Y 3.35 - FB_DE_10Y 3.47
    expect(container.textContent).toContain("-0.12pp");
  });

  it("hides a spread whose leg is stale, and keeps the rest", async () => {
    freshness = allFresh();
    freshness.sources.find((s) => s.key === "foreign_bonds_gb").status = "stale";
    const { container } = render(<ForeignBondsTab />);
    await settle(container);
    await waitFor(() => expect(screen.queryByText("Gilt–UST 10Y")).toBeNull());
    expect(screen.queryByText("Gilt–Bund 10Y")).toBeNull();
    expect(screen.queryByText("GB 10Y–2Y")).toBeNull();
    expect(screen.getByText("Bund–UST 10Y")).toBeTruthy();
    expect(screen.getByText("JP 30Y–10Y")).toBeTruthy();
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
    expect(fSections).toEqual(mSections);
    expect(bonds.body.textContent).toContain("Source: Deutsche Bundesbank");
  });

  it("the same controls: series toggles, % CHANGE, the four ranges", async () => {
    for (const [hash, toggles] of [["#/markets", 12], ["#/foreign-bonds", 20]]) {
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
