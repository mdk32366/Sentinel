import { describe, expect, it } from "vitest";
import { buildYieldSeries } from "./yieldSeries";

/**
 * F-0007. The old implementation zipped by array index off DGS10, so a monthly
 * series was painted onto the first N daily dates. These cases fail against
 * that implementation and pass against the date join, which is what makes them
 * worth having rather than a restatement of the code.
 */

const daily = (dates) => dates.map((date, i) => ({ date, value: 4 + i / 100 }));

describe("buildYieldSeries", () => {
  it("puts every value on its own date", () => {
    const rows = buildYieldSeries({
      DGS10: daily(["2026-01-02", "2026-01-03", "2026-01-06"]),
      DFF: [{ date: "2026-01-06", value: 3.63 }],
    });
    const withFf = rows.filter((r) => r["Fed Funds"] != null);
    expect(withFf).toHaveLength(1);
    expect(withFf[0].date).toBe("2026-01-06");
  });

  it("does NOT shift a sparse series onto early dates", () => {
    // The defect, stated as a test: the secondary series has one point, dated
    // late. Index zipping put it at index 0 — the FIRST date. The date join
    // must not.
    //
    // D-0057 made Fed Funds daily, which removed the 60-against-1,250 case
    // that produced F-0007. It did NOT remove this one: DFF has no weekend or
    // holiday observations and FRED publishes it a few days behind the
    // Treasury yields, so one missing day is enough to start pairing the
    // wrong dates — quieter than the original, and just as wrong.
    const rows = buildYieldSeries({
      DGS10: daily(["2026-01-02", "2026-01-03", "2026-01-06", "2026-02-02"]),
      DFF: [{ date: "2026-02-02", value: 3.63 }],
    });
    expect(rows[0]["Fed Funds"]).toBeUndefined();
    expect(rows.at(-1)["Fed Funds"]).toBe(3.63);
  });

  it("spans the full range when a sparse series ends late", () => {
    const rows = buildYieldSeries({
      DGS10: daily(Array.from({ length: 60 }, (_, i) =>
        `2026-01-${String((i % 28) + 1).padStart(2, "0")}`)),
      DFF: [{ date: "2026-12-01", value: 3.0 }],
    });
    expect(rows.at(-1).date).toBe("2026-12-01");
    expect(rows.at(-1)["Fed Funds"]).toBe(3.0);
  });

  it("includes dates that only a secondary series has", () => {
    // A union, not a left join off DGS10. A point on a day DGS10 skipped -
    // a holiday one series observes and the other does not - must still
    // appear.
    const rows = buildYieldSeries({
      DGS10: daily(["2026-01-02"]),
      DFF: [{ date: "2026-01-01", value: 3.63 }],
    });
    expect(rows.map((r) => r.date)).toEqual(["2026-01-01", "2026-01-02"]);
  });

  it("returns rows sorted ascending regardless of input order", () => {
    const rows = buildYieldSeries({
      DGS10: [
        { date: "2026-03-01", value: 5 },
        { date: "2026-01-01", value: 4 },
        { date: "2026-02-01", value: 4.5 },
      ],
    });
    expect(rows.map((r) => r.date)).toEqual(["2026-01-01", "2026-02-01", "2026-03-01"]);
  });

  it("aligns two series that have different missing days", () => {
    // DGS2 used to drift against DGS10 whenever their gaps differed.
    const rows = buildYieldSeries({
      DGS10: daily(["2026-01-02", "2026-01-05", "2026-01-06"]),
      DGS2: [
        { date: "2026-01-02", value: 1 },
        { date: "2026-01-06", value: 3 },
      ],
    });
    const byDate = Object.fromEntries(rows.map((r) => [r.date, r]));
    expect(byDate["2026-01-02"]["2Y"]).toBe(1);
    expect(byDate["2026-01-05"]["2Y"]).toBeUndefined();
    expect(byDate["2026-01-06"]["2Y"]).toBe(3);
  });

  it("tolerates missing codes and malformed points", () => {
    const rows = buildYieldSeries({
      DGS10: [{ date: "2026-01-02", value: 4 }, null, { value: 9 }],
    });
    expect(rows).toHaveLength(1);
  });

  it("returns an empty array for no data rather than throwing", () => {
    expect(buildYieldSeries({})).toEqual([]);
    expect(buildYieldSeries()).toEqual([]);
  });
});
