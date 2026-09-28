/**
 * One module owning the API base URL. ORDER-03 Part F step 1.
 *
 * It replaced this, which lived at the top of App.jsx:
 *
 *     const API = window.location.hostname === "localhost"
 *       ? "http://localhost:8000/api" : "/api";
 *
 * That tests the hostname against the literal string "localhost", so the app
 * could only be developed from `localhost`. Loaded from `127.0.0.1`, a LAN
 * address, or any preview host, it fell through to the same-origin `/api` —
 * correct in production, wrong against a Vite dev server on a different port,
 * and the failure is every request 404ing with nothing explaining why.
 *
 * Resolution order:
 *
 *   1. VITE_API_BASE, if set. An explicit override always wins.
 *   2. In dev, the API on port 8000 of WHATEVER HOST THE PAGE CAME FROM.
 *      The host is read rather than assumed, which is the actual fix.
 *   3. In production, same-origin `/api` — FastAPI serves the bundle itself,
 *      so there is no cross-origin request to make. This is also why the CORS
 *      middleware was removed in D-0035 / F-0029.
 */

const DEV_API_PORT = 8000;

function stripTrailingSlash(value) {
  return value.endsWith("/") ? value.slice(0, -1) : value;
}

function resolveBase() {
  const configured = import.meta.env?.VITE_API_BASE;
  if (configured) return stripTrailingSlash(configured);

  if (import.meta.env?.DEV) {
    const { protocol, hostname } = window.location;
    return `${protocol}//${hostname}:${DEV_API_PORT}/api`;
  }

  return "/api";
}

export const API_BASE = resolveBase();

/** Absolute URL for an API path. Accepts "/holdings" or "holdings". */
export function apiUrl(path = "") {
  if (!path) return API_BASE;
  return `${API_BASE}${path.startsWith("/") ? path : `/${path}`}`;
}

/**
 * fetch(), with the base URL applied.
 *
 * Deliberately does NOT throw on a non-2xx response: callers here already
 * branch on `r.ok` or read the JSON body for an error field, and changing that
 * contract while moving 22 call sites would mix a refactor with a behaviour
 * change. Part F step 2 is where error handling gets revisited.
 */
export function apiFetch(path, options) {
  return fetch(apiUrl(path), options);
}
