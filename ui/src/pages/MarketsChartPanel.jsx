import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, ReferenceLine } from "recharts";

import { CustomTooltip } from "../components/CustomTooltip";
import { RANGES } from "../lib/constants";
import { formatDate } from "../lib/format";

/**
 * The MARKETS / FOREIGN-BONDS chart panel: series toggles, % CHANGE, ranges
 * and the line chart. Extracted from MarketsTab unchanged (Sentinel D-0113) so
 * the country cards embed the same chart, filtered to one country, rather than
 * a fork. `view` is a useChartView() state; the caller decides its lifetime.
 * `pressedState` adds aria-pressed to % CHANGE; MARKETS leaves it off so its
 * markup stays byte-identical to master (AC-1).
 */
export function MarketsChartPanel({ charted, view, chartData, loading, height = 380, testId, pressedState = false }) {
  const { activeMetrics, setActiveMetrics, range, setRange, normalized, setNormalized } = view;
  return (
    <div data-testid={testId} style={{ background: "#0A1520", border: "1px solid #1A2530", borderRadius: 2, padding: "24px 28px" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 24, flexWrap: "wrap", gap: 12 }}>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          {charted.map(m => {
            const on = activeMetrics.includes(m.code);
            return <button key={m.code} onClick={() => setActiveMetrics(prev => prev.includes(m.code) ? prev.filter(c => c !== m.code) : [...prev, m.code])} style={{ background: on ? `${m.color}18` : "transparent", border: `1px solid ${on ? m.color : "#1E2D3D"}`, color: on ? m.color : "#3A4D5C", borderRadius: 2, padding: "5px 12px", cursor: "pointer", fontFamily: "monospace", fontSize: 12, transition: "all 0.15s" }}>{m.label}</button>;
          })}
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <button aria-pressed={pressedState ? (normalized ? "true" : "false") : undefined} onClick={() => setNormalized(p => !p)} style={{ background: normalized ? "#1A2530" : "transparent", border: `1px solid ${normalized ? "#5A6878" : "#1E2D3D"}`, color: normalized ? "#8A9BAC" : "#3A4D5C", borderRadius: 2, padding: "5px 12px", cursor: "pointer", fontFamily: "monospace", fontSize: 11 }}>% CHANGE</button>
          <div style={{ display: "flex", border: "1px solid #1E2D3D", borderRadius: 2, overflow: "hidden" }}>
            {RANGES.map(r => <button key={r.label} onClick={() => setRange(r)} style={{ background: range.label === r.label ? "#1A2530" : "transparent", border: "none", borderLeft: "1px solid #1E2D3D", color: range.label === r.label ? "#C8A96E" : "#3A4D5C", padding: "5px 12px", cursor: "pointer", fontFamily: "monospace", fontSize: 12 }}>{r.label}</button>)}
          </div>
        </div>
      </div>
      {loading ? (
        <div style={{ height, display: "flex", alignItems: "center", justifyContent: "center", color: "#2A3540", fontFamily: "monospace", fontSize: 13 }}>fetching data...</div>
      ) : (
        <ResponsiveContainer width="100%" height={height}>
          <LineChart data={chartData} margin={{ top: 4, right: 8, bottom: 4, left: 8 }}>
            <CartesianGrid strokeDasharray="2 6" stroke="#0F1923" vertical={false} />
            <XAxis dataKey="date" tickFormatter={formatDate} tick={{ fill: "#3A4D5C", fontFamily: "monospace", fontSize: 11 }} axisLine={{ stroke: "#1A2530" }} tickLine={false} minTickGap={60} interval="preserveStartEnd" />
            <YAxis tick={{ fill: "#3A4D5C", fontFamily: "monospace", fontSize: 11 }} axisLine={false} tickLine={false} tickFormatter={v => normalized ? `${v.toFixed(1)}%` : v.toFixed(2)} width={52} />
            {normalized && <ReferenceLine y={0} stroke="#2A3540" strokeDasharray="4 4" />}
            <Tooltip content={<CustomTooltip />} />
            <Legend wrapperStyle={{ fontFamily: "monospace", fontSize: 11, color: "#5A6878", paddingTop: 16 }} formatter={(value) => charted.find(m => m.code === value)?.label || value} />
            {activeMetrics.map(code => {
              const m = charted.find(x => x.code === code);
              return <Line key={code} type="monotone" dataKey={code} name={code} stroke={m?.color} strokeWidth={1.5} dot={false} activeDot={{ r: 3, strokeWidth: 0 }} connectNulls />;
            })}
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
