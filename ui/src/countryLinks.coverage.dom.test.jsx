// @vitest-environment jsdom
/**
 * D-0091 guards (b): every country mention on rows 1-15 is a link to its card.
 *
 * Matt's ask was to ENSURE that a country, when clicked, leads to its card.
 * Fifteen surfaces rendered countries and they had grown three different
 * behaviours, one of them (CDS) sending a token the card could not resolve
 * (F-0106). A per-surface patch fixes today; this is what keeps it fixed.
 *
 * G5 renders each surface against the captured production payloads and walks
 * every text node. A text node whose trimmed value EQUALS a known country
 * name or ISO3 is a mention, and every mention must sit inside an
 * `a[href="#/country/<ISO3>"]` for that country. Equality, not substring, so
 * tooltip prose ("Japan's holdings moved...") is never a mention.
 *
 * Non-vacuity is pinned from the fixture: an empty render, or a stub that
 * misses a URL, finds too few mentions and goes red rather than green.
 *
 * G6 proves the scanner itself still sees a bad mention. G9 is a static lint
 * for a raw country cell, in the style of architecture.test.js.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { cleanup, render, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CountryLink } from "./components/CountryLink";
import { countryHref } from "./lib/countryRoute";
import { CDSTab } from "./pages/CDSTab";
import { CompositeTab } from "./pages/CompositeTab";
import { CountryTab } from "./pages/CountryTab";
import { CrossAssetTab } from "./pages/CrossAssetTab";
import { GoldReservesTab } from "./pages/GoldReservesTab";
import { HoldingsTab } from "./pages/HoldingsTab";

const FIXTURE = join(import.meta.dirname, "../../tests/fixtures/api/production_payloads.json");
const P = JSON.parse(readFileSync(FIXTURE, "utf8"));

const TIERS = ["crisis", "stressed", "elevated", "watch"];
const compositeRows = TIERS.flatMap((t) => P.composite[t] || []);
const crossRows = ["cross_asset_stress", "treasury_only_stress", "gold_only_stress"]
  .flatMap((k) => P.cross_asset_stress[k] || []);
const holdingRows = P.holdings.holdings;
const goldRows = P.gold_reserves.reserves;
const cdsRows = P.cds_all;

/** `/countries` is not in the fixture; it is the union of holdings and gold. */
const countries = (() => {
  const byIso = new Map();
  for (const r of [...holdingRows, ...goldRows]) {
    if (!byIso.has(r.country_code)) byIso.set(r.country_code, { iso_code: r.country_code, name: r.country_name, region: null });
  }
  return [...byIso.values()];
})();

/** The HOLDINGS liquidation chips are literals in the page, not payload. */
const LIQUIDATION_CHIPS = [["RUS", "Russia"], ["TUR", "Turkey"], ["QAT", "Qatar"], ["UZB", "Uzbekistan"]];

/**
 * Every country the fixture knows, as text -> ISO3. The expected ISO always
 * comes from the payload row itself (`country_code`, `country_iso`,
 * `country_iso3` for CDS, `iso_code`), never from a name lookup in the UI.
 */
const VOCAB = new Map();
function learn(text, iso) {
  if (!text || !iso) return;
  const prior = VOCAB.get(text);
  if (prior && prior !== iso) throw new Error(`fixture is ambiguous: "${text}" is both ${prior} and ${iso}`);
  VOCAB.set(text, iso);
}
for (const r of holdingRows) { learn(r.country_name, r.country_code); learn(r.country_code, r.country_code); }
for (const r of goldRows) { learn(r.country_name, r.country_code); learn(r.country_code, r.country_code); }
for (const r of compositeRows) { learn(r.country_name, r.country_iso); learn(r.country_iso, r.country_iso); }
for (const r of crossRows) { learn(r.country_name, r.country_iso); learn(r.country_iso, r.country_iso); }
for (const r of cdsRows) { learn(r.country_name, r.country_iso3); learn(r.country_iso3, r.country_iso3); }
for (const [iso, name] of LIQUIDATION_CHIPS) { learn(name, iso); learn(iso, iso); }

/**
 * Walk every text node under `root`. Returns the mentions found and the bad
 * ones: a mention with no enclosing link, or a link to the wrong card.
 */
function scanCountryMentions(root, vocab = VOCAB) {
  const walker = root.ownerDocument.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const mentions = [];
  const bad = [];
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    const text = node.nodeValue.trim();
    const iso = vocab.get(text);
    if (!iso) continue;
    const expected = countryHref(iso);
    const link = node.parentElement?.closest("a[href]");
    const got = link ? link.getAttribute("href") : null;
    mentions.push({ text, expected, got });
    if (got !== expected) bad.push({ text, expected, got });
  }
  return { mentions, bad };
}

function report(surface, bad) {
  return bad.map((b) => `${surface}: "${b.text}" → expected ${b.expected}, got ${b.got ?? "<none>"}`).join("\n");
}

function stubFor(url) {
  if (url.includes("/holdings/cross-asset-stress")) return P.cross_asset_stress;
  if (url.includes("/holdings")) return P.holdings;
  if (url.includes("/gold-reserves")) return P.gold_reserves;
  if (url.includes("/stress/composite")) return P.composite;
  if (url.includes("/cds/coverage")) return { configured: 31, with_data: cdsRows.length, without_data: 31 - cdsRows.length, missing_codes: [] };
  if (url.includes("/cds/all")) return P.cds_all;
  if (url.includes("/countries")) return countries;
  if (url.includes("/freshness")) return { counts: {}, sources: [] };
  return {};
}

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn((url) => Promise.resolve({
    ok: true, status: 200, statusText: "OK",
    json: () => Promise.resolve(stubFor(String(url))),
    text: () => Promise.resolve(""),
  })));
});

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

const isos = (rows, key) => rows.map((r) => r[key]).filter(Boolean);

/**
 * Per surface: the minimum number of mentions, and the ISO3s that must each
 * have at least one link. Both computed from the fixture.
 */
const SURFACES = [
  {
    name: "HOLDINGS (rows 4-7)", Component: HoldingsTab,
    // table rows + 8 quick cards + 4 liquidation chips + Top Holder
    min: holdingRows.length + Math.min(8, holdingRows.length) + LIQUIDATION_CHIPS.length + 1,
    required: [...isos(holdingRows, "country_code"), ...LIQUIDATION_CHIPS.map(([iso]) => iso)],
  },
  {
    name: "GOLD (rows 8-11)", Component: GoldReservesTab,
    // table rows + 8 quick cards + Top Holder (the chart is 0x0 in jsdom; G8)
    min: goldRows.length + Math.min(8, goldRows.length) + 1,
    required: isos(goldRows, "country_code"),
  },
  {
    name: "COMPOSITE (rows 12-13)", Component: CompositeTab,
    // leaderboard rows + Top Risk
    min: compositeRows.length + 1,
    required: [...isos(compositeRows, "country_iso"), P.composite.summary.highest_risk.country_iso],
  },
  {
    name: "CDS (row 14)", Component: CDSTab,
    min: cdsRows.length,
    required: isos(cdsRows, "country_iso3"),
  },
  {
    name: "CROSS-ASSET (row 15)", Component: CrossAssetTab,
    min: crossRows.length,
    required: isos(crossRows, "country_iso"),
  },
  {
    name: "COUNTRY picker (rows 1-3)", Component: CountryTab,
    // every tile + the USA issuer button
    min: countries.length + 1,
    required: [...countries.map((c) => c.iso_code), "USA"],
  },
];

describe("the fixture can support this guard", () => {
  it("has the row counts the Spec pinned", () => {
    expect(compositeRows.length).toBeGreaterThanOrEqual(49);
    expect(cdsRows.length).toBe(21);
    expect(crossRows.length).toBeGreaterThanOrEqual(34);
    expect(holdingRows.length).toBeGreaterThanOrEqual(36);
    expect(goldRows.length).toBeGreaterThanOrEqual(97);
  });

  it("every CDS row carries an ISO3 (F-0106: the token is not one)", () => {
    for (const r of cdsRows) expect(countryHref(r.country_iso3), r.country_iso).not.toBeNull();
    expect(countryHref(cdsRows[0].country_iso)).toBeNull();
  });
});

describe("G5: every country mention on rows 1-15 opens its card", () => {
  for (const { name, Component, min, required } of SURFACES) {
    it(name, async () => {
      const { container } = render(<Component latestAll={{}} />);
      // Non-vacuity doubles as the wait: until the data is in, there are no
      // mentions, and a surface that never renders them times out red.
      await waitFor(() => {
        expect(scanCountryMentions(container).mentions.length).toBeGreaterThanOrEqual(min);
      });

      const { mentions, bad } = scanCountryMentions(container);
      expect(bad.length, `\n${report(name, bad)}\n`).toBe(0);
      expect(mentions.length).toBeGreaterThanOrEqual(min);

      const linked = new Set([...container.querySelectorAll("a[href^='#/country/']")].map((a) => a.getAttribute("href")));
      const missing = [...new Set(required)].filter((iso) => !linked.has(countryHref(iso)));
      expect(missing, `${name}: no link to these cards`).toEqual([]);
    });
  }
});

describe("G6: the scanner can still see a bad mention", () => {
  it("reports exactly the two raw mentions and not the linked one", () => {
    const { container } = render(
      <div>
        <span>Russia</span> <span>RUS</span>
        <CountryLink iso="RUS" name="Russia" />
      </div>,
    );
    const { mentions, bad } = scanCountryMentions(container);
    expect(mentions).toHaveLength(4);
    expect(bad).toEqual([
      { text: "Russia", expected: "#/country/RUS", got: null },
      { text: "RUS", expected: "#/country/RUS", got: null },
    ]);
  });

  it("reports a link to the wrong card", () => {
    const { container } = render(<a href="#/country/RUSSIA">Russia</a>);
    const { bad } = scanCountryMentions(container);
    expect(bad).toEqual([{ text: "Russia", expected: "#/country/RUS", got: "#/country/RUSSIA" }]);
  });

  it("does not count prose", () => {
    const { container } = render(<p>Japan&apos;s holdings moved while Russia exited.</p>);
    expect(scanCountryMentions(container).mentions).toHaveLength(0);
  });
});

/**
 * G9: a raw country cell in a page is a regression waiting to render. Strip
 * every <CountryLink ...>...</CountryLink> (and self-closing one), then fail
 * on any JSX child that prints a country field directly. Prop values
 * (`iso={c.country_code}`) and template literals (`${...}`) are not children.
 */
const PAGES = ["HoldingsTab", "GoldReservesTab", "CompositeTab", "CDSTab", "CrossAssetTab", "CountryTab"];
const RAW_FIELD = /(?<![=$])\{\s*[\w?.]+\.(country_name|country_code|country_iso3?|iso_code)\s*\}/g;
const RAW_NAME_OR_ISO = /(?<![=$])\{\s*c\.(name|iso)\s*\}/g;
/** `file:reason` for anything legitimate. There are none after D-0091. */
const ALLOW = [];

/** Blank out CountryLink elements, keeping offsets so line numbers survive. */
function stripCountryLinks(src) {
  let out = src;
  let from = 0;
  for (;;) {
    const start = out.indexOf("<CountryLink", from);
    if (start < 0) return out;
    // End of the opening tag: the first ">" outside any {...}.
    let depth = 0;
    let i = start + 1;
    for (; i < out.length; i++) {
      const ch = out[i];
      if (ch === "{") depth++;
      else if (ch === "}") depth--;
      else if (ch === ">" && depth === 0) break;
    }
    let end = i + 1;
    if (out[i - 1] !== "/") {
      const close = out.indexOf("</CountryLink>", end);
      end = close < 0 ? out.length : close + "</CountryLink>".length;
    }
    out = out.slice(0, start) + out.slice(start, end).replace(/[^\n]/g, " ") + out.slice(end);
    from = end;
  }
}

describe("G9: no page prints a raw country field outside a CountryLink", () => {
  for (const page of PAGES) {
    it(`pages/${page}.jsx`, () => {
      const src = readFileSync(join(import.meta.dirname, "pages", `${page}.jsx`), "utf8");
      const stripped = stripCountryLinks(src);
      const patterns = [RAW_FIELD, ...(page === "HoldingsTab" || page === "CountryTab" ? [RAW_NAME_OR_ISO] : [])];
      const offenders = [];
      for (const re of patterns) {
        for (const m of stripped.matchAll(re)) {
          const line = stripped.slice(0, m.index).split("\n").length;
          offenders.push(`pages/${page}.jsx:${line}: ${m[0]}`);
        }
      }
      const allowed = offenders.filter((o) => !ALLOW.some((a) => o.startsWith(a.split(":")[0])));
      expect(allowed).toEqual([]);
    });
  }

  it("the lint can fail (self-test)", () => {
    const src = `<td>{c.country_name}</td><CountryLink iso={c.country_iso} name={c.country_name}>{c.country_iso}</CountryLink><CountryLink iso={x.iso_code} />`;
    const hits = [...stripCountryLinks(src).matchAll(RAW_FIELD)].map((m) => m[0]);
    expect(hits).toEqual(["{c.country_name}"]);
  });
});
