import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import { METRICS, SOVEREIGN_YIELD_CODES, TABS, TRESEG_CODES } from "./constants";

const SRC = join(import.meta.dirname, "..");

/** Every .js/.jsx under ui/src, as [relativePath, contents]. */
function sourceFiles(dir = SRC, prefix = "") {
  const out = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const rel = prefix ? `${prefix}/${entry.name}` : entry.name;
    if (entry.isDirectory()) out.push(...sourceFiles(join(dir, entry.name), rel));
    else if (/\.jsx?$/.test(entry.name)) out.push([rel, readFileSync(join(dir, entry.name), "utf8")]);
  }
  return out;
}

describe("the shared constants are actually shared", () => {
  /**
   * F-0062. `SOVEREIGN_YIELD_CODES` was extracted into this module, and
   * App.jsx went on carrying its own inline copy of the same fourteen codes
   * — twice. Three copies that happened to agree, with nothing that would
   * say so if they stopped agreeing.
   *
   * This is deliberately a property of the codebase rather than of a named
   * file (F-0061): it scans whatever is under ui/src, so moving a component
   * does not break it and pasting the codes into a NEW file does.
   */
  it("no file outside constants.js spells a FRED sovereign yield code", () => {
    const offenders = sourceFiles()
      .filter(([rel]) => !rel.endsWith("lib/constants.js"))
      .filter(([, body]) => /IRLTLT01[A-Z]{2}M156N/.test(body))
      .map(([rel]) => rel);
    expect(offenders).toEqual([]);
  });

  it("no file outside constants.js spells a FRED reserves-ex-gold code", () => {
    const offenders = sourceFiles()
      .filter(([rel]) => !rel.endsWith("lib/constants.js"))
      .filter(([, body]) => /TRESEG[A-Z]{2}M052N/.test(body))
      .map(([rel]) => rel);
    expect(offenders).toEqual([]);
  });

  it("covers the countries it claims to", () => {
    expect(Object.keys(SOVEREIGN_YIELD_CODES)).toHaveLength(14);
    expect(Object.keys(TRESEG_CODES)).toHaveLength(12);
    for (const code of Object.values(SOVEREIGN_YIELD_CODES)) {
      expect(code).toMatch(/^IRLTLT01[A-Z]{2}M156N$/);
    }
  });

  it("has no duplicate metric codes and no duplicate tabs", () => {
    const codes = METRICS.map((m) => m.code);
    expect(new Set(codes).size).toBe(codes.length);
    expect(new Set(TABS).size).toBe(TABS.length);
  });

  it("D-0051: STRESS is retired and must not come back as a tab", () => {
    expect(TABS).not.toContain("STRESS");
  });
});
