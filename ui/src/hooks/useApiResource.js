import { useCallback, useEffect, useState } from "react";

import { apiFetch } from "../lib/api";

/**
 * Fetch one JSON resource on mount.
 *
 * ORDER-03 Part F step 4. Five tabs carried this, character for character:
 *
 *     const [data, setData] = useState(null);
 *     const [loading, setLoading] = useState(true);
 *     useEffect(() => {
 *       apiFetch(`/thing`)
 *         .then(r => r.json())
 *         .then(d => { setData(d); setLoading(false); })
 *         .catch(() => setLoading(false));
 *     }, []);
 *
 * Two things are wrong with it, and neither is visible at a glance.
 *
 * **It never checks `r.ok`** (`F-0063`). A 500 carrying a JSON error body
 * parses fine, so the body is installed as data and `loading` goes false. What
 * each tab then renders depends on whether it happens to look for an error
 * key: COMPOSITE checks `data.error`, CROSS-ASSET checks `data.detail`, and
 * HOLDINGS and GOLD check neither — so for those two a server error renders as
 * an *empty table*, which reads as "no country holds Treasuries" rather than
 * as a failure. A fault that renders as a plausible success is worse than one
 * that renders as nothing.
 *
 * **It never cancels.** A tab unmounted mid-flight still resolves and still
 * calls setState.
 *
 * So this hook reports the three states separately — `loading`, `error`,
 * `data` — and a caller that ignores `error` gets a blank page rather than a
 * confident empty one. `reload()` re-runs it in place, which is what CDS and
 * ADMIN want after kicking off a fetch.
 */
export function useApiResource(path, { enabled = true } = {}) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(Boolean(enabled && path));
  const [nonce, setNonce] = useState(0);

  const reload = useCallback(() => setNonce((n) => n + 1), []);

  useEffect(() => {
    if (!enabled || !path) return undefined;
    let live = true;

    // The reset belongs at the top of the effect so a changed `path` clears
    // the previous resource's data instead of showing it under the new
    // heading. It cannot loop: neither setter feeds [path, enabled, nonce].
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLoading(true);

    apiFetch(path)
      .then((response) => {
        if (!response.ok) {
          // The body of a failure is not the resource. Carry the status so a
          // caller can say WHICH failure it was.
          const failure = new Error(`${response.status} ${response.statusText}`.trim());
          failure.status = response.status;
          throw failure;
        }
        return response.json();
      })
      .then((body) => {
        if (!live) return;
        setData(body);
        setError(null);
      })
      .catch((cause) => {
        if (!live) return;
        setData(null);
        setError(cause instanceof Error ? cause : new Error(String(cause)));
      })
      .finally(() => {
        if (live) setLoading(false);
      });

    return () => { live = false; };
  }, [path, enabled, nonce]);

  return { data, error, loading, reload };
}
