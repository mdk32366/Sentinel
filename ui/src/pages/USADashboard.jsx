import { useState } from "react";

import { latestValue, yoyPercent, yoySeries } from "../lib/usaSeries";
import { buildYieldSeries } from "../lib/yieldSeries";
import { useUSASeries } from "../hooks/useUSASeries";
import { BreakingPointCalculator } from "../components/usa/BreakingPointCalculator";
import { FeedbackLoop } from "../components/usa/FeedbackLoop";
import { M2GrowthChart } from "../components/usa/M2GrowthChart";
import { RateScenarios } from "../components/usa/RateScenarios";
import { USAKeyMetrics } from "../components/usa/USAKeyMetrics";
import { YieldCurveChart } from "../components/usa/YieldCurveChart";

const RANGES = [[365, "1Y"], [730, "2Y"], [1825, "5Y"], [3650, "10Y"]];

/**
 * The USA country view, rendered inside the COUNTRY tab.
 *
 * The US is the issuer of the asset every other country is monitored for
 * holding, so this page asks a different question from `CountryDetail`: not
 * "is this country selling?" but "can the issuer carry the debt?". Hence the
 * fiscal calculator rather than a holdings chart.
 */
export function USADashboard() {
  const [range, setRange] = useState(365 * 5);
  const [customRate, setCustomRate] = useState(null);

  const data = useUSASeries(range);

  const m2 = data["M2SL"] || [];

  return (
    <div>
      {/* Header */}
      <div style={{ marginBottom: 20 }}>
        <div style={{ fontFamily: "monospace", fontSize: 20, color: "#E8E0D0", fontWeight: 700, marginBottom: 4 }}>
          United States of America
          <span style={{ marginLeft: 12, fontSize: 11, color: "#3A4D5C" }}>USA · Treasury Issuer · Reserve Currency</span>
        </div>
        <div style={{ fontFamily: "monospace", fontSize: 11, color: "#5A6878", lineHeight: 1.7, maxWidth: 860 }}>
          The US is the <span style={{ color: "#C8A96E" }}>issuer</span> of the reserve asset being monitored globally.
          US stress is not forced selling — it&apos;s the Fed&apos;s ability to manage <span style={{ color: "#C8A96E" }}>$36T in debt</span> as
          foreign demand weakens, the dollar debasement math, and whether the bond market will accept the terms the Fed is offering.
        </div>
      </div>

      {/* Range */}
      <div style={{ display: "flex", gap: 6, marginBottom: 20 }}>
        {RANGES.map(([days, label]) => (
          <button key={label} onClick={() => setRange(days)}
            style={{ background: range === days ? "#1A2530" : "transparent", border: `1px solid ${range === days ? "#5A6878" : "#1E2D3D"}`, color: range === days ? "#C8A96E" : "#3A4D5C", borderRadius: 2, padding: "4px 12px", cursor: "pointer", fontFamily: "monospace", fontSize: 11 }}>
            {label}
          </button>
        ))}
      </div>

      <USAKeyMetrics
        dgs10={latestValue(data["DGS10"])}
        dgs2={latestValue(data["DGS2"])}
        fedfunds={latestValue(data["DFF"])}
        realYield={latestValue(data["DFII10"])}
        m2Yoy={yoyPercent(m2)}
        m2Latest={latestValue(m2)}
        cpiYoy={yoyPercent(data["CPIAUCSL"])}
        dxyLatest={latestValue(data["DTWEXBGS"])}
        spotGold={latestValue(data["GOLD_SPOT_USD"])}
      />

      <BreakingPointCalculator
        dgs10={latestValue(data["DGS10"])}
        customRate={customRate}
        onCustomRate={setCustomRate}
      />

      <YieldCurveChart rows={buildYieldSeries(data)} />

      <M2GrowthChart rows={yoySeries(m2)} current={yoyPercent(m2)} />

      <RateScenarios />

      <FeedbackLoop />
    </div>
  );
}
