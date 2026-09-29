/**
 * Series maths for the USA dashboard.
 *
 * The dashboard groups `/timeseries` by metric rather than by date — it draws
 * each series on its own axis, so it never needs the date-keyed join the
 * MARKETS chart uses.
 */

const DAY_MS = 24 * 60 * 60 * 1000;

/** Widest and narrowest gap that still counts as "a year ago". */
const YEAR_MIN_DAYS = 340;
const YEAR_MAX_DAYS = 400;

/**
 * Group a flat `/timeseries` response into `{code: [{date, value}]}`.
 *
 * Values are parsed, since the API returns them as strings, and each series
 * is sorted ascending — the caller reads `at(-1)` for the latest and walks
 * backwards for a year-ago comparison, and both are wrong on an unsorted
 * series without saying so.
 */
export function byMetric(raw = []) {
  const out = {};
  for (const point of raw || []) {
    if (!point || !point.date || !point.metric_code) continue;
    const value = parseFloat(point.value);
    if (Number.isNaN(value)) continue;
    (out[point.metric_code] ||= []).push({ date: String(point.date).split("T")[0], value });
  }
  for (const series of Object.values(out)) series.sort((a, b) => a.date.localeCompare(b.date));
  return out;
}

/** The most recent value of a series, or null. */
export function latestValue(series) {
  return series?.length ? series[series.length - 1].value : null;
}

/**
 * The observation roughly a year before `index`, found BY DATE.
 *
 * Returns null when nothing falls in the window rather than reaching for the
 * nearest point — `F-0055` again: "the oldest thing I have", reported as a
 * year-on-year change, is a wrong number that looks right.
 */
export function yearAgo(series, index) {
  // The guard comes FIRST. A default of `series.length - 1` is evaluated
  // before the body, so `yearAgo(undefined)` threw before it could return
  // null - and the USA dashboard calls this for CPIAUCSL, which is simply
  // absent whenever that pipeline has not run.
  if (!series?.length) return null;
  const at = index ?? series.length - 1;
  if (at <= 0 || at >= series.length) return null;
  const asOf = Date.parse(series[at].date);
  for (let i = at - 1; i >= 0; i -= 1) {
    const gap = (asOf - Date.parse(series[i].date)) / DAY_MS;
    if (gap >= YEAR_MIN_DAYS && gap <= YEAR_MAX_DAYS) return series[i];
    if (gap > YEAR_MAX_DAYS) return null;
  }
  return null;
}

/** Year-on-year percentage change at the end of a series, or null. */
export function yoyPercent(series) {
  const latest = series?.length ? series[series.length - 1] : null;
  const ago = yearAgo(series);
  if (!latest || !ago || ago.value === 0) return null;
  return ((latest.value - ago.value) / Math.abs(ago.value)) * 100;
}

/**
 * Year-on-year growth at every point in a series, for the M2 chart.
 *
 * `F-0067`: this used to index back twelve rows — `m2Data[i - 12]` — while
 * the M2 stat card beside it looked back BY DATE. Two methods for the same
 * quantity on the same screen, and the index-based one is right only while
 * the series has no gaps and is exactly monthly. It is the same shape as
 * `F-0007` and `F-0055`, in a third place.
 *
 * Points with no observation in the window are omitted, which is what the old
 * `.filter(d => d.growth != null)` did.
 */
export function yoySeries(series) {
  if (!series?.length) return [];
  const out = [];
  for (let i = 0; i < series.length; i += 1) {
    const ago = yearAgo(series, i);
    if (!ago || ago.value === 0) continue;
    out.push({
      date: series[i].date,
      growth: ((series[i].value - ago.value) / Math.abs(ago.value)) * 100,
    });
  }
  return out;
}
