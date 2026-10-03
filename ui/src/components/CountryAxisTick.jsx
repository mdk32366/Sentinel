import { countryHref } from "../lib/countryRoute";

/**
 * D-0091: a Recharts X-axis tick that is a link to the country's card.
 *
 * An SVG `<a href>` is a real link - focusable, accessible, and it opens in a
 * new tab like any other. With no ISO3 key it falls back to bare text.
 *
 * The defaults reproduce the GOLD chart's previous tick (`fill #5A6878`,
 * monospace 10, rotated -45 and anchored at the end), so only the link
 * affordance changes.
 */
export function CountryAxisTick({
  x = 0, y = 0, payload,
  angle = -45, textAnchor = "end",
  fill = "#5A6878", fontSize = 10, fontFamily = "monospace",
}) {
  const value = payload?.value;
  const href = countryHref(value);
  const text = (
    <text x={0} y={0} dy="0.71em" textAnchor={textAnchor} transform={`rotate(${angle})`}
      fill={fill} fontSize={fontSize} fontFamily={fontFamily}>
      {value}
    </text>
  );
  return (
    <g transform={`translate(${x},${y})`}>
      {href
        ? <a href={href} className="country-link" data-country={value} aria-label={`${value} — open country card`}>{text}</a>
        : text}
    </g>
  );
}
