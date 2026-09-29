/**
 * Series maths for the stat cards.
 *
 * F-0055: the "vs 30d" change on every ticker used to be computed as
 *
 *     month30[code] = withVal[withVal.length - 2][code]   // the PREVIOUS row
 *
 * which is the previous *observation*, not the observation thirty days ago.
 * For a monthly series those are the same thing. For a daily one they are not:
 * measured against production on 2026-09-29, eight of the eleven tickers were
 * labelling a one-to-three-day move as "vs 30d". The number was right, the
 * formatting was right, and the label was wrong by an order of magnitude.
 *
 * So the lookup is now by DATE, and it reports the gap it actually found. The
 * caller labels with that number rather than assuming thirty.
 */

const DAY_MS = 24 * 60 * 60 * 1000;

function daysBetween(laterIso, earlierIso) {
  return Math.round((Date.parse(laterIso) - Date.parse(earlierIso)) / DAY_MS);
}

/**
 * Collapse `[{date, CODE: value}]` rows into per-code ascending series.
 * @returns {Record<string, Array<{date: string, value: number}>>}
 */
export function seriesByCode(rows = [], codes = []) {
  const out = {};
  for (const code of codes) {
    out[code] = (rows || [])
      .filter((row) => row && row[code] != null)
      .map((row) => ({ date: row.date, value: row[code] }))
      .sort((a, b) => a.date.localeCompare(b.date));
  }
  return out;
}

/** Most recent value per code, or undefined where the series is empty. */
export function latestByCode(series = {}) {
  const out = {};
  for (const [code, points] of Object.entries(series)) {
    if (points.length) out[code] = points[points.length - 1].value;
  }
  return out;
}

/**
 * The observation closest to `daysBack` before the latest one, searching
 * backwards from the target date.
 *
 * Returns `{ value, date, actualDays }`, or null when the series is too short
 * to look back that far — null rather than the nearest available point,
 * because "the oldest thing I have" silently reported as a 30-day change is
 * the defect this function exists to remove.
 */
export function priorObservation(points = [], daysBack = 30) {
  if (!points || points.length < 2) return null;

  const latest = points[points.length - 1];
  const cutoff = Date.parse(latest.date) - daysBack * DAY_MS;

  let chosen = null;
  for (const point of points) {
    if (Date.parse(point.date) <= cutoff) chosen = point;
    else break;
  }
  if (!chosen) return null;

  return {
    value: chosen.value,
    date: chosen.date,
    actualDays: daysBetween(latest.date, chosen.date),
  };
}

/**
 * Change between two values.
 *
 * A percentage-point difference for series already expressed as a percentage
 * or an index; a percent change otherwise. Getting this branch wrong prints
 * "2.5%" where "2.5pp" is meant, which reads as plausible either way.
 */
export function changeBetween(latest, prior, unit) {
  if (latest == null || prior == null) return null;
  if (unit === "%" || unit === "") return latest - prior;
  if (prior === 0) return null;
  return ((latest - prior) / prior) * 100;
}

/** "pp" for a percentage series, "%" otherwise. Pairs with changeBetween. */
export function changeSuffix(unit) {
  return unit === "%" ? "pp" : "%";
}

/**
 * How to label the comparison, using the gap that was actually found rather
 * than the one that was asked for.
 */
export function changeWindowLabel(actualDays) {
  if (actualDays == null) return "";
  return `vs ${actualDays}d`;
}
