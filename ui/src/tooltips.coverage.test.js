/**
 * Every tile, card and column header carries a tooltip.
 *
 * Owner ruling, 2026-10-08: "Install tooltips on all tiles, cards, and column
 * headers." A rule nobody enforces is decoration (architecture.test.js), so
 * this enforces it from the source:
 *
 *  - a tile is an object literal with a `label` and a value (`val`, `value`
 *    or `v`). Each one must also carry a `tip`.
 *  - a column header is a `<th>`. Each one must be a `ColHeader` or an
 *    `InfoTip as="th"`, both of which require a tip to show anything. A bare
 *    `<th>` is a header with no explanation.
 *
 * pages.dom.test.jsx checks the rendered half: every header that actually
 * mounts carries the `data-tip` marker InfoTip sets.
 */
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const SRC = import.meta.dirname;

function sources(dir = SRC, prefix = "") {
  const out = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const rel = prefix ? `${prefix}/${entry.name}` : entry.name;
    if (entry.isDirectory()) out.push(...sources(join(dir, entry.name), rel));
    else if (/\.jsx?$/.test(entry.name) && !/\.test\.jsx?$/.test(entry.name)) {
      out.push([rel, readFileSync(join(dir, entry.name), "utf8")]);
    }
  }
  return out;
}

/** Object literals opening with `{ label: ...` , returned whole. */
function labelledObjects(text) {
  const found = [];
  const re = /\{\s*label:/g;
  let m;
  while ((m = re.exec(text))) {
    let depth = 0;
    let j = m.index;
    for (; j < text.length; j += 1) {
      if (text[j] === "{") depth += 1;
      else if (text[j] === "}" && --depth === 0) break;
    }
    found.push(text.slice(m.index, j + 1));
  }
  return found;
}

describe("every tile carries a tip", () => {
  it("no { label, value } object is missing its tip", () => {
    const missing = [];
    for (const [rel, text] of sources()) {
      for (const obj of labelledObjects(text)) {
        if (/\b(val|value|v)\s*:/.test(obj) && !/\btip\s*:/.test(obj)) {
          missing.push(`${rel}: ${obj.slice(0, 50).replace(/\s+/g, " ")}`);
        }
      }
    }
    expect(missing).toEqual([]);
  });
});

describe("every column header carries a tip", () => {
  it("no bare <th> outside ColHeader and InfoTip", () => {
    const bare = [];
    for (const [rel, text] of sources()) {
      if (/(^|\/)(ColHeader|InfoTip)\.jsx$/.test(rel)) continue;
      const lines = text.split("\n");
      lines.forEach((line, i) => {
        if (/<th[\s>]/.test(line)) bare.push(`${rel}:${i + 1}`);
      });
    }
    expect(bare).toEqual([]);
  });
});
