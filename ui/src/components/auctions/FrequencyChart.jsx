import { BAND } from "../../lib/auctions";

/**
 * The trailing 12-month signal count over time, against its two bands
 * (D-0109). Plain SVG: one line, two dashed band lines, the latest point.
 */
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
        <line key={band} data-band-line={band} x1={0} x2={W} y1={y(v)} y2={y(v)}
          stroke={BAND[band].color} strokeOpacity={0.45} strokeDasharray="4 4" vectorEffect="non-scaling-stroke" />
      ))}
      <path data-series="count" d={d} fill="none" stroke="#8A9BAC" strokeWidth={1.5} vectorEffect="non-scaling-stroke" />
      <circle cx={x(pts.length - 1)} cy={y(last.count)} r={3} fill={color} />
    </svg>
  );
}
