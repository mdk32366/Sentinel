/**
 * Join yield series for the country-detail chart.
 *
 * F-0007: this logic used to live inline in App.jsx and zipped the series by
 * ARRAY INDEX off DGS10:
 *
 *     data["DGS10"].map((d, i) => ({ "Fed Funds": data["FEDFUNDS"]?.[i]?.value }))
 *
 * DGS10 is daily — around 1,250 points over five years — and FEDFUNDS is
 * monthly, around 60. So sixty monthly values were painted onto the first sixty
 * DAILY dates: the Fed Funds line appeared squeezed into the left ~5% of the
 * chart, against dates it never had, and was null for the rest. DGS2 drifted
 * the same way whenever the two series had different missing days.
 *
 * Joining on the date keeps every point where it belongs. A sparse series
 * against a daily axis is correct — every <Line> carries connectNulls, so it
 * draws through the points it really has.
 *
 * `D-0057` replaced FEDFUNDS with DFF here, so the Fed Funds line is daily
 * like the rest of the curve and the sixty-against-1,250 mismatch is gone.
 * **The date join still matters and has not become redundant**: DFF has no
 * weekend or holiday observations, FRED publishes it a few days behind the
 * Treasury yields, and DFII10 has gaps of its own. Any two of those differing
 * by a single missing day is enough for an index zip to start pairing the
 * wrong dates — the same defect, but quieter, because a one-day slip does not
 * look obviously wrong the way a line squeezed into the left 5% did.
 *
 * Extracted from App.jsx so it can be tested at all (F-0053).
 */

/** Which metric code supplies which chart series key. */
export const YIELD_SERIES = [
  ["DGS10", "10Y"],
  ["DGS30", "30Y"],
  ["DGS2", "2Y"],
  ["DFF", "Fed Funds"],
  ["DFII10", "Real Yield"],
];

/**
 * @param {Record<string, Array<{date: string, value: number}>>} data
 * @param {Array<[string, string]>} series  code -> chart key
 * @returns {Array<Object>} one row per date, ascending, sparse where a series
 *                          has no observation on that date
 */
export function buildYieldSeries(data = {}, series = YIELD_SERIES) {
  const byDate = new Map();

  for (const [code, key] of series) {
    for (const point of data?.[code] || []) {
      if (!point || !point.date) continue;
      if (!byDate.has(point.date)) byDate.set(point.date, { date: point.date });
      byDate.get(point.date)[key] = point.value;
    }
  }

  return [...byDate.values()].sort((a, b) => a.date.localeCompare(b.date));
}
