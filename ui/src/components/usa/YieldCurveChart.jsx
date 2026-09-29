import { CartesianGrid, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { breakingPointRate } from "../../lib/fiscal";
import { formatDate } from "../../lib/format";

const BREAK = breakingPointRate();

/**
 * The USA rate structure over the selected window.
 *
 * `F-0007`: the date join lives in `lib/yieldSeries.js` so it can be tested.
 * It used to be an index zip here, which paired the 30Y of one date with the
 * 2Y of another whenever a series had a gap.
 */
export function YieldCurveChart({ rows }) {
  if (!rows?.length) return null;

  return (
    <div style={{ background: "#0A1520", border: "1px solid #1A2530", borderRadius: 2, padding: "20px 24px", marginBottom: 20 }}>
      <div style={{ fontFamily: "monospace", fontSize: 10, color: "#3A4D5C", letterSpacing: "0.1em", marginBottom: 16 }}>YIELD CURVE &amp; RATE STRUCTURE</div>
      <ResponsiveContainer width="100%" height={200}>
        <LineChart data={rows} margin={{ top: 4, right: 8, bottom: 4, left: 8 }}>
          <CartesianGrid strokeDasharray="2 6" stroke="#0F1923" vertical={false} />
          <XAxis dataKey="date" tickFormatter={formatDate} tick={{ fill: "#3A4D5C", fontFamily: "monospace", fontSize: 10 }} axisLine={false} tickLine={false} minTickGap={60} interval="preserveStartEnd" />
          <YAxis tick={{ fill: "#3A4D5C", fontFamily: "monospace", fontSize: 10 }} axisLine={false} tickLine={false} width={40} tickFormatter={(v) => `${v}%`} />
          <ReferenceLine y={BREAK} stroke="#E07B5A" strokeDasharray="4 4" strokeOpacity={0.5} label={{ value: `${BREAK.toFixed(1)}% warning`, fill: "#E07B5A66", fontFamily: "monospace", fontSize: 9, position: "right" }} />
          <ReferenceLine y={0} stroke="#2A3540" strokeDasharray="3 3" />
          <Tooltip contentStyle={{ background: "#0A1520", border: "1px solid #1E2D3D", borderRadius: 2, fontFamily: "monospace", fontSize: 11 }} labelStyle={{ color: "#5A6878" }} labelFormatter={formatDate} formatter={(v, n) => [`${v?.toFixed(2)}%`, n]} />
          <Legend wrapperStyle={{ fontFamily: "monospace", fontSize: 10, color: "#5A6878", paddingTop: 12 }} />
          <Line type="monotone" dataKey="30Y" stroke="#D4B06A" strokeWidth={1.5} dot={false} connectNulls />
          <Line type="monotone" dataKey="10Y" stroke="#C8A96E" strokeWidth={1.5} dot={false} connectNulls />
          <Line type="monotone" dataKey="2Y" stroke="#9B8EC4" strokeWidth={1.5} dot={false} connectNulls />
          <Line type="monotone" dataKey="Fed Funds" stroke="#5DB87A" strokeWidth={1.5} dot={false} connectNulls />
          <Line type="monotone" dataKey="Real Yield" stroke="#E8C547" strokeWidth={1} dot={false} connectNulls strokeDasharray="3 3" />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
