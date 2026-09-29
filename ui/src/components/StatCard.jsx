import { formatValue } from "../lib/format";
import { InfoTip } from "./InfoTip";

/**
 * One of the twelve cards on MARKETS.
 *
 * `tip` and `stressRole` come from `METRICS`. The role line is the one that
 * matters: eight of the twelve series here are not read by any scorer, and a
 * card sitting on a sovereign-stress board implies otherwise unless it says
 * so. `D-0016` had to be ruled explicitly for exactly that reason.
 *
 * Gold for a scored series, grey for context — the same distinction the
 * colours make everywhere else here, where grey means "nothing to report"
 * rather than "something is wrong".
 */
export function StatCard({ label, value, unit, change, color, tip, stressRole, scored }) {
  const up = (change?.value ?? 0) >= 0;

  return (
    <InfoTip
      as="div"
      title={label}
      tip={tip}
      footer={stressRole}
      footerColor={scored ? "#C8A96E" : "#5A6878"}
      placement="below"
      align="left"
      tabIndex={tip ? 0 : undefined}
      style={{
        background: "#0F1923",
        border: `1px solid ${color}33`,
        borderTop: `2px solid ${color}`,
        borderRadius: 2,
        padding: "18px 22px",
        minWidth: 0,
        cursor: tip ? "help" : "default",
        outline: "none",
      }}
    >
      <div style={{ fontSize: 11, letterSpacing: "0.12em", color: "#5A6878", textTransform: "uppercase", marginBottom: 8, fontFamily: "monospace" }}>
        <span style={tip ? { borderBottom: "1px dashed #2A3D50", paddingBottom: 1 } : undefined}>{label}</span>
      </div>
      <div style={{ fontSize: 26, fontWeight: 700, color: "#E8E0D0", fontFamily: "monospace", lineHeight: 1 }}>
        {value != null ? formatValue(value, unit) : <span style={{ color: "#2A3540" }}>—</span>}
      </div>
      {change != null && (
        <div style={{ marginTop: 6, fontSize: 12, color: up ? "#5DB87A" : "#E07B5A", fontFamily: "monospace" }}>
          {up ? "▲" : "▼"} {Math.abs(change.value).toFixed(2)}{change.suffix} {change.window}
        </div>
      )}
    </InfoTip>
  );
}
