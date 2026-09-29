import { formatValue } from "../lib/format";

export function StatCard({ label, value, unit, change, color }) {
  const up = (change?.value ?? 0) >= 0;
  return (
    <div style={{ background: "#0F1923", border: `1px solid ${color}33`, borderTop: `2px solid ${color}`, borderRadius: 2, padding: "18px 22px", minWidth: 0 }}>
      <div style={{ fontSize: 11, letterSpacing: "0.12em", color: "#5A6878", textTransform: "uppercase", marginBottom: 8, fontFamily: "monospace" }}>{label}</div>
      <div style={{ fontSize: 26, fontWeight: 700, color: "#E8E0D0", fontFamily: "monospace", lineHeight: 1 }}>
        {value != null ? formatValue(value, unit) : <span style={{ color: "#2A3540" }}>—</span>}
      </div>
      {change != null && (
        <div style={{ marginTop: 6, fontSize: 12, color: up ? "#5DB87A" : "#E07B5A", fontFamily: "monospace" }}>
          {up ? "▲" : "▼"} {Math.abs(change.value).toFixed(2)}{change.suffix} {change.window}
        </div>
      )}
    </div>
  );
}
