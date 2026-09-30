import { describe, expect, it } from "vitest";

import { ageInDays, freshness } from "./freshness";

const NOW = new Date(2026, 8, 29); // 2026-09-29, local

/**
 * A tolerance as the server would send it.
 *
 * F-0087: these cases used to pass a `TIC_TOLERANCE_DAYS` constant the
 * client held. The client no longer holds one — `freshness` judges only
 * against a number it is handed, and the numbers live in
 * `pipelines/freshness_watchdog.py`. The judging behaviour is unchanged and
 * still tested; what changed is where the threshold comes from.
 */
const FROM_SERVER = 100;

describe("ageInDays", () => {
  it("handles the month-precision form the composite sends", () => {
    // The composite's as_of is "2025-12" — a month, not a day.
    expect(ageInDays("2025-12", NOW)).toBe(302);
  });

  it("handles a full date and an ISO timestamp", () => {
    expect(ageInDays("2026-09-28", NOW)).toBe(1);
    expect(ageInDays("2026-09-28T00:00:00", NOW)).toBe(1);
  });

  it("reads the calendar day from the string, not from a timezone shift", () => {
    // F-0071 again: a bare date parsed as UTC midnight renders a day early
    // west of UTC, and an age computed from it is off by one everywhere.
    expect(ageInDays("2026-09-29", NOW)).toBe(0);
  });

  it("is null for a missing or unparseable value rather than NaN", () => {
    for (const bad of [null, undefined, "", "unknown", "Dec 2025"]) {
      expect(ageInDays(bad, NOW), String(bad)).toBeNull();
    }
  });
});

describe("freshness", () => {
  it("flags the real case: TIC frozen at December 2025", () => {
    const f = freshness("2025-12", FROM_SERVER, NOW);
    expect(f.age).toBe(302);
    expect(f.stale).toBe(true);
    expect(f.text).toBe("302 days old");
  });

  it("does not flag an ordinary monthly lag", () => {
    // TIC publishes monthly with roughly a two-month lag. That is the
    // source's cadence, not a fault, and colouring it red would train the
    // reader to ignore the colour.
    const f = freshness("2026-08", FROM_SERVER, NOW);
    expect(f.stale).toBe(false);
    expect(f.color).toBe("#1E2D3D");
  });

  it("turns failure-red only past the tolerance", () => {
    expect(freshness("2026-06-22", FROM_SERVER, NOW).stale).toBe(false);
    expect(freshness("2026-06-20", FROM_SERVER, NOW).stale).toBe(true);
  });

  it("uses whatever tolerance it is handed, holding none of its own", () => {
    // F-0087. This case replaces one that asserted the client constant
    // equalled 100 to match the pipeline. It matched the wrong number: 100
    // is where pipelines/treasury_holdings.py REFUSES the file, while
    // pipelines/freshness_watchdog.py — which owns the question the reader
    // is actually asking — calls TIC stale at 55. Three numbers existed for
    // one question and the screen could contradict itself.
    //
    // Asserted with a value nobody would hardcode, so a smuggled-in default
    // fails here.
    expect(freshness("2026-08-01", 37, NOW).stale).toBe(true);
    expect(freshness("2026-08-01", 90, NOW).stale).toBe(false);
  });

  it("makes NO ruling when it is given no tolerance", () => {
    // A 302-day-old date is certainly stale, but this function is not the
    // component that gets to say so. Silence is correct here; the verdict
    // comes from the watchdog, through DataConfidence.
    const f = freshness("2025-12", null, NOW);
    expect(f.age).toBe(302);
    expect(f.stale).toBe(false);
    expect(f.color).toBe("#1E2D3D");
  });

  it("says nothing at all when there is no date", () => {
    const f = freshness(null, FROM_SERVER, NOW);
    expect(f.text).toBe("");
    expect(f.stale).toBe(false);
  });
});
