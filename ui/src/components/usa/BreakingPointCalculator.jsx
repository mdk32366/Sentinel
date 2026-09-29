import {
  ANNUAL_REVENUE_T, breakingPointRate, crisisRate, dangerColor,
  interestCost, interestPercentOfRevenue, rateTable,
} from "../../lib/fiscal";
import { ColHeader } from "../ColHeader";

const BREAK = breakingPointRate();
const CRISIS = crisisRate();

/** Risk classification for a given interest/revenue percentage. */
function statusFor(pct) {
  if (pct >= 35) return { label: "⚡ CRISIS", color: "#FF4444" };
  if (pct >= 25) return { label: "⚠ DANGER", color: "#E07B5A" };
  if (pct >= 20) return { label: "WATCH", color: "#E8C547" };
  return { label: "OK", color: "#5DB87A" };
}

/**
 * The fiscal sensitivity table and its live readout.
 *
 * `A-0012`: every constant behind this is a hand-entered FY2024 actual or CBO
 * estimate, and the panel says so in its own footnote. It is a sensitivity,
 * not a forecast — the arithmetic lives in `lib/fiscal.js` with tests.
 */
export function BreakingPointCalculator({ dgs10, customRate, onCustomRate }) {
  const activeYield = customRate ?? dgs10 ?? 4.3;
  const activeInterest = interestCost(activeYield);
  const activeInterestPct = interestPercentOfRevenue(activeYield);
  const color = dangerColor(activeYield);
  const rows = rateTable();

  const headroom = dgs10 != null ? BREAK - (customRate ?? dgs10) : null;

  const readout = [
    { label: "Annual Interest Cost", val: `$${activeInterest.toFixed(2)}T`, color },
    { label: "% of Federal Revenue", val: `${activeInterestPct.toFixed(1)}%`, color },
    { label: "Warning zone (25%)", val: `${BREAK.toFixed(1)}% yield`, color: "#E07B5A" },
    { label: "Crisis zone (35%)", val: `${CRISIS.toFixed(1)}% yield`, color: "#FF4444" },
    {
      label: "Distance to warning",
      val: headroom == null ? "—"
        : headroom > 0 ? `+${headroom.toFixed(2)}pp headroom`
        : `${headroom.toFixed(2)}pp BREACHED`,
      color: headroom != null && headroom <= 0 ? "#FF4444" : "#5DB87A",
    },
  ];

  return (
    <div style={{ background: "#0A1520", border: `1px solid ${color}44`, borderLeft: `3px solid ${color}`, borderRadius: 2, padding: "20px 24px", marginBottom: 20 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16, flexWrap: "wrap", gap: 12 }}>
        <div>
          <div style={{ fontFamily: "monospace", fontSize: 12, color: "#8A9BAC", letterSpacing: "0.1em", marginBottom: 4 }}>FISCAL BREAKING POINT CALCULATOR</div>
          <div style={{ fontFamily: "monospace", fontSize: 11, color: "#5A6878" }}>
            At $36.2T debt · $6T rolling over annually · ${ANNUAL_REVENUE_T}T revenue · Every 100bps = <span style={{ color: "#C8A96E" }}>+$60B/yr in new interest</span>
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <span style={{ fontFamily: "monospace", fontSize: 11, color: "#5A6878" }}>Model 10Y at:</span>
          <input type="range" min="1" max="12" step="0.25" value={customRate ?? activeYield}
            onChange={(e) => onCustomRate(parseFloat(e.target.value))}
            style={{ width: 140, accentColor: "#C8A96E" }} />
          <span style={{ fontFamily: "monospace", fontSize: 14, color: "#C8A96E", minWidth: 40 }}>{(customRate ?? activeYield).toFixed(2)}%</span>
          {customRate && <button onClick={() => onCustomRate(null)} style={{ background: "transparent", border: "1px solid #1E2D3D", color: "#3A4D5C", borderRadius: 2, padding: "3px 8px", cursor: "pointer", fontFamily: "monospace", fontSize: 10 }}>reset</button>}
        </div>
      </div>

      <div style={{ display: "flex", gap: 16, marginBottom: 20, flexWrap: "wrap" }}>
        {readout.map((s) => (
          <div key={s.label} style={{ background: "#0F1923", borderRadius: 2, padding: "10px 16px", flex: "1 1 140px" }}>
            <div style={{ fontFamily: "monospace", fontSize: 10, color: "#5A6878", marginBottom: 4 }}>{s.label}</div>
            <div style={{ fontFamily: "monospace", fontSize: 16, fontWeight: 700, color: s.color }}>{s.val}</div>
          </div>
        ))}
      </div>

      <table style={{ width: "100%", borderCollapse: "collapse", marginBottom: 12 }}>
        <thead>
          <tr>
            <ColHeader label="10Y Yield" tip="Hypothetical 10-year Treasury yield scenario. The current live value is highlighted. Each row shows what happens to US debt service costs if the 10Y yield settles at this level." align="right" style={{ padding: "6px 12px" }} />
            <ColHeader label="Annual Interest" tip="Projected annual interest expense in trillions, calculated as: locked-in cost ($0.55T) + new rollover debt ($6T/yr) × this yield rate. Based on FY2024 actuals and CBO debt maturity estimates." align="right" style={{ padding: "6px 12px" }} />
            <ColHeader label="% of Revenue" tip="Interest expense as a percentage of projected federal revenue (~$4.9T/yr). The 25% threshold is considered the emerging-market danger zone. Above 35% is Japan-level fiscal stress." align="right" style={{ padding: "6px 12px" }} />
            <ColHeader label="Status" tip="Risk classification: OK = interest <20% of revenue (manageable); WATCH = 20–25% (monitor closely); DANGER = 25–35% (emerging market threshold crossed); CRISIS = >35% (debt spiral risk, Japan 2024 analog)." align="right" style={{ padding: "6px 12px" }} />
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const isCurrent = Math.abs(row.rate - (customRate ?? dgs10 ?? 4.3)) < 0.3;
            const isBreak = row.rate >= BREAK && row.rate < BREAK + 0.6;
            const isCrisis = row.rate >= CRISIS && row.rate < CRISIS + 0.6;
            const status = statusFor(row.pct);
            return (
              <tr key={row.rate} style={{ background: isCurrent ? "#C8A96E0D" : "transparent", borderBottom: "1px solid #0F1923" }}>
                <td style={{ padding: "7px 12px", fontFamily: "monospace", fontSize: 12, color: isCurrent ? "#C8A96E" : "#E8E0D0", textAlign: "right", fontWeight: isCurrent ? 700 : 400 }}>
                  {row.rate.toFixed(1)}% {isCurrent ? "← current" : ""} {isBreak ? "← warning threshold" : ""} {isCrisis ? "← crisis threshold" : ""}
                </td>
                <td style={{ padding: "7px 12px", fontFamily: "monospace", fontSize: 12, color: "#8A9BAC", textAlign: "right" }}>${row.cost.toFixed(2)}T/yr</td>
                <td style={{ padding: "7px 12px", fontFamily: "monospace", fontSize: 12, color: status.color, textAlign: "right" }}>{row.pct.toFixed(1)}%</td>
                <td style={{ padding: "7px 12px", textAlign: "right" }}>
                  <span style={{ fontFamily: "monospace", fontSize: 10, color: status.color, background: `${status.color}18`, border: `1px solid ${status.color}44`, borderRadius: 2, padding: "1px 6px" }}>{status.label}</span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <div style={{ fontFamily: "monospace", fontSize: 10, color: "#2A3540" }}>
        Assumptions: $36.2T total debt · $6T annual rollover · $4.9T revenue · $0.55T existing locked-in interest · Danger = 25% interest/revenue (EM threshold) · Crisis = 35% (Japan-level)
      </div>
    </div>
  );
}
