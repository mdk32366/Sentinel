import {
  SPR_CAPACITY_MB, SPR_CURRENT_MB, US_GOLD_TONNES, usGoldValueT,
} from "../../lib/fiscal";

/**
 * The eight tiles across the top of the USA dashboard.
 *
 * `F-0057`: the US gold tile was priced at a hardcoded 4587 while
 * `GOLD_SPOT_USD` had been a live daily series since `D-0041` — an $85bn
 * overstatement against a months-old price. There is deliberately no fallback
 * constant: with no spot price the tile says so, rather than showing a
 * plausible wrong number.
 */
export function USAKeyMetrics({ dgs10, dgs2, fedfunds, realYield, m2Yoy, m2Latest, cpiYoy, dxyLatest, spotGold }) {
  const spread = dgs10 != null && dgs2 != null ? dgs10 - dgs2 : null;
  const goldValueT = usGoldValueT(spotGold);

  const tiles = [
    {
      label: "10Y Yield",
      val: dgs10 != null ? `${dgs10.toFixed(2)}%` : "—",
      color: "#C8A96E",
      sub: spread != null ? `Spread vs 2Y: ${spread > 0 ? "+" : ""}${spread.toFixed(2)}pp` : "",
    },
    { label: "Fed Funds", val: fedfunds != null ? `${fedfunds.toFixed(2)}%` : "—", color: "#5DB87A", sub: "" },
    {
      label: "Real Yield",
      val: realYield != null ? `${realYield.toFixed(2)}%` : "—",
      color: realYield != null && realYield < 0 ? "#E07B5A" : "#7EB8C9",
      sub: realYield != null && realYield < 0 ? "⚠ Financial repression" : "Positive",
    },
    {
      label: "M2 Growth YoY",
      val: m2Yoy != null ? `${m2Yoy.toFixed(1)}%` : "—",
      color: m2Yoy != null && m2Yoy > 10 ? "#E07B5A" : m2Yoy != null && m2Yoy > 5 ? "#E8C547" : "#5DB87A",
      sub: m2Yoy != null && m2Latest != null ? `$${(m2Latest / 1000).toFixed(1)}T total` : "",
    },
    {
      label: "CPI YoY",
      val: cpiYoy != null ? `${cpiYoy.toFixed(1)}%` : "—",
      color: cpiYoy != null && cpiYoy > 4 ? "#E07B5A" : cpiYoy != null && cpiYoy > 2 ? "#E8C547" : "#5DB87A",
      sub: cpiYoy != null && cpiYoy > 2 ? "Above 2% target" : "",
    },
    { label: "Dollar Index", val: dxyLatest != null ? dxyLatest.toFixed(1) : "—", color: "#7EC4A0", sub: "" },
    {
      label: "US Gold",
      val: `${US_GOLD_TONNES.toLocaleString()}t`,
      color: "#C8A96E",
      sub: goldValueT != null ? `$${goldValueT.toFixed(2)}T at $${spotGold.toFixed(0)}/oz` : "spot price unavailable",
    },
    {
      label: "SPR Level",
      val: `${SPR_CURRENT_MB}M bbl`,
      color: SPR_CURRENT_MB < 400 ? "#E07B5A" : "#5DB87A",
      sub: `${((SPR_CURRENT_MB / SPR_CAPACITY_MB) * 100).toFixed(0)}% of capacity (${SPR_CAPACITY_MB}M)`,
    },
  ];

  return (
    <div style={{ display: "flex", gap: 10, marginBottom: 20, flexWrap: "wrap" }}>
      {tiles.map((s) => (
        <div key={s.label} style={{ background: "#0F1923", border: "1px solid #1A2530", borderTop: `2px solid ${s.color}`, borderRadius: 2, padding: "12px 16px", flex: "1 1 130px" }}>
          <div style={{ fontFamily: "monospace", fontSize: 10, color: "#5A6878", textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 4 }}>{s.label}</div>
          <div style={{ fontFamily: "monospace", fontSize: 18, fontWeight: 700, color: s.color }}>{s.val}</div>
          {s.sub && <div style={{ fontFamily: "monospace", fontSize: 10, color: "#5A6878", marginTop: 3 }}>{s.sub}</div>}
        </div>
      ))}
    </div>
  );
}
