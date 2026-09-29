import { formatDate } from "../lib/format";
import { METRICS } from "../lib/constants";

export const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  return (
    <div style={{ background: "#0A1520", border: "1px solid #1E2D3D", borderRadius: 2, padding: "10px 14px", fontFamily: "monospace", fontSize: 12 }}>
      <div style={{ color: "#5A6878", marginBottom: 6 }}>{formatDate(label)}</div>
      {payload.map((p, i) => (
        <div key={i} style={{ color: p.color, marginBottom: 2 }}>
          {METRICS.find(m => m.code === p.name)?.label ?? p.name}:{" "}
          <span style={{ color: "#E8E0D0" }}>{p.value?.toFixed(3)}</span>
        </div>
      ))}
    </div>
  );
};
