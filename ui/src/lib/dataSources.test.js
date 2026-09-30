/**
 * `F-0096` — the one surface whose job is to say where the numbers come from.
 *
 * The ABOUT tab's source catalogue lived inside the component as a local const,
 * so nothing could check it. It drifted until it claimed three sources were
 * MANUAL that had become automated, named `mfhhis01.txt` as the TIC file (the
 * `F-0088` defect verbatim, still being recommended to the reader months after
 * it was found), omitted CDS and TreasuryDirect, and listed CDS under FUTURE
 * while it was a live scoring dimension.
 *
 * A stale entry here is worse than a stale entry anywhere else: every other
 * screen shows data, this one makes claims about provenance, and a reader has no
 * way to tell a wrong claim from a right one.
 */
import { describe, expect, it } from "vitest";

import { FUTURE, SIGNALS, SOURCES } from "./dataSources";

describe("the source catalogue", () => {
  it("claims nothing is hand-fed, because nothing is", () => {
    // The `manual` flag drives an amber border on the card. Three of five
    // sources carried it while their pipelines had already been automated
    // (D-0076, F-0091) — and one of the two it did NOT flag, TIC, was the most
    // broken of the lot.
    const manual = SOURCES.filter((s) => s.manual).map((s) => s.name);
    expect(manual).toEqual([]);
  });

  it("every source states an update cadence and a lag", () => {
    // A source with no stated lag is one a reader cannot judge, which is the
    // whole reason this tab exists.
    for (const s of SOURCES) {
      expect(s.update, s.name).toBeTruthy();
      expect(s.lag, s.name).toBeTruthy();
      expect(s.metrics.length, s.name).toBeGreaterThan(0);
    }
  });

  it("does not still recommend the frozen TIC history file", () => {
    // F-0088. mfhhis01.txt is served, returns 200, is rewritten by every
    // release, and ends at December 2025. Naming it here as the source is how
    // the next person reintroduces a nine-month freeze.
    const tic = SOURCES.find((s) => s.name.startsWith("TIC"));
    expect(tic).toBeTruthy();
    expect(tic.url).toContain("slt_table5");
    // It may be MENTIONED — the note explains what it is and why not to use it.
    // It must not be the URL.
    expect(tic.url).not.toContain("mfhhis");
  });

  it("credits gold to the IMF return rather than the compilation of it", () => {
    // D-0076. WGC's own files are named '..._IFS.xlsx'; we now read the
    // upstream monthly feed directly.
    const gold = SOURCES.find((s) => /Gold Reserves/i.test(s.name));
    expect(gold.name).toMatch(/IMF/);
    expect(gold.update).toMatch(/monthly/i);
  });

  it("lists every source the model actually scores on", () => {
    // CDS and TreasuryDirect were absent entirely. CDS is dimension 7 and the
    // only market-priced input in the whole model.
    const blob = SOURCES.map((s) => s.name + s.metrics.join(" ")).join(" ");
    for (const needed of ["FRED", "TIC", "IMF", "World Bank", "LBMA", "CDS", "TreasuryDirect"]) {
      expect(blob, `${needed} is not in the catalogue`).toContain(needed);
    }
  });
});

describe("the roadmap", () => {
  it("does not promise things that already ship", () => {
    // It offered "CDS Spreads ... Requires Bloomberg or Markit data" while CDS
    // was one day old, scored, and free. A roadmap listing shipped features as
    // future work cannot be used to tell what the system does.
    const shipped = SOURCES.map((s) => s.name + s.metrics.join(" ")).join(" ");
    for (const f of FUTURE) {
      const claimsCds = /\bCDS\b/.test(f.name);
      const claimsMoney = /broad money|\bM2\b/i.test(f.name);
      expect(claimsCds && /CDS/.test(shipped), `FUTURE still lists ${f.name}`).toBe(false);
      expect(claimsMoney && /Broad Money/.test(shipped), `FUTURE still lists ${f.name}`).toBe(false);
    }
  });

  it("gives a reason for each item, not just a name", () => {
    for (const f of FUTURE) {
      expect(f.why, f.name).toBeTruthy();
      expect(f.why.length, f.name).toBeGreaterThan(40);
    }
  });
});

describe("the signal tiers", () => {
  it("describes the three multiplier tiers in order", () => {
    expect(SIGNALS.map((s) => s.tier)).toEqual([1, 2, 3]);
  });

  it("every tier states a formula, a threshold and an interpretation", () => {
    for (const s of SIGNALS) {
      expect(s.formula, s.name).toBeTruthy();
      expect(s.threshold, s.name).toBeTruthy();
      expect(s.interpretation, s.name).toBeTruthy();
    }
  });
});
