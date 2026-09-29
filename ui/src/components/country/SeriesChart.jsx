import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { formatDate } from "../../lib/format";

/**
 * One panel of the country detail: a title, a line, and a footnote.
 *
 * The TIC, gold and reserves-ex-gold charts were three copies of the same
 * forty lines, differing only in `dataKey`, stroke, title, axis width and two
 * formatters. Three copies meant three places to fix a tooltip and two to
 * forget — and they had already drifted: the reserves chart used a 56px axis
 * and carried a source line, the other two did not.
 *
 * Renders nothing when there are no rows, which is what each caller's
 * `length > 0` guard did.
 */
export function SeriesChart({
  title, rows, dataKey, stroke, axisWidth = 48,
  tickFormat, tooltipFormat, tooltipLabel, footnote,
}) {
  if (!rows?.length) return null;

  return (
    <div style={{ background: "#0F1923", border: "1px solid #1A2530", borderRadius: 2, padding: "16px 20px" }}>
      <div style={{ fontFamily: "monospace", fontSize: 11, color: "#5A6878", marginBottom: 12, letterSpacing: "0.1em" }}>
        {title}
      </div>
      <ResponsiveContainer width="100%" height={160}>
        <LineChart data={rows} margin={{ top: 4, right: 8, bottom: 4, left: 8 }}>
          <CartesianGrid strokeDasharray="2 6" stroke="#0A1520" vertical={false} />
          <XAxis dataKey="date" tickFormatter={formatDate} tick={{ fill: "#3A4D5C", fontFamily: "monospace", fontSize: 10 }} axisLine={false} tickLine={false} minTickGap={60} interval="preserveStartEnd" />
          <YAxis tick={{ fill: "#3A4D5C", fontFamily: "monospace", fontSize: 10 }} axisLine={false} tickLine={false} width={axisWidth} tickFormatter={tickFormat} />
          <Tooltip
            formatter={(v) => [tooltipFormat(v), tooltipLabel]}
            contentStyle={{ background: "#0A1520", border: "1px solid #1E2D3D", borderRadius: 2, fontFamily: "monospace", fontSize: 11 }}
            labelFormatter={formatDate}
            labelStyle={{ color: "#5A6878" }}
          />
          <Line type="monotone" dataKey={dataKey} stroke={stroke} strokeWidth={1.5} dot={false} activeDot={{ r: 3 }} connectNulls />
        </LineChart>
      </ResponsiveContainer>
      {footnote && (
        <div style={{ fontFamily: "monospace", fontSize: 10, color: "#1E2D3D", marginTop: 8 }}>{footnote}</div>
      )}
    </div>
  );
}
