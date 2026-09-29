import { useEffect, useState } from "react";

import { apiFetch } from "../lib/api";
import { METRICS, SOVEREIGN_YIELD_CODES } from "../lib/constants";
import { latestByCode, pivotByDate, priorObservation, seriesByCode } from "../lib/series";

/** Everything the ticker and the stat cards draw from. */
export const TRACKED_CODES = [
  ...METRICS.map((m) => m.code),
  ...Object.values(SOVEREIGN_YIELD_CODES),
];

/** How far back the stat cards look for their comparison point. */
export const CHANGE_WINDOW_DAYS = 30;

/**
 * The latest value of every tracked code, plus the observation roughly
 * `CHANGE_WINDOW_DAYS` before it.
 *
 * `F-0055`: `prior` is found BY DATE and carries `actualDays`, the gap it
 * really found. It used to be `points.at(-2)` — the previous row, which on a
 * daily series is yesterday, while the card said "vs 30d". The caller labels
 * with the number this returns rather than assuming thirty.
 *
 * A window of 120 days is requested because the monthly series (CPI, M2, the
 * sovereign yields) need four months to contain two observations.
 */
export function useMarketSeries() {
  const [latestAll, setLatestAll] = useState({ latest: {}, prior: {} });

  useEffect(() => {
    let live = true;
    const end = new Date();
    const start = new Date();
    start.setDate(start.getDate() - 120);

    apiFetch(`/timeseries?metric_codes=${TRACKED_CODES.join(",")}&start_date=${start.toISOString()}&end_date=${end.toISOString()}`)
      .then((response) => (response.ok ? response.json() : Promise.reject(new Error(String(response.status)))))
      .then((raw) => {
        if (!live) return;
        const series = seriesByCode(pivotByDate(raw), TRACKED_CODES);
        const prior = {};
        for (const code of TRACKED_CODES) {
          const found = priorObservation(series[code], CHANGE_WINDOW_DAYS);
          if (found) prior[code] = found;
        }
        setLatestAll({ latest: latestByCode(series), prior });
      })
      // The ticker is furniture: if it cannot load, the header simply carries
      // no numbers. It must not take the tab with it.
      .catch(() => {});

    return () => { live = false; };
  }, []);

  return latestAll;
}
