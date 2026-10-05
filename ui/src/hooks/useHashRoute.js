import { useMemo, useSyncExternalStore } from "react";

import { parseRoute } from "../lib/countryRoute";

/**
 * D-0091: `{ tab, iso }` from `location.hash`, re-read on `hashchange`.
 *
 * `useSyncExternalStore` rather than `useState` + `useEffect`: the URL is an
 * external store, and syncing it into state from an effect is exactly what
 * `react-hooks/set-state-in-effect` (run in CI) exists to stop. The snapshot
 * is the hash STRING, so it is stable between renders; parsing happens after.
 */
function subscribe(onChange) {
  window.addEventListener("hashchange", onChange);
  return () => window.removeEventListener("hashchange", onChange);
}

const getSnapshot = () => window.location.hash;
const getServerSnapshot = () => "";

export function useHashRoute() {
  const hash = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
  return useMemo(() => parseRoute(hash), [hash]);
}
