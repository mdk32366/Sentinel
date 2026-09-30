/**
 * `A-0019` — the surface says which dimensions can speak about a country.
 *
 * `F-0097` removed the false-exit path, and the honest consequence is that
 * dimension 1 (50 points, the largest) reaches only the twenty countries SLT
 * Table 5 names. The other 28 get nothing from it, not because they look calm
 * but because their position is unknown.
 *
 * Option 1 of `A-0019` was chosen over re-weighting: disclosure changes no
 * number, and re-weighting changes every number in the model. So these cases
 * pin what is *said*, and one of them pins that nothing is scored differently.
 */
import { describe, expect, it } from "vitest";

import {
  cdsCoverageNote,
  coverageBadge,
  monetaryCoverageNote,
  ticCoverageNote,
  unavailableDimensions,
  unreachablePoints,
} from "./coverage";

/** Germany as production serves it: the case that was worth 50 of 50 points. */
const DEU = {
  country_iso: "DEU",
  composite_score: 8.0,
  tic_state: "below_threshold",
  tic_last_reported_bn: 103.1,
  tic_last_reported_date: "2025-12-01",
  tic_score: 0,
  gold_score: 8.0,
  monetary_score: 0,
  cds_score: 0,
  cds_coverage: "quoted",
  m2_stale: false,
};

/** Kazakhstan: never in the table at all. */
const KAZ = { ...DEU, country_iso: "KAZ", tic_state: "no_data",
  tic_last_reported_bn: null, tic_last_reported_date: null };

/** France: reported, and scored on its actual trend. */
const FRA = { ...DEU, country_iso: "FRA", tic_state: "reported",
  tic_score: 42, composite_score: 42.0 };

describe("the Treasury dimension's reason", () => {
  it("names the last reported figure and its month", () => {
    // The whole difference between a fact and a fabrication. "EXITED: Zero US
    // Treasuries" was the fabrication; "$103.1bn in 2025-12" is checkable.
    const note = ticCoverageNote(DEU);
    expect(note).toMatch(/103\.1/);
    expect(note).toMatch(/2025-12/);
  });

  it("says scored as nothing rather than as zero", () => {
    // The distinction the reader has to come away with.
    expect(ticCoverageNote(DEU)).toMatch(/not as zero/i);
  });

  it("explains that Table 5 names only the twenty largest", () => {
    // Without this a reader cannot tell whether absence is a finding or a
    // reporting threshold.
    expect(ticCoverageNote(DEU)).toMatch(/twenty/);
    expect(ticCoverageNote(DEU)).toMatch(/All Other/);
  });

  it("distinguishes never-reported from fell-off-the-list", () => {
    const note = ticCoverageNote(KAZ);
    expect(note).toMatch(/never appeared/);
    expect(note).not.toMatch(/last reported/);
  });

  it("is silent for a country that does report", () => {
    expect(ticCoverageNote(FRA)).toBeNull();
  });

  it("does not invent a figure when none was stored", () => {
    // tic_last_reported_bn is null for no_data, and "$nullbn" on screen is
    // worse than saying nothing.
    expect(ticCoverageNote(KAZ)).not.toMatch(/\$/);
  });
});

describe("the other dimensions' reasons", () => {
  it("reports a broad money figure too old to score", () => {
    // F-0092. Canada's newest is 2008.
    const note = monetaryCoverageNote({ m2_stale: true, m2_year: 2008 });
    expect(note).toMatch(/2008/);
    expect(note).toMatch(/three years/);
  });

  it("is silent when broad money is current", () => {
    expect(monetaryCoverageNote({ m2_stale: false, m2_year: 2025 })).toBeNull();
  });

  it("keeps the CDS explanations that already existed", () => {
    // These were inline in StressContribution. Moved, not rewritten — a
    // rewrite would have quietly changed what three surfaces say.
    expect(cdsCoverageNote("not on the board")).toMatch(/No CDS quoted/);
    expect(cdsCoverageNote("not quoted as a running spread")).toMatch(/points-upfront/);
    expect(cdsCoverageNote("stale (2026-01-04)")).toMatch(/2026-01-04/);
    expect(cdsCoverageNote("quoted")).toBeNull();
    expect(cdsCoverageNote(null)).toBeNull();
  });
});

describe("the aggregate", () => {
  it("lists only the dimensions that cannot speak", () => {
    const missing = unavailableDimensions(DEU);
    expect(missing.map((d) => d.key)).toEqual(["tic_score"]);
  });

  it("orders by the points at stake", () => {
    const row = { ...DEU, m2_stale: true, m2_year: 2008,
      cds_coverage: "not on the board" };
    expect(unavailableDimensions(row).map((d) => d.max)).toEqual([50, 35, 20]);
  });

  it("totals the points the model could not reach", () => {
    expect(unreachablePoints(DEU)).toBe(50);
    expect(unreachablePoints(FRA)).toBe(0);
    expect(unreachablePoints({ ...DEU, m2_stale: true, m2_year: 2008 })).toBe(85);
  });

  it("returns nothing for a fully covered country", () => {
    expect(unavailableDimensions(FRA)).toEqual([]);
    expect(coverageBadge(FRA)).toBeNull();
  });

  it("survives a missing row rather than throwing", () => {
    // The composite payload omits fields for countries it does not rank.
    expect(unavailableDimensions(null)).toEqual([]);
    expect(unreachablePoints(null)).toBe(0);
    expect(coverageBadge(undefined)).toBeNull();
  });
});

describe("the table badge", () => {
  it("counts the unavailable dimensions", () => {
    expect(coverageBadge(DEU).text).toMatch(/^1/);
    expect(coverageBadge({ ...DEU, m2_stale: true, m2_year: 2008 }).text).toMatch(/^2/);
  });

  it("states the unreachable points out of 165 in its tooltip", () => {
    // 165 is the raw maximum, so "50 of 165" tells a reader how much of the
    // model was unavailable — which is the point of A-0019.
    expect(coverageBadge(DEU).title).toMatch(/50 of 165/);
  });

  it("carries every reason, not just a count", () => {
    const badge = coverageBadge({ ...DEU, m2_stale: true, m2_year: 2008 });
    expect(badge.title).toMatch(/Treasury/);
    expect(badge.title).toMatch(/Monetary/);
    expect(badge.title).toMatch(/103\.1/);
    expect(badge.title).toMatch(/2008/);
  });
});

describe("no score is changed", () => {
  it("this module reads and never computes a score", async () => {
    // A-0019 option 1 was chosen BECAUSE it changes no number. A helper here
    // that adjusted a score would have quietly implemented option 4.
    const src = await import("./coverage?raw").catch(() => null);
    // If raw import is unavailable in this environment, assert behaviourally
    // instead: the row goes in unmodified and comes back unmodified.
    const row = { ...DEU };
    const before = JSON.stringify(row);
    unavailableDimensions(row);
    unreachablePoints(row);
    coverageBadge(row);
    expect(JSON.stringify(row)).toBe(before);
    if (src?.default) {
      expect(src.default).not.toMatch(/composite_score\s*=/);
    }
  });
});
