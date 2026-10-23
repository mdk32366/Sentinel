import { BAND } from "../../lib/auctions";
import { InfoTip } from "../InfoTip";

/**
 * The trailing 12-month signal count over time, against its two bands
 * (D-0109). Plain SVG: one line, two dashed band lines, the latest point.
 */
const BAND_MEANING = {
  elevated: "At or above this line, weak auctions are arriving in runs rather than one at a time. It is the top fifth of months",
  high: "At or above this line, the run is unusual by the standard of the whole record. Only the top 3% of months reach it",
};

/** What a band line means, how often the history reached it, and where today sits. */
function bandTip(band, at, frequency) {
  const pts = frequency.history ?? [];
  const hits = pts.filter((p) => p.count >= at);
  const years = [...new Set(hits.map((p) => p.month.slice(0, 4)))];
  const since = pts.length ? pts[0].month.slice(0, 4) : "";
  const reached = hits.length
    ? `Reached in ${hits.length} month${hits.length === 1 ? "" : "s"}: ${years.join(", ")}.`
    : "Never reached.";
  const today = `Today: ${frequency.count}, ${frequency.count >= at ? "on or above" : "below"} this line.`;
  return `${BAND[band].label} · ${at} signals in 12 months (D-0109). ${BAND_MEANING[band]} since ${since}. ${reached} ${today}`;
}

export function FrequencyChart({ frequency, height = 70 }) {
  const pts = frequency.history ?? [];
  if (pts.length < 2) return null;
  const W = 600;
  const H = height;
  const top = Math.max(frequency.high_at + 2, ...pts.map((p) => p.count));
  const x = (i) => (i / (pts.length - 1)) * (W - 8) + 4;
  const y = (v) => H - 4 - (v / top) * (H - 10);
  const d = pts.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p.count).toFixed(1)}`).join("");
  const last = pts[pts.length - 1];
  const color = BAND[frequency.band]?.color ?? "#8A9BAC";
  return (
    <svg width="100%" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" style={{ display: "block", height }}
      role="img" aria-label={`Trailing 12-month signal count, ${pts[0].month} to ${last.month}`}>
      {[["elevated", frequency.elevated_at], ["high", frequency.high_at]].map(([band, v]) => (
        // A dashed line is a pixel tall; the transparent stroke under it is the
        // hover target, so the reader can find the tooltip.
        <InfoTip as="g" key={band} data-band-tip={band} title={`${BAND[band].label} line`}
          tip={bandTip(band, v, frequency)} placement="above" style={{ cursor: "help" }}>
          <line x1={0} x2={W} y1={y(v)} y2={y(v)} stroke="transparent" strokeWidth={12}
            vectorEffect="non-scaling-stroke" pointerEvents="stroke" />
          <line data-band-line={band} x1={0} x2={W} y1={y(v)} y2={y(v)}
            stroke={BAND[band].color} strokeOpacity={0.45} strokeDasharray="4 4" vectorEffect="non-scaling-stroke" />
        </InfoTip>
      ))}
      <path data-series="count" d={d} fill="none" stroke="#8A9BAC" strokeWidth={1.5} vectorEffect="non-scaling-stroke" />
      <circle cx={x(pts.length - 1)} cy={y(last.count)} r={3} fill={color} />
    </svg>
  );
}
