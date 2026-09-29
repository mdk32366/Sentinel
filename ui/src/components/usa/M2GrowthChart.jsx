import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { formatDate } from "../../lib/format";

/** The same thresholds the M2 tile uses. */
const growthColor = (v) => (v > 10 ? "#E07B5A" : v > 5 ? "#E8C547" : "#5DB87A");

/**
 * US M2 year-on-year growth.
 *
 * `F-0067`: the series behind this used to index back twelve rows while the
 * tile beside it looked back by date. Both now come from
 * `usaSeries.yoySeries`, so the chart and the badge cannot disagree.
 */
export function M2GrowthChart({ rows, current }) {
  if (!rows?.length) return null;

  return (
    <div style={{ background: "#0A1520", border: "1px solid #1A2530", borderRadius: 2, padding: "20px 24px", marginBottom: 20 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 16 }}>
        <div style={{ fontFamily: "monospace", fontSize: 10, color: "#3A4D5C", letterSpacing: "0.1em" }}>US M2 BROAD MONEY GROWTH (YoY %)</div>
        {current != null && (
          <span style={{ fontFamily: "monospace", fontSize: 10, color: growthColor(current), background: `${growthColor(current)}18`, border: `1px solid ${growthColor(current)}44`, borderRadius: 2, padding: "1px 6px" }}>
            {current.toFixed(1)}% current
          </span>
        )}
      </div>
      <ResponsiveContainer width="100%" height={160}>
        <LineChart data={rows} margin={{ top: 4, right: 8, bottom: 4, left: 8 }}>
          <CartesianGrid strokeDasharray="2 6" stroke="#0F1923" vertical={false} />
          <XAxis dataKey="date" tickFormatter={formatDate} tick={{ fill: "#3A4D5C", fontFamily: "monospace", fontSize: 10 }} axisLine={false} tickLine={false} minTickGap={60} interval="preserveStartEnd" />
          <YAxis tick={{ fill: "#3A4D5C", fontFamily: "monospace", fontSize: 10 }} axisLine={false} tickLine={false} width={44} tickFormatter={(v) => `${v.toFixed(0)}%`} />
          <ReferenceLine y={10} stroke="#E07B5A" strokeDasharray="4 4" strokeOpacity={0.5} label={{ value: "10%", fill: "#E07B5A66", fontFamily: "monospace", fontSize: 9, position: "right" }} />
          <ReferenceLine y={0} stroke="#2A3540" strokeDasharray="3 3" />
          <Tooltip formatter={(v) => [`${v?.toFixed(1)}%`, "M2 YoY"]} contentStyle={{ background: "#0A1520", border: "1px solid #1E2D3D", borderRadius: 2, fontFamily: "monospace", fontSize: 11 }} labelStyle={{ color: "#5A6878" }} labelFormatter={formatDate} />
          <Line type="monotone" dataKey="growth" stroke="#6A8FC4" strokeWidth={1.5} dot={false} connectNulls />
        </LineChart>
      </ResponsiveContainer>
      <div style={{ fontFamily: "monospace", fontSize: 10, color: "#2A3540", marginTop: 6 }}>
        The 2020-2022 surge (peak +27%) drove CPI to 9.1%. Current trajectory matters for foreign holders deciding whether dollar reserves are worth holding.
      </div>
    </div>
  );
}
