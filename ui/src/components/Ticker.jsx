import { formatValue } from "../lib/format";

export function Ticker({ data }) {
  if (!data.length) return null;
  const items = [...data, ...data];
  return (
    <div style={{ overflow: "hidden", borderBottom: "1px solid #1A2530", background: "#080E14", padding: "6px 0" }}>
      <div style={{ display: "flex", gap: 48, whiteSpace: "nowrap", animation: "ticker 40s linear infinite", width: "max-content" }}>
        {items.map((item, i) => (
          <span key={i} style={{ fontFamily: "monospace", fontSize: 12, color: "#5A6878" }}>
            <span style={{ color: item.color, marginRight: 6 }}>{item.code}</span>
            <span style={{ color: "#8A9BAC" }}>{formatValue(item.latest, item.unit) ?? "—"}</span>
          </span>
        ))}
      </div>
      <style>{`@keyframes ticker { from { transform: translateX(0) } to { transform: translateX(-50%) } }`}</style>
    </div>
  );
}
