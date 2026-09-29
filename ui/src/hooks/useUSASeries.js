import { useEffect, useState } from "react";

import { apiFetch } from "../lib/api";
import { byMetric } from "../lib/usaSeries";

/** The codes the USA dashboard draws. */
export const USA_CODES = [
  "DGS30", "DGS10", "DGS2", "DGS5", "FEDFUNDS",
  "DFII10", "DTWEXBGS", "CPIAUCSL", "M2SL", "GOLD_SPOT_USD",
];

/**
 * Every USA series, grouped by metric code, for the last `days` days.
 *
 * Refetches on a changed window. `days` is a number rather than an object, so
 * there is no identity trap here (`F-0065`).
 *
 * Failures leave the previous grouping in place and are silent, which is what
 * this page did before. Every tile and chart already renders "—" or nothing
 * for a missing series, so a partial load degrades tile by tile rather than
 * taking the page.
 */
export function useUSASeries(days) {
  const [data, setData] = useState({});

  useEffect(() => {
    let live = true;
    const end = new Date();
    const start = new Date();
    start.setDate(start.getDate() - days);

    apiFetch(`/timeseries?metric_codes=${USA_CODES.join(",")}&start_date=${start.toISOString()}&end_date=${end.toISOString()}`)
      .then((response) => (response.ok ? response.json() : Promise.reject(new Error(String(response.status)))))
      .then((raw) => { if (live) setData(byMetric(raw)); })
      .catch(() => {});

    return () => { live = false; };
  }, [days]);

  return data;
}
