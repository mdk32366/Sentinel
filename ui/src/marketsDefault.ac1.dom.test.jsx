// @vitest-environment jsdom
/**
 * Sentinel D-0111 (vault:D-0057) AC-1 / AC-2: the default dashboard does not move.
 *
 * MARKETS was lifted out of App.jsx into pages/MarketsTab.jsx so FOREIGN-BONDS
 * could reuse it. A refactor like that is the change most likely to alter the
 * default view without anyone meaning to. So the default view is pinned as
 * BYTES: `__fixtures__/markets-default.ac1.html` was written by this test from
 * master at be64218, BEFORE the refactor, and the PR must reproduce it exactly.
 *
 * Three regions, three rules:
 *   - header + ticker: byte-identical (same ticker codes, same values)
 *   - MARKETS body (DataConfidence, 12 StatCards, chart panel, spread strip,
 *     footer): byte-identical
 *   - tab strip: identical except ONE new FOREIGN-BONDS button straight after
 *     MARKETS (AC-2). Removing that button must give the master bytes back.
 *
 * Regenerate only from master, never to make this pass:
 *   AC1_WRITE_BASELINE=1 npx vitest run src/marketsDefault.ac1.dom.test.jsx
 */
import { readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { cleanup, render, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App";

const BASELINE = join(import.meta.dirname, "__fixtures__", "markets-default.ac1.html");
const MARK = "\n<!-- ===== region ===== -->\n";

/** Two deterministic observations per requested code, ~60 days apart. */
function timeseries(url) {
  const m = /metric_codes=([^&]*)/.exec(url);
  const codes = m ? decodeURIComponent(m[1]).split(",").filter(Boolean) : [];
  const out = [];
  codes.forEach((code, i) => {
    const base = 1 + i * 0.37;
    out.push({ metric_code: code, date: "2026-08-03T00:00:00", value: Number(base.toFixed(4)) });
    out.push({ metric_code: code, date: "2026-09-02T00:00:00", value: Number((base + 0.11).toFixed(4)) });
    out.push({ metric_code: code, date: "2026-10-02T00:00:00", value: Number((base + 0.05).toFixed(4)) });
  });
  return out;
}

function stubResponse(url) {
  if (url.includes("/timeseries")) return timeseries(url);
  if (url.includes("/health")) return { status: "healthy" };
  if (url.includes("/stats")) {
    return { timeseries_records: 64336, data_latest: "2026-10-02T00:00:00" };
  }
  if (url.includes("/freshness")) {
    const src = (key, status) => ({ key, label: key, status, age_days: 1, max_age_days: 5, note: "n" });
    return {
      counts: {},
      sources: [src("treasury_yields", "ok"), src("oil", "ok"), src("dollar_index", "stale"), src("gold_price", "ok")],
    };
  }
  return {};
}

beforeEach(() => {
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

/** [header+ticker, tab strip, body] of the rendered default view. */
async function regions() {
  const { container } = render(<App />);
  // Settled: the ticker has values, the spread strip has rendered, the
  // freshness strip has rendered, and the footer carries the stats date.
  await waitFor(() => {
    const text = container.textContent;
    expect(text).toContain("SPREAD");
    expect(text).toContain("Last data point");
    expect(text).toContain("DATA CONFIDENCE");
    expect(text).toContain("records");
  });
  const root = container.firstChild;
  const kids = [...root.children];
  // header, ticker, tab strip, body
  expect(kids.length).toBe(4);
  return {
    head: kids[0].outerHTML + kids[1].outerHTML,
    tabs: kids[2],
    body: kids[3].outerHTML,
  };
}

describe("AC-1: the default dashboard renders byte-identical to master be64218", () => {
  it("header + ticker, tab strip (less FOREIGN-BONDS) and MARKETS body match the master bytes", async () => {
    const { head, tabs, body } = await regions();
    const labels = [...tabs.querySelectorAll("button")].map((b) => b.textContent);

    if (globalThis.process?.env?.AC1_WRITE_BASELINE) {
      writeFileSync(BASELINE, [head, tabs.outerHTML, body].join(MARK) + "\n");
      return;
    }

    const [mHead, mTabs, mBody] = readFileSync(BASELINE, "utf8").replace(/\n$/, "").split(MARK);

    // AC-2: exactly one new tab, straight after MARKETS.
    const fb = [...tabs.querySelectorAll("button")].filter((b) => b.textContent === "FOREIGN-BONDS");
    expect(fb.length).toBe(1);
    expect(labels.indexOf("FOREIGN-BONDS")).toBe(labels.indexOf("MARKETS") + 1);
    const stripped = tabs.cloneNode(true);
    [...stripped.querySelectorAll("button")].find((b) => b.textContent === "FOREIGN-BONDS").remove();
    expect(stripped.outerHTML).toBe(mTabs);

    expect(head).toBe(mHead);
    expect(body).toBe(mBody);
    expect(body.length).toBeGreaterThan(2000);
  });
});
