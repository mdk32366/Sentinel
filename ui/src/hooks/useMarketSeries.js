import { useEffect, useState } from "react";

import { apiFetch } from "../lib/api";
import { METRICS, MONTHLY_10Y_EXTRA_CODES, SOVEREIGN_YIELD_CODES } from "../lib/constants";
import { latestByCode, pivotByDate, priorObservation, seriesByCode } from "../lib/series";

/** Everything the ticker and the stat cards draw from. */
export const TRACKED_CODES = [
  ...METRICS.map((m) => m.code),
  ...Object.values(SOVEREIGN_YIELD_CODES),
];

/** How far back the stat cards look for their comparison point. */
export const CHANGE_WINDOW_DAYS = 30;

/**
 * The latest value of every code in `codes`, plus the observation roughly
 * `CHANGE_WINDOW_DAYS` before it, and the newest date any of them carries.
 *
 * `F-0055`: `prior` is found BY DATE and carries `actualDays`, the gap it
 * really found. It used to be `points.at(-2)` — the previous row, which on a
 * daily series is yesterday, while the card said "vs 30d". The caller labels
 * with the number this returns rather than assuming thirty.
 *
 * A window of 120 days is requested because the monthly series (CPI, M2, the
 * sovereign yields) need four months to contain two observations.
 *
 * Sentinel D-0111: generalised from `useMarketSeries` so FOREIGN-BONDS draws
 * on the same window and the same prior-observation rule. Keyed on the joined
 * code string, not the array's identity (F-0065).
 *
 * Sentinel D-0112: also `dates`, the newest observation date per code, for the
 * FOREIGN-BONDS "Source: Banque de France, updated <date>" line. Additive:
 * no existing caller reads it. Amendment 2: also `series`, the per-code
 * points, for the daily OAT–Bund spread. Additive too.
 */
export function useSeries(codes) {
  const [state, setState] = useState({ latest: {}, prior: {}, latestDate: null, dates: {}, series: {} });
  const key = (codes || []).join(",");

  useEffect(() => {
    // Sentinel D-0113: an empty list (a non-FB country card) asks for nothing.
    if (!key) return undefined;
    let live = true;
    const list = key ? key.split(",") : [];
    const end = new Date();
    const start = new Date();
    start.setDate(start.getDate() - 120);

    apiFetch(`/timeseries?metric_codes=${key}&start_date=${start.toISOString()}&end_date=${end.toISOString()}`)
      .then((response) => (response.ok ? response.json() : Promise.reject(new Error(String(response.status)))))
      .then((raw) => {
        if (!live) return;
        const series = seriesByCode(pivotByDate(raw), list);
        const prior = {};
        const dates = {};
        let latestDate = null;
        for (const code of list) {
          const found = priorObservation(series[code], CHANGE_WINDOW_DAYS);
          if (found) prior[code] = found;
          const last = series[code]?.at(-1)?.date;
          if (last) dates[code] = last;
          if (last && (!latestDate || last > latestDate)) latestDate = last;
        }
        setState({ latest: latestByCode(series), prior, latestDate, dates, series });
      })
      // The ticker is furniture: if it cannot load, the header simply carries
      // no numbers. It must not take the tab with it.
      .catch(() => {});

    return () => { live = false; };
  }, [key]);

  return state;
}

/**
 * Sentinel D-0118: what the hook requests. TRACKED_CODES plus the display-only
 * monthly 10Y series (India's INDIRLTLT01STM) a country card reads. Kept out
 * of TRACKED_CODES so the ticker and MARKETS cards do not change.
 */
export const MARKET_REQUEST_CODES = [...TRACKED_CODES, ...Object.values(MONTHLY_10Y_EXTRA_CODES)];

/** Everything the ticker and the MARKETS stat cards draw from. */
export function useMarketSeries() {
  return useSeries(MARKET_REQUEST_CODES);
}
