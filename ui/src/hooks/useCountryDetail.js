import { useEffect, useState } from "react";

import { apiFetch } from "../lib/api";
import { TRESEG_CODES } from "../lib/constants";

const EMPTY_CDS = { cds5y: null, cds10y: null, termSpread: null, coverage: null, history: [] };

/**
 * Everything the country panel reads for one ISO code.
 *
 * Four requests, deliberately not four `useApiResource` calls: the three
 * history series settle together so the panel does not paint itself in
 * stages, while CDS is independent because a country with no CDS coverage is
 * ordinary and must not hold up the rest.
 *
 * Each history request fails soft to null. A country the API has no TIC row
 * for is the normal case, not a fault, and the panel already distinguishes
 * "no data available for XXX" from a loaded-but-empty position.
 */
export function useCountryDetail(iso) {
  const [state, setState] = useState({
    ticHistory: null, goldHistory: null, reservesHistory: null, loading: true,
  });
  const [cds, setCds] = useState(EMPTY_CDS);

  useEffect(() => {
    let live = true;
    // Reset on a changed `iso` so the previous country's charts do not sit
    // under the new country's name. Cannot loop: neither setter feeds [iso].
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setState((prev) => ({ ...prev, loading: true }));

    const end = new Date();
    const start = new Date();
    start.setFullYear(start.getFullYear() - 3);
    const window = `start_date=${start.toISOString()}&end_date=${end.toISOString()}`;
    const tresegCode = TRESEG_CODES[iso];

    const json = (path) => apiFetch(path)
      .then((r) => (r.ok ? r.json() : null))
      .catch(() => null);

    Promise.all([
      json(`/holdings/${iso}?${window}`),
      json(`/gold-reserves/${iso}`),
      tresegCode ? json(`/timeseries?metric_codes=${tresegCode}&${window}`) : Promise.resolve(null),
    ]).then(([ticHistory, goldHistory, reservesHistory]) => {
      if (!live) return;
      setState({ ticHistory, goldHistory, reservesHistory, loading: false });
    });

    json(`/cds?country=${iso}`).then((body) => {
      if (!live) return;
      if (!body) { setCds(EMPTY_CDS); return; }
      const cds5y = body?.["5Y"]?.value ?? null;
      const cds10y = body?.["10Y"]?.value ?? null;
      setCds({
        cds5y,
        cds10y,
        termSpread: cds5y != null && cds10y != null ? cds10y - cds5y : null,
        // F-0074: WHY there is no number, when there is none. F-0078: this
        // endpoint resolved nothing at all until the ISO code was mapped, so
        // every country read "No coverage" regardless.
        coverage: body?.coverage ?? null,
        history: Array.isArray(body?.history) ? body.history : [],
      });
    });

    return () => { live = false; };
  }, [iso]);

  return { ...state, cds };
}
