import { useState } from "react";

import { SCENARIOS, scenarioOutcomes } from "../../lib/rateScenarios";

/**
 * Pick a rate path and see what it does to the long end.
 *
 * The scenarios and their consequences live in `lib/rateScenarios.js` — they
 * are editorial judgement worth stating in one place and testing, and a file
 * exporting both a component and a constant breaks fast refresh.
 */
export function RateScenarios() {
  const [scenario, setScenario] = useState(null);

  return (
    <div style={{ background: "#0A1520", border: "1px solid #1A2530", borderRadius: 2, padding: "20px 24px", marginBottom: 20 }}>
      <div style={{ fontFamily: "monospace", fontSize: 10, color: "#3A4D5C", letterSpacing: "0.1em", marginBottom: 4 }}>RATE CUT SCENARIO ANALYSIS</div>
      <div style={{ fontFamily: "monospace", fontSize: 11, color: "#5A6878", marginBottom: 16 }}>The Fed controls the short end. The bond market controls the long end. These are not the same thing.</div>
      <div style={{ display: "flex", gap: 8, marginBottom: 16, flexWrap: "wrap" }}>
        {SCENARIOS.map((s) => (
          <button key={s.label} onClick={() => setScenario(scenario?.label === s.label ? null : s)}
            style={{ background: scenario?.label === s.label ? `${s.color}18` : "transparent", border: `1px solid ${scenario?.label === s.label ? s.color : "#1E2D3D"}`, color: scenario?.label === s.label ? s.color : "#5A6878", borderRadius: 2, padding: "6px 14px", cursor: "pointer", fontFamily: "monospace", fontSize: 11 }}>
            {s.label}
          </button>
        ))}
      </div>
      {scenario ? (
        <div style={{ background: `${scenario.color}0D`, border: `1px solid ${scenario.color}33`, borderLeft: `3px solid ${scenario.color}`, borderRadius: 2, padding: "16px 20px" }}>
          <div style={{ fontFamily: "monospace", fontSize: 12, color: scenario.color, fontWeight: 700, marginBottom: 8 }}>{scenario.label}</div>
          <div style={{ fontFamily: "monospace", fontSize: 12, color: "#8A9BAC", lineHeight: 1.8, marginBottom: 12 }}>{scenario.desc}</div>
          <div style={{ display: "flex", gap: 20, flexWrap: "wrap" }}>
            {scenarioOutcomes(scenario).map((s) => (
              <div key={s.label}>
                <div style={{ fontFamily: "monospace", fontSize: 10, color: "#3A4D5C", marginBottom: 2 }}>{s.label}</div>
                <div style={{ fontFamily: "monospace", fontSize: 12, color: s.color, fontWeight: 600 }}>{s.val}</div>
              </div>
            ))}
          </div>
        </div>
      ) : (
        <div style={{ fontFamily: "monospace", fontSize: 11, color: "#2A3540", padding: "8px 0" }}>Select a scenario to see bond market implications.</div>
      )}
    </div>
  );
}
