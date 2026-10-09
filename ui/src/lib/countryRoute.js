/**
 * D-0091: the country card has an address.
 *
 * Before this, nothing in the UI had a URL. Fifteen surfaces rendered a
 * country, each hand-rolled its own `onClick` on a div, a row or a button, and
 * three different behaviours grew out of that - including CDS sending the
 * namespace token "RUSSIA" to a card keyed by ISO3 (F-0106).
 *
 * The address is a HASH route, `#/country/<ISO3>`, and that is deliberate:
 * `main.py` serves the bundle with `StaticFiles(html=True)`, which has no SPA
 * fallback, so a path route like `/country/RUS` would 404 on refresh. The hash
 * never reaches the server, survives Basic Auth, refreshes, and opens in a new
 * tab. No router dependency and no backend change.
 *
 * Pure: no React, no DOM except the two navigate helpers.
 */
import { TABS } from "./constants";

const ISO3 = /^[A-Z]{3}$/;

function safeDecode(s) {
  try { return decodeURIComponent(s); } catch { return s; }
}

/** True for an ISO-3166 alpha-3 shaped key. Never upper-cases or maps. */
export function isCountryKey(k) {
  return typeof k === "string" && ISO3.test(k);
}

/**
 * The card's address, or null. It never guesses: "rus", "RUSSIA" and
 * "UNITED_STATES" are not keys, and a caller holding one gets no link rather
 * than a link to an empty card. Mapping names to ISO belongs to the server
 * (`ISO_BY_CDS_NAME`); a second copy here would be F-0062 again.
 */
export function countryHref(iso) {
  return isCountryKey(iso) ? `#/country/${iso}` : null;
}

/** `#/holdings`, `#/cross-asset`, ... */
export function tabHref(tab) {
  return `#/${String(tab).toLowerCase()}`;
}

/**
 * `{ tab, iso }` for a location hash.
 *
 * `#/country/<x>` is the COUNTRY tab; `iso` is the upper-cased segment when it
 * is ISO3-shaped and null otherwise, so a bad deep link shows the picker
 * rather than an empty card. The route segment is the one place input is
 * upper-cased: it is typed by people, not produced by a payload.
 */
// D-0109. Views a tab can be opened on directly: `#/auctions/signals` is the
// address the USA card's signal-frequency card links to.
const TAB_VIEWS = { AUCTIONS: ["signals"] };

/** `#/<tab>/<view>` for a view a tab supports. */
export function viewHref(tab, view) {
  return `${tabHref(tab)}/${view}`;
}

export function parseRoute(hash) {
  const path = String(hash ?? "").replace(/^#\/?/, "");
  const [head = "", rest = ""] = path.split("/");
  const segment = head.toUpperCase();

  if (segment === "COUNTRY") {
    const candidate = safeDecode(rest).toUpperCase();
    return { tab: "COUNTRY", iso: isCountryKey(candidate) ? candidate : null };
  }
  if (TABS.includes(segment)) {
    const candidate = safeDecode(rest).toLowerCase();
    const view = TAB_VIEWS[segment]?.includes(candidate) ? candidate : undefined;
    return { tab: segment, iso: null, view };
  }
  return { tab: "MARKETS", iso: null };
}

/** Navigate to a card. A no-op for a missing or non-ISO key. */
export function navigateToCountry(iso) {
  const href = countryHref(iso);
  if (href) window.location.hash = href;
}

/** Navigate to a tab. */
export function navigateToTab(tab) {
  window.location.hash = tabHref(tab);
}
