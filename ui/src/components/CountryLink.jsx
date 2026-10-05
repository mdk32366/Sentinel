import { countryHref } from "../lib/countryRoute";

/**
 * D-0091: the one way a country mention opens its card.
 *
 * A real `<a href="#/country/<ISO3>">`: in the tab order, activates on Enter,
 * opens in a new tab on Ctrl/Cmd/middle-click, and gives the live proof a URL.
 * Same tab by default - there is no `target`.
 *
 * `onClick` only stops propagation. It never prevents the default, because
 * the browser's own hash navigation IS the behaviour. Stopping propagation
 * keeps a containing row's handler (the HOLDINGS / GOLD inline history panel,
 * F-0064) from also firing.
 *
 * An unknown key renders the name as plain text with a VISIBLE muted `?`.
 * A silently unlinked name looks exactly like a working one, which is the
 * F-0064 / F-0097 shape ("a dash indistinguishable from..."). Not `◦`: that
 * already means "no CDS quote" on COMPOSITE.
 *
 * Aggregates (Foreign Official, All Other, regions) never come through here.
 */
const CODE_STYLE = { marginLeft: 8, fontSize: 10, color: "#3A4D5C" };

function stop(e) {
  e.stopPropagation();
}

export function CountryLink({
  iso, name, showCode = true, children, style, codeStyle,
  onMouseEnter, onMouseLeave,
}) {
  const href = countryHref(iso);
  const label = children ?? name;

  if (!href) {
    const raw = String(iso ?? "");
    return (
      <span data-country-unlinked={raw} style={style}>
        {label}
        <sup
          title={`No country card: key '${raw}' is not an ISO-3166 alpha-3 code`}
          aria-label="no country card"
          style={{ marginLeft: 2, fontSize: 9, color: "#5A6878", cursor: "help" }}>?</sup>
      </span>
    );
  }

  return (
    <a
      href={href}
      className="country-link"
      data-country={iso}
      aria-label={`${name ?? iso} (${iso}) — open country card`}
      onClick={stop}
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
      style={style}>
      {label}
      {showCode && <span style={{ ...CODE_STYLE, ...codeStyle }}>{iso}</span>}
    </a>
  );
}
