import { useCallback, useState } from "react";

import { apiFetch } from "../lib/api";

/**
 * Fire a write against the API and keep per-key progress and outcome.
 *
 * ADMIN runs eight pipelines from one table and CDS runs one from a banner;
 * both tracked `{[name]: bool}` and `{[name]: {ok, data}}` by hand. Keyed
 * rather than single, because ADMIN can have two pipelines in flight and a
 * single `running` flag would grey out the wrong row.
 *
 * Unlike the read path this never had the `F-0063` defect: both call sites
 * already recorded `response.ok` alongside the body, so a pipeline that
 * returned 500 showed as failed. That distinction is preserved exactly —
 * `ok` is the HTTP result, and `data` is whatever came back either way,
 * because a failed pipeline's body is the error message worth showing.
 *
 * `run` returns the outcome as well as storing it, so a caller can reload
 * its resources afterwards without reaching into state.
 */
export function useAsyncAction() {
  const [running, setRunning] = useState({});
  const [results, setResults] = useState({});

  const run = useCallback(async (key, path, { method = "POST" } = {}) => {
    setRunning((prev) => ({ ...prev, [key]: true }));
    setResults((prev) => ({ ...prev, [key]: null }));

    let outcome;
    try {
      const response = await apiFetch(path, { method });
      // A pipeline that fails hard can answer with an HTML error page. Losing
      // the status to a JSON parse error would report a server fault as a
      // client one.
      const body = await response.json().catch(() => ({}));
      outcome = { ok: response.ok, data: body };
    } catch (cause) {
      outcome = { ok: false, data: { error: cause.message } };
    }

    setResults((prev) => ({ ...prev, [key]: outcome }));
    setRunning((prev) => ({ ...prev, [key]: false }));
    return outcome;
  }, []);

  return { running, results, run };
}
