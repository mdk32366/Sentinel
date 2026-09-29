import { useCallback, useEffect, useState } from "react";

import { apiFetch } from "../lib/api";
import { pivotByDate } from "../lib/series";

/**
 * Rebase every series to its own first observation, as a percentage.
 *
 * Exported because it is the one piece of arithmetic on the MARKETS chart and
 * it is worth being able to test without a chart. A series whose first
 * observation is zero is dropped rather than divided by, which is why the
 * guard is `base[code]` and not `base[code] != null`.
 */
export function normalizeRows(rows, codes) {
  if (!rows.length) return rows;
  const base = {};
  for (const code of codes) base[code] = rows.find((r) => r[code] != null)?.[code];

  return rows.map((row) => {
    const out = { date: row.date };
    for (const code of codes) {
      if (row[code] != null && base[code]) out[code] = ((row[code] - base[code]) / base[code]) * 100;
    }
    return out;
  });
}

/**
 * The rows behind the MARKETS chart, for the currently selected codes, range
 * and normalisation. Refetches whenever any of the three changes.
 *
 * `F-0065`: this depends on the VALUES of its inputs, not on their identities.
 * The obvious version closes over `activeMetrics` and `range` and lists them
 * as dependencies, which works only while every caller happens to hold them
 * in state. Hand it an array literal — as any test does, and as a caller
 * computing its codes inline would — and each render produces a new array,
 * which re-arms the effect, which sets state, which renders. The first run of
 * this hook's own tests died with:
 *
 *     Worker exited unexpectedly with exit code 134
 *
 * So the dependency is the joined code string and the day count. A hook whose
 * correctness rests on the caller's memoisation is a trap with no signal.
 */
export function useChartSeries({ activeMetrics, range, normalized }) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);

  const codes = (activeMetrics || []).join(",");
  const days = range?.days;

  const fetchRows = useCallback(async () => {
    const selected = codes ? codes.split(",") : [];
    if (!selected.length || !days) {
      setRows([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const end = new Date();
      const start = new Date();
      start.setDate(start.getDate() - days);
      const response = await apiFetch(
        `/timeseries?metric_codes=${codes}&start_date=${start.toISOString()}&end_date=${end.toISOString()}`,
      );
      if (!response.ok) throw new Error(`${response.status} ${response.statusText}`.trim());
      const pivoted = pivotByDate(await response.json());
      setRows(normalized ? normalizeRows(pivoted, selected) : pivoted);
    } catch (cause) {
      // An empty chart with the axes still drawn, rather than the PREVIOUS
      // range's data sitting under the new range's label — that would be a
      // wrong chart rather than a missing one. Logged rather than swallowed,
      // because unlike the ticker this is the thing the user asked for.
      console.error("chart series failed to load", cause);
      setRows([]);
    } finally {
      setLoading(false);
    }
  }, [codes, days, normalized]);

  // fetchRows is a useCallback over [codes, days, normalized] — three
  // primitives. None of its setters touch them, so this cannot loop (F-0056).
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { fetchRows(); }, [fetchRows]);

  return { rows, loading };
}
