import { useState, useEffect, useCallback } from "react";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, ReferenceLine, BarChart, Bar, Cell } from "recharts";

const API = window.location.hostname === "localhost" ? "http://localhost:8000/api" : "/api";

const METRICS = [
  { code: "DGS10",      label: "10Y Treasury",  color: "#C8A96E", unit: "%" },
  { code: "DGS5",       label: "5Y Treasury",   color: "#7EB8C9", unit: "%" },
  { code: "DGS2",       label: "2Y Treasury",   color: "#9B8EC4", unit: "%" },
  { code: "FEDFUNDS",   label: "Fed Funds",     color: "#5DB87A", unit: "%" },
  { code: "DFII10",     label: "Real Yield",    color: "#E8C547", unit: "%" },
  { code: "DCOILWTICO", label: "WTI Crude Oil", color: "#E07B5A", unit: "$/bbl" },
  { code: "DTWEXBGS",   label: "Dollar Index",  color: "#7EC4A0", unit: "" },
  { code: "CPIAUCSL",   label: "CPI",           color: "#C47EB8", unit: "" },
  { code: "M2SL",       label: "M2 Money",      color: "#6A8FC4", unit: "B$" },

];

const RANGES = [
  { label: "6M",  days: 180 },
  { label: "1Y",  days: 365 },
  { label: "2Y",  days: 730 },
  { label: "5Y",  days: 1825 },
];

const TABS = ["MARKETS", "HOLDINGS", "CROSS-ASSET", "GOLD", "COMPOSITE", "STRESS", "COUNTRY", "ADMIN", "ABOUT"];

function formatDate(d) {
  return new Date(d).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "2-digit" });
}

function formatValue(v, unit) {
  if (v == null) return null;
  if (unit === "%") return `${v.toFixed(2)}%`;
  if (unit === "$/bbl") return `$${v.toFixed(2)}`;
  if (unit === "B$") return `$${(v / 1000).toFixed(1)}T`;
  return v.toFixed(2);
}

function scoreColor(score) {
  if (score >= 50) return "#E07B5A";
  if (score >= 25) return "#E8C547";
  return "#5A6878";
}

function tierColor(tier) {
  if (tier === "DIVERGENCE")    return "#FF4444";
  if (tier === "CROSS_ASSET")   return "#E07B5A";
  if (tier === "TREASURY_ONLY") return "#E8C547";
  if (tier === "GOLD_ONLY")     return "#C8A96E";
  return "#5A6878";
}

function tierLabel(tier) {
  if (tier === "DIVERGENCE")    return "⚡ DIVERGENCE";
  if (tier === "CROSS_ASSET")   return "⚠ CROSS-ASSET";
  if (tier === "TREASURY_ONLY") return "T-ONLY";
  if (tier === "GOLD_ONLY")     return "Au ONLY";
  return tier;
}

// ── Shared UI ─────────────────────────────────────────────────────────────────

function StatCard({ label, value, unit, change, color }) {
  const up = change >= 0;
  return (
    <div style={{ background: "#0F1923", border: `1px solid ${color}33`, borderTop: `2px solid ${color}`, borderRadius: 2, padding: "18px 22px", minWidth: 0 }}>
      <div style={{ fontSize: 11, letterSpacing: "0.12em", color: "#5A6878", textTransform: "uppercase", marginBottom: 8, fontFamily: "monospace" }}>{label}</div>
      <div style={{ fontSize: 26, fontWeight: 700, color: "#E8E0D0", fontFamily: "monospace", lineHeight: 1 }}>
        {value != null ? formatValue(value, unit) : <span style={{ color: "#2A3540" }}>—</span>}
      </div>
      {change != null && (
        <div style={{ marginTop: 6, fontSize: 12, color: up ? "#5DB87A" : "#E07B5A", fontFamily: "monospace" }}>
          {up ? "▲" : "▼"} {Math.abs(change).toFixed(2)}{unit === "%" ? "pp" : "%"} vs 30d
        </div>
      )}
    </div>
  );
}

function Ticker({ data }) {
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

const CustomTooltip = ({ active, payload, label }) => {
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

function AlertBanner({ message, color = "#E07B5A" }) {
  return (
    <div style={{ background: `${color}15`, border: `1px solid ${color}44`, borderLeft: `3px solid ${color}`, borderRadius: 2, padding: "10px 16px", marginBottom: 12, fontFamily: "monospace", fontSize: 12, color }}>
      ⚠ {message}
    </div>
  );
}

function StressBar({ score, max = 100 }) {
  const w = Math.min(100, (score / max) * 100);
  const color = scoreColor(score);
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <div style={{ flex: 1, background: "#0F1923", borderRadius: 2, height: 6, overflow: "hidden" }}>
        <div style={{ width: `${w}%`, background: color, height: "100%", borderRadius: 2, transition: "width 0.3s" }} />
      </div>
      <span style={{ fontFamily: "monospace", fontSize: 11, color, minWidth: 32, textAlign: "right" }}>{score.toFixed(0)}</span>
    </div>
  );
}

// ── Country Detail (shared between HOLDINGS and COUNTRY tabs) ─────────────────


// Sovereign yield FRED codes
const SOVEREIGN_YIELD_CODES = {
  JPN: "IRLTLT01JPM156N", DEU: "IRLTLT01DEM156N", ITA: "IRLTLT01ITM156N",
  FRA: "IRLTLT01FRM156N", ESP: "IRLTLT01ESM156N", GBR: "IRLTLT01GBM156N",
  AUS: "IRLTLT01AUM156N", CAN: "IRLTLT01CAM156N",
  NLD: "IRLTLT01NLM156N", NOR: "IRLTLT01NOM156N", SWE: "IRLTLT01SEM156N",
  CHE: "IRLTLT01CHM156N", BEL: "IRLTLT01BEM156N", KOR: "IRLTLT01KRM156N",
};


function CountryDetail({ iso, onClose, standalone = false, latestAll = {} }) {
  const [ticHistory, setTicHistory] = useState(null);
  const [goldHistory, setGoldHistory] = useState(null);
  const [loading, setLoading] = useState(true);
  const [narrative, setNarrative] = useState(null);
  const [narrativeLoading, setNarrativeLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    setNarrative(null);
    const end = new Date();
    const start = new Date();
    start.setFullYear(start.getFullYear() - 3);
    Promise.all([
      fetch(`${API}/holdings/${iso}?start_date=${start.toISOString()}&end_date=${end.toISOString()}`).then(r => r.json()).catch(() => null),
      fetch(`${API}/gold-reserves/${iso}`).then(r => r.json()).catch(() => null),
    ]).then(([tic, gold]) => {
      setTicHistory(tic);
      setGoldHistory(gold);
      setLoading(false);
    });
  }, [iso]);

  const handleGenerateNarrative = async (ticChart, goldChart, latestTic, ticMom, latestGold) => {
    setNarrativeLoading(true);
    setNarrative(null);
    try {
      const yieldCode = SOVEREIGN_YIELD_CODES[iso];
      const countryYield = yieldCode ? latestAll[yieldCode] : null;
      const us10y = latestAll["DGS10"];
      const spreadBps = countryYield != null && us10y != null ? (countryYield - us10y) * 100 : null;
      const prompt = `You are a financial analyst writing a concise 200-250 word brief for a sophisticated audience. Analyze ${ticHistory?.country_name ?? iso} (${iso}) based on this data:

TREASURY HOLDINGS: ${latestTic ? `$${latestTic.holdings.toFixed(1)}B current` : "no data"}${ticMom != null ? `, MoM ${ticMom > 0 ? "+" : ""}${ticMom.toFixed(2)}%` : ""}, ${ticChart.length} months of history
GOLD RESERVES: ${latestGold ? `${latestGold.tonnes.toFixed(0)} metric tonnes` : "no data"}
SOVEREIGN YIELD SPREAD VS US 10Y: ${spreadBps != null ? `${spreadBps > 0 ? "+" : ""}${spreadBps.toFixed(0)} basis points` : "not available"}

Write three short sections:

SITUATION
What is this country doing with its US Treasury holdings and gold reserves? 2-3 plain sentences using the real numbers.

WHAT TO WATCH
What trends matter most right now? What would signal a change in posture? 2-3 sentences.

RISK FACTORS
What are the top 2 risks to monitor? Be specific. 2 sentences.

Use plain English. No markdown formatting. No bullet points.`;

      const r = await fetch(`${API}/analyze/country`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt }),
      });
      const data = await r.json();
      setNarrative(data.text || "Analysis unavailable.");
    } catch (e) {
      setNarrative("Failed to generate analysis. Please try again.");
    }
    setNarrativeLoading(false);
  };

  if (loading) return <div style={{ padding: 24, fontFamily: "monospace", fontSize: 13, color: "#3A4D5C" }}>loading {iso}...</div>;

  const container = standalone
    ? { background: "#080E14", minHeight: "100%" }
    : { background: "#0A1520", border: "1px solid #1A2530", borderRadius: 2, padding: 24, marginTop: 12 };

  const ticChart = (ticHistory?.holdings || []).map(h => ({
    date: h.date.split("T")[0],
    holdings: h.holdings_billions_usd,
  }));

  const goldChart = (goldHistory?.reserves || []).map(h => ({
    date: h.date.split("T")[0],
    tonnes: h.metric_tonnes,
  }));

  const latestTic = ticChart[ticChart.length - 1];
  const prevTic = ticChart[ticChart.length - 2];
  const ticMom = latestTic && prevTic ? ((latestTic.holdings - prevTic.holdings) / prevTic.holdings * 100) : null;
  const latestGold = goldChart[goldChart.length - 1];
  const yieldCode = SOVEREIGN_YIELD_CODES[iso];
  const countryYield = yieldCode ? latestAll[yieldCode] : null;
  const us10y = latestAll["DGS10"];
  const spreadBps = countryYield != null && us10y != null ? (countryYield - us10y) * 100 : null;
  const spreadColor = spreadBps == null ? "#3A4D5C" : spreadBps > 150 ? "#FF4444" : spreadBps > 50 ? "#E07B5A" : spreadBps > 0 ? "#E8C547" : "#7EB8C9";

  return (
    <div style={container}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 20 }}>
        <div>
          <div style={{ fontFamily: "monospace", fontSize: 10, color: "#5A6878", letterSpacing: "0.1em", marginBottom: 4 }}>COUNTRY DETAIL</div>
          <div style={{ fontFamily: "monospace", fontSize: 20, color: "#E8E0D0", fontWeight: 700 }}>
            {ticHistory?.country_name ?? goldHistory?.country_name ?? iso}
            <span style={{ marginLeft: 10, fontSize: 13, color: "#3A4D5C" }}>{iso}</span>
          </div>
        </div>
        {onClose && (
          <button onClick={onClose} style={{ background: "transparent", border: "1px solid #1E2D3D", color: "#5A6878", borderRadius: 2, padding: "6px 14px", cursor: "pointer", fontFamily: "monospace", fontSize: 12 }}>✕</button>
        )}
      </div>

      {/* Exited position banner */}
      {ticHistory?.data_points === 0 && goldChart.length > 0 && (
        <div style={{ background: "#FF444415", border: "1px solid #FF444444", borderLeft: "4px solid #FF4444", borderRadius: 2, padding: "12px 18px", marginBottom: 20 }}>
          <div style={{ fontFamily: "monospace", fontSize: 12, color: "#FF4444", fontWeight: 700, marginBottom: 4 }}>
            ⚠ COMPLETED TREASURY LIQUIDATION
          </div>
          <div style={{ fontFamily: "monospace", fontSize: 11, color: "#8A9BAC", lineHeight: 1.6 }}>
            {ticHistory?.country_name ?? iso} holds zero US Treasury securities. Position has been fully exited.
            {goldChart.length > 0 && ` Gold reserves: ${goldChart[goldChart.length-1]?.tonnes?.toFixed(0)}t — gold accumulation pattern confirms de-dollarization posture.`}
          </div>
        </div>
      )}

      {/* Stat cards */}
      <div style={{ display: "flex", gap: 12, marginBottom: 24, flexWrap: "wrap" }}>
        {[
          {
            label: "T-Bill Holdings",
            val: latestTic ? `$${latestTic.holdings.toFixed(1)}B` : ticHistory?.data_points === 0 ? "EXITED" : "—",
            color: latestTic ? "#C8A96E" : ticHistory?.data_points === 0 ? "#FF4444" : "#3A4D5C",
            sub: ticHistory?.data_points === 0 ? "Zero US Treasuries held" : null,
          },
          {
            label: "MoM Change",
            val: ticMom != null ? `${ticMom > 0 ? "+" : ""}${ticMom.toFixed(2)}%` : ticHistory?.data_points === 0 ? "N/A" : "—",
            color: ticMom == null ? "#3A4D5C" : ticMom < 0 ? "#E07B5A" : "#5DB87A"
          },
          { label: "Gold Reserves", val: latestGold ? `${latestGold.tonnes.toFixed(0)}t` : "—", color: "#E8C547" },
          { label: "Sovereign Yield", val: countryYield != null ? `${countryYield.toFixed(2)}%` : "—", color: "#7EB8C9" },
          { label: "Spread vs US 10Y", val: spreadBps != null ? `${spreadBps > 0 ? "+" : ""}${spreadBps.toFixed(0)}bps` : "—", color: spreadColor },
        ].map(s => (
          <div key={s.label} style={{ background: "#0F1923", border: `1px solid ${s.color}22`, borderTop: `2px solid ${s.color}`, borderRadius: 2, padding: "12px 16px", flex: "1 1 120px" }}>
            <div style={{ fontFamily: "monospace", fontSize: 10, color: "#5A6878", textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 4 }}>{s.label}</div>
            <div style={{ fontFamily: "monospace", fontSize: 16, fontWeight: 700, color: s.color }}>{s.val}</div>
            {s.sub && <div style={{ fontFamily: "monospace", fontSize: 10, color: s.color, marginTop: 3, opacity: 0.8 }}>{s.sub}</div>}
          </div>
        ))}
      </div>

      {/* Charts */}
      <div style={{ display: "grid", gridTemplateColumns: ticChart.length && goldChart.length ? "1fr 1fr" : "1fr", gap: 16 }}>
        {ticChart.length > 0 && (
          <div style={{ background: "#0F1923", border: "1px solid #1A2530", borderRadius: 2, padding: "16px 20px" }}>
            <div style={{ fontFamily: "monospace", fontSize: 11, color: "#5A6878", marginBottom: 12, letterSpacing: "0.1em" }}>TREASURY HOLDINGS ($B) — {ticHistory?.data_points} months</div>
            <ResponsiveContainer width="100%" height={160}>
              <LineChart data={ticChart} margin={{ top: 4, right: 8, bottom: 4, left: 8 }}>
                <CartesianGrid strokeDasharray="2 6" stroke="#0A1520" vertical={false} />
                <XAxis dataKey="date" tickFormatter={formatDate} tick={{ fill: "#3A4D5C", fontFamily: "monospace", fontSize: 10 }} axisLine={false} tickLine={false} minTickGap={60} />
                <YAxis tick={{ fill: "#3A4D5C", fontFamily: "monospace", fontSize: 10 }} axisLine={false} tickLine={false} width={48} tickFormatter={v => `$${v.toFixed(0)}B`} />
                <Tooltip formatter={v => [`$${v.toFixed(1)}B`, "Holdings"]} contentStyle={{ background: "#0A1520", border: "1px solid #1E2D3D", borderRadius: 2, fontFamily: "monospace", fontSize: 11 }} labelFormatter={formatDate} labelStyle={{ color: "#5A6878" }} />
                <Line type="monotone" dataKey="holdings" stroke="#C8A96E" strokeWidth={1.5} dot={false} activeDot={{ r: 3 }} connectNulls />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
        {goldChart.length > 0 && (
          <div style={{ background: "#0F1923", border: "1px solid #1A2530", borderRadius: 2, padding: "16px 20px" }}>
            <div style={{ fontFamily: "monospace", fontSize: 11, color: "#5A6878", marginBottom: 12, letterSpacing: "0.1em" }}>GOLD RESERVES (tonnes) — {goldHistory?.data_points} quarters</div>
            <ResponsiveContainer width="100%" height={160}>
              <LineChart data={goldChart} margin={{ top: 4, right: 8, bottom: 4, left: 8 }}>
                <CartesianGrid strokeDasharray="2 6" stroke="#0A1520" vertical={false} />
                <XAxis dataKey="date" tickFormatter={formatDate} tick={{ fill: "#3A4D5C", fontFamily: "monospace", fontSize: 10 }} axisLine={false} tickLine={false} minTickGap={60} />
                <YAxis tick={{ fill: "#3A4D5C", fontFamily: "monospace", fontSize: 10 }} axisLine={false} tickLine={false} width={48} tickFormatter={v => `${v.toFixed(0)}t`} />
                <Tooltip formatter={v => [`${v.toFixed(1)}t`, "Gold"]} contentStyle={{ background: "#0A1520", border: "1px solid #1E2D3D", borderRadius: 2, fontFamily: "monospace", fontSize: 11 }} labelFormatter={formatDate} labelStyle={{ color: "#5A6878" }} />
                <Line type="monotone" dataKey="tonnes" stroke="#E8C547" strokeWidth={1.5} dot={false} activeDot={{ r: 3 }} connectNulls />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>

      {!ticChart.length && !goldChart.length && (
        <div style={{ fontFamily: "monospace", fontSize: 13, color: "#3A4D5C", padding: 24, textAlign: "center" }}>No data available for {iso}</div>
      )}

      {/* AI Narrative */}
      {(ticChart.length > 0 || goldChart.length > 0) && (
        <div style={{ background: "#060D14", border: "1px solid #C8A96E33", borderLeft: "3px solid #C8A96E", borderRadius: 2, padding: "16px 20px", marginTop: 16 }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: narrative || narrativeLoading ? 16 : 0 }}>
            <div>
              <div style={{ fontFamily: "monospace", fontSize: 11, color: "#C8A96E", letterSpacing: "0.1em", marginBottom: 2 }}>SENTINEL ANALYST BRIEF</div>
              {!narrative && !narrativeLoading && <div style={{ fontFamily: "monospace", fontSize: 11, color: "#3A4D5C" }}>AI-generated analysis using treasury, gold, and yield spread data</div>}
            </div>
            <button
              onClick={() => handleGenerateNarrative(ticChart, goldChart, latestTic, ticMom, latestGold)}
              disabled={narrativeLoading}
              style={{ background: narrativeLoading ? "#0F1923" : "#C8A96E18", border: `1px solid ${narrativeLoading ? "#1E2D3D" : "#C8A96E"}`, color: narrativeLoading ? "#3A4D5C" : "#C8A96E", borderRadius: 2, padding: "8px 16px", cursor: narrativeLoading ? "not-allowed" : "pointer", fontFamily: "monospace", fontSize: 12, whiteSpace: "nowrap" }}>
              {narrativeLoading ? "⟳ Generating..." : narrative ? "↻ Regenerate" : "▶ Generate Analysis"}
            </button>
          </div>
          {narrativeLoading && <div style={{ fontFamily: "monospace", fontSize: 12, color: "#3A4D5C", lineHeight: 1.8 }}>Analyzing treasury holdings, gold reserves, and sovereign spread data...</div>}
          {narrative && !narrativeLoading && (
            <div style={{ borderTop: "1px solid #1A2530", paddingTop: 14 }}>
              {narrative.split("\n").map((line, i) => {
                const trimmed = line.trim();
                if (!trimmed) return <div key={i} style={{ height: 6 }} />;
                const isHeader = /^(SITUATION|WHAT TO WATCH|RISK FACTORS)/i.test(trimmed);
                if (isHeader) return <div key={i} style={{ fontFamily: "monospace", fontSize: 10, color: "#C8A96E", letterSpacing: "0.1em", textTransform: "uppercase", marginBottom: 4, marginTop: i > 0 ? 14 : 0 }}>{trimmed}</div>;
                return <div key={i} style={{ fontFamily: "monospace", fontSize: 12, color: "#8A9BAC", lineHeight: 1.8, marginBottom: 2 }}>{trimmed}</div>;
              })}
              <div style={{ fontFamily: "monospace", fontSize: 10, color: "#1E2D3D", marginTop: 12, borderTop: "1px solid #1A2530", paddingTop: 8 }}>
                Generated by Claude Haiku · Data: US Treasury TIC · World Gold Council · FRED
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
// ── Holdings Tab ──────────────────────────────────────────────────────────────

function StressTable({ countries, onSelect, selected }) {
  const [sort, setSort] = useState("stress_score");
  const sorted = [...countries].sort((a, b) => {
    if (sort === "stress_score") return b.stress_score - a.stress_score;
    if (sort === "mom") return (a.mom_change_pct ?? 0) - (b.mom_change_pct ?? 0);
    if (sort === "consecutive") return b.consecutive_declining_months - a.consecutive_declining_months;
    if (sort === "holdings") return b.latest_holdings_bn - a.latest_holdings_bn;
    return 0;
  });
  const col = (label, key) => (
    <th onClick={() => setSort(key)} style={{ fontFamily: "monospace", fontSize: 10, letterSpacing: "0.1em", color: sort === key ? "#C8A96E" : "#3A4D5C", textTransform: "uppercase", padding: "8px 12px", textAlign: "right", cursor: "pointer", borderBottom: "1px solid #1A2530", whiteSpace: "nowrap" }}>
      {label} {sort === key ? "↓" : ""}
    </th>
  );
  return (
    <div style={{ overflowX: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr>
            <th style={{ fontFamily: "monospace", fontSize: 10, color: "#3A4D5C", textTransform: "uppercase", padding: "8px 12px", textAlign: "left", borderBottom: "1px solid #1A2530" }}>Country</th>
            <th style={{ fontFamily: "monospace", fontSize: 10, color: "#3A4D5C", textTransform: "uppercase", padding: "8px 12px", textAlign: "left", borderBottom: "1px solid #1A2530" }}>Region</th>
            {col("Holdings $B", "holdings")}
            {col("MoM %", "mom")}
            {col("Consec ↓", "consecutive")}
            <th style={{ fontFamily: "monospace", fontSize: 10, color: "#3A4D5C", textTransform: "uppercase", padding: "8px 12px", borderBottom: "1px solid #1A2530", minWidth: 120 }}>Stress</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map(c => {
            const isSelected = selected?.country_iso === c.country_iso;
            const alertColor = c.alert ? scoreColor(c.stress_score) : null;
            return (
              <tr key={c.country_iso} onClick={() => onSelect(isSelected ? null : c)}
                style={{ cursor: "pointer", background: isSelected ? "#0F1923" : "transparent", borderBottom: "1px solid #0F1923" }}
                onMouseEnter={e => e.currentTarget.style.background = "#0D1820"}
                onMouseLeave={e => e.currentTarget.style.background = isSelected ? "#0F1923" : "transparent"}>
                <td style={{ padding: "10px 12px", fontFamily: "monospace", fontSize: 13, color: "#E8E0D0" }}>
                  {c.alert && <span style={{ color: alertColor, marginRight: 6 }}>●</span>}
                  {c.country_name}<span style={{ marginLeft: 6, fontSize: 10, color: "#3A4D5C" }}>{c.country_iso}</span>
                </td>
                <td style={{ padding: "10px 12px", fontFamily: "monospace", fontSize: 11, color: "#5A6878" }}>{c.region}</td>
                <td style={{ padding: "10px 12px", fontFamily: "monospace", fontSize: 13, color: "#8A9BAC", textAlign: "right" }}>{c.latest_holdings_bn != null ? `$${c.latest_holdings_bn.toFixed(1)}B` : "—"}</td>
                <td style={{ padding: "10px 12px", fontFamily: "monospace", fontSize: 13, textAlign: "right", color: c.mom_change_pct == null ? "#3A4D5C" : c.mom_change_pct < 0 ? "#E07B5A" : "#5DB87A" }}>
                  {c.mom_change_pct != null ? `${c.mom_change_pct > 0 ? "+" : ""}${c.mom_change_pct.toFixed(2)}%` : "—"}
                </td>
                <td style={{ padding: "10px 12px", fontFamily: "monospace", fontSize: 13, textAlign: "right", color: c.consecutive_declining_months >= 3 ? "#E07B5A" : "#8A9BAC" }}>
                  {c.consecutive_declining_months > 0 ? `${c.consecutive_declining_months}mo` : "—"}
                </td>
                <td style={{ padding: "10px 12px", minWidth: 140 }}><StressBar score={c.stress_score} /></td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function HoldingsTab({ onCountrySelect, latestAll = {} }) {
  const [holdings, setHoldings] = useState(null);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState(null);
  const [sort, setSort] = useState("holdings");

  useEffect(() => {
    fetch(`${API}/holdings`)
      .then(r => r.json())
      .then(d => { setHoldings(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  if (loading) return <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: 300, fontFamily: "monospace", fontSize: 13, color: "#3A4D5C" }}>loading...</div>;
  if (!holdings) return <div style={{ fontFamily: "monospace", color: "#E07B5A", padding: 24 }}>No TIC data. Run POST /api/fetch/treasury-holdings</div>;

  const rows = [...(holdings.holdings || [])].sort((a, b) => {
    if (sort === "holdings") return b.holdings_billions_usd - a.holdings_billions_usd;
    if (sort === "pct") return b.percent_of_total - a.percent_of_total;
    if (sort === "country") return a.country_name.localeCompare(b.country_name);
    return 0;
  });

  const total = holdings.total_billions_usd;
  const asOf = holdings.date ? new Date(holdings.date).toLocaleDateString("en-US", { month: "short", year: "numeric" }) : "—";
  const top3pct = rows.slice(0, 3).reduce((s, r) => s + r.percent_of_total, 0);

  const col = (label, key) => (
    <th onClick={() => setSort(key)} style={{ fontFamily: "monospace", fontSize: 10, letterSpacing: "0.1em", color: sort === key ? "#C8A96E" : "#3A4D5C", textTransform: "uppercase", padding: "8px 16px", textAlign: "right", cursor: "pointer", borderBottom: "1px solid #1A2530", whiteSpace: "nowrap" }}>
      {label} {sort === key ? "↓" : ""}
    </th>
  );

  return (
    <div>
      {/* Summary cards */}
      <div style={{ display: "flex", gap: 12, marginBottom: 20, flexWrap: "wrap" }}>
        {[
          { label: "Total Foreign Holdings", val: `$${(total / 1000).toFixed(2)}T` },
          { label: "Countries Reporting", val: rows.length },
          { label: "Top Holder", val: rows[0]?.country_code ?? "—" },
          { label: "Top 3 Concentration", val: `${top3pct.toFixed(1)}%`, alert: top3pct > 40 },
          { label: "Data As Of", val: asOf },
        ].map(s => (
          <div key={s.label} style={{ background: "#0F1923", border: `1px solid ${s.alert ? "#E07B5A33" : "#1A2530"}`, borderTop: `2px solid ${s.alert ? "#E07B5A" : "#1A2530"}`, borderRadius: 2, padding: "14px 20px", flex: "1 1 140px" }}>
            <div style={{ fontFamily: "monospace", fontSize: 10, color: "#5A6878", textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 6 }}>{s.label}</div>
            <div style={{ fontFamily: "monospace", fontSize: 20, fontWeight: 700, color: s.alert ? "#E07B5A" : "#E8E0D0" }}>{s.val}</div>
          </div>
        ))}
      </div>

      {/* Top 8 quick cards */}
      <div style={{ display: "flex", gap: 8, marginBottom: 20, flexWrap: "wrap" }}>
        {rows.slice(0, 8).map(c => (
          <div key={c.country_code}
            onClick={() => onCountrySelect(c.country_code)}
            style={{ background: "#0A1520", border: "1px solid #1A2530", borderRadius: 2, padding: "8px 14px", cursor: "pointer", flex: "1 1 110px", maxWidth: 160 }}>
            <div style={{ fontFamily: "monospace", fontSize: 10, color: "#5A6878" }}>{c.country_code}</div>
            <div style={{ fontFamily: "monospace", fontSize: 13, color: "#E8E0D0", marginTop: 2 }}>${c.holdings_billions_usd.toFixed(0)}B</div>
            <div style={{ fontFamily: "monospace", fontSize: 11, color: "#C8A96E", marginTop: 2 }}>{c.percent_of_total.toFixed(1)}%</div>
          </div>
        ))}
      </div>

      {/* Inline country detail */}
      {selected && (
        <CountryDetail iso={selected.country_code} onClose={() => setSelected(null)} latestAll={latestAll.latest ?? {}} />
      )}

      {/* Full holdings table */}
      <div style={{ background: "#0A1520", border: "1px solid #1A2530", borderRadius: 2, padding: "20px 0" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "0 20px 16px" }}>
          <div style={{ fontFamily: "monospace", fontSize: 12, color: "#8A9BAC", letterSpacing: "0.1em" }}>
            FOREIGN TREASURY HOLDINGS
            <span style={{ marginLeft: 10, fontSize: 10, color: "#3A4D5C" }}>click row for history · click ISO card for full view</span>
          </div>
        </div>
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr>
                <th style={{ fontFamily: "monospace", fontSize: 10, color: "#3A4D5C", textTransform: "uppercase", padding: "8px 16px", textAlign: "left", borderBottom: "1px solid #1A2530" }}>Country</th>
                {col("Holdings ($B)", "holdings")}
                {col("% of Total", "pct")}
                <th style={{ fontFamily: "monospace", fontSize: 10, color: "#3A4D5C", textTransform: "uppercase", padding: "8px 16px", borderBottom: "1px solid #1A2530", minWidth: 160 }}>Share</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((c, i) => {
                const isSelected = selected?.country_code === c.country_code;
                return (
                  <tr key={c.country_code}
                    onClick={() => setSelected(isSelected ? null : c)}
                    style={{ cursor: "pointer", background: isSelected ? "#0F1923" : "transparent", borderBottom: "1px solid #0F1923" }}
                    onMouseEnter={e => e.currentTarget.style.background = "#0D1820"}
                    onMouseLeave={e => e.currentTarget.style.background = isSelected ? "#0F1923" : "transparent"}>
                    <td style={{ padding: "10px 16px", fontFamily: "monospace", fontSize: 13, color: "#E8E0D0" }}>
                      <span style={{ color: "#3A4D5C", fontSize: 10, marginRight: 8 }}>{i + 1}</span>
                      {c.country_name}
                      <span style={{ marginLeft: 8, fontSize: 10, color: "#3A4D5C" }}>{c.country_code}</span>
                    </td>
                    <td style={{ padding: "10px 16px", fontFamily: "monospace", fontSize: 13, color: "#8A9BAC", textAlign: "right" }}>${c.holdings_billions_usd.toFixed(1)}B</td>
                    <td style={{ padding: "10px 16px", fontFamily: "monospace", fontSize: 13, color: "#C8A96E", textAlign: "right" }}>{c.percent_of_total.toFixed(1)}%</td>
                    <td style={{ padding: "10px 16px" }}>
                      <div style={{ background: "#0F1923", borderRadius: 2, height: 5, overflow: "hidden" }}>
                        <div style={{ width: `${Math.min(100, c.percent_of_total * 3)}%`, background: i < 3 ? "#C8A96E" : "#2A3D50", height: "100%", borderRadius: 2 }} />
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
      <div style={{ marginTop: 12, fontFamily: "monospace", fontSize: 11, color: "#1E2D3D" }}>Source: US Treasury TIC · Data as of {asOf}</div>
    </div>
  );
}

// ── Country Search Tab ────────────────────────────────────────────────────────

function USADashboard() {
  const [data, setData] = useState({});
  const [range, setRange] = useState(365 * 5);
  const [scenario, setScenario] = useState(null);
  const [customRate, setCustomRate] = useState(null);

  useEffect(() => {
    const end = new Date();
    const start = new Date();
    start.setDate(start.getDate() - range);
    const codes = "DGS10,DGS2,DGS5,FEDFUNDS,DFII10,DTWEXBGS,CPIAUCSL,M2SL";
    fetch(`${API}/timeseries?metric_codes=${codes}&start_date=${start.toISOString()}&end_date=${end.toISOString()}`)
      .then(r => r.json())
      .then(raw => {
        const byMetric = {};
        raw.forEach(({ date, value, metric_code }) => {
          if (!byMetric[metric_code]) byMetric[metric_code] = [];
          byMetric[metric_code].push({ date: date.split("T")[0], value: parseFloat(value) });
        });
        setData(byMetric);
      }).catch(() => {});
  }, [range]);

  const latest = (code) => {
    const s = data[code]; if (!s?.length) return null;
    return s[s.length - 1].value;
  };

  const yoy = (code) => {
    const s = data[code]; if (!s?.length) return null;
    const last = s[s.length - 1].value;
    const ago = s.find(d => { const diff = (new Date(s[s.length-1].date) - new Date(d.date))/(86400000); return diff>=340&&diff<=400; });
    if (!ago) return null;
    return ((last - ago.value) / Math.abs(ago.value)) * 100;
  };

  const dgs10 = latest("DGS10");
  const dgs2 = latest("DGS2");
  const fedfunds = latest("FEDFUNDS");
  const realYield = latest("DFII10");
  const spread = dgs10!=null&&dgs2!=null ? dgs10-dgs2 : null;
  const m2Yoy = yoy("M2SL");
  const m2Latest = latest("M2SL");
  const cpiYoy = yoy("CPIAUCSL");
  const dxyLatest = latest("DTWEXBGS");

  // ── Fiscal breaking point calculator ────────────────────────────────────────
  // Constants (FY2024 actuals / CBO estimates)
  const TOTAL_DEBT_T = 36.2;          // $T
  const ANNUAL_REVENUE_T = 4.9;       // $T federal revenue
  const ANNUAL_ROLLOVER_T = 6.0;      // $T debt rolling over annually (~avg 6Y maturity)
  const LOCKED_IN_INTEREST_T = 0.55;  // $T already locked in at existing rates
  const SPR_CURRENT_MB = 370;         // Million barrels current
  const SPR_CAPACITY_MB = 714;        // Million barrels capacity
  const US_GOLD_TONNES = 8133;        // Tonnes (unchanged since 1971)
  const US_GOLD_TROY_OZ = 261.5e6;    // Troy ounces
  const SPOT_GOLD = 4587;             // $/oz approximate

  const calcInterestCost = (yieldRate) => {
    // New debt issued this year at new yield, rest at existing average rate
    const newDebtCost = ANNUAL_ROLLOVER_T * (yieldRate / 100);
    return LOCKED_IN_INTEREST_T + newDebtCost;
  };

  const breakingPointRate = () => {
    // When does interest / revenue hit 25% (emerging market danger zone)?
    // LOCKED_IN + ROLLOVER * rate = 0.25 * REVENUE
    // rate = (0.25 * REVENUE - LOCKED_IN) / ROLLOVER
    return ((0.25 * ANNUAL_REVENUE_T - LOCKED_IN_INTEREST_T) / ANNUAL_ROLLOVER_T) * 100;
  };

  const crisisRate = () => {
    // When does interest hit 35% of revenue? (Japan-level crisis)
    return ((0.35 * ANNUAL_REVENUE_T - LOCKED_IN_INTEREST_T) / ANNUAL_ROLLOVER_T) * 100;
  };

  const BREAK = breakingPointRate(); // ~5.5%
  const CRISIS = crisisRate();       // ~8.5%

  const activeYield = customRate ?? dgs10 ?? 4.3;
  const activeInterest = calcInterestCost(activeYield);
  const activeInterestPct = (activeInterest / ANNUAL_REVENUE_T) * 100;

  const dangerColor = activeYield >= CRISIS ? "#FF4444" : activeYield >= BREAK ? "#E07B5A" : activeYield >= BREAK - 1 ? "#E8C547" : "#5DB87A";

  const SCENARIOS = [
    { label: "Hold (4%)", ff: 4.0, color: "#5A6878", desc: "Status quo. Yield curve flat. Deficit serviceable but growing. Foreign holders reducing slowly." },
    { label: "Cut to 2%", ff: 2.0, color: "#E8C547", desc: "Moderate easing. Long end likely rises 50-100bps — bear steepener. Dollar weakens. Foreign selling continues." },
    { label: "Cut to 1%", ff: 1.0, color: "#E07B5A", desc: "Aggressive signal. Long end rises 100-200bps. Dollar weakens sharply. Foreign holders accelerate selling. Deficit widens as long-term borrowing costs stay high." },
    { label: "Cut to 0% (ZIRP)", ff: 0.0, color: "#FF4444", desc: "2020-2022 playbook: M2 surged 27%, CPI hit 9%, 10Y rose from 0.5% to 3.5%. The bond market doesn't care what the Fed says." },
  ];

  // Build chart data
  const yieldData = (data["DGS10"]||[]).map((d,i) => ({
    date: d.date, "10Y": d.value,
    "2Y": data["DGS2"]?.[i]?.value,
    "Fed Funds": data["FEDFUNDS"]?.[i]?.value,
    "Real Yield": data["DFII10"]?.[i]?.value,
  }));
  const m2Data = (data["M2SL"]||[]).map(d => ({ date: d.date, value: d.value }));
  const m2YoyData = m2Data.map((d, i) => {
    if (i < 12) return { date: d.date, growth: null };
    const ago = m2Data[i-12];
    return { date: d.date, growth: ago ? ((d.value - ago.value)/ago.value*100) : null };
  }).filter(d => d.growth != null);

  // Interest cost table
  const RATE_TABLE = [3.5, 4.0, 4.5, 5.0, 5.5, 6.0, 7.0, 8.0].map(r => ({
    rate: r,
    cost: calcInterestCost(r),
    pct: (calcInterestCost(r) / ANNUAL_REVENUE_T * 100),
  }));

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
          US stress is not forced selling — it's the Fed's ability to manage <span style={{ color: "#C8A96E" }}>$36T in debt</span> as
          foreign demand weakens, the dollar debasement math, and whether the bond market will accept the terms the Fed is offering.
        </div>
      </div>

      {/* Range */}
      <div style={{ display: "flex", gap: 6, marginBottom: 20 }}>
        {[[365,"1Y"],[730,"2Y"],[1825,"5Y"],[3650,"10Y"]].map(([d,l]) => (
          <button key={l} onClick={() => setRange(d)} style={{ background: range===d?"#1A2530":"transparent", border:`1px solid ${range===d?"#5A6878":"#1E2D3D"}`, color:range===d?"#C8A96E":"#3A4D5C", borderRadius:2, padding:"4px 12px", cursor:"pointer", fontFamily:"monospace", fontSize:11 }}>{l}</button>
        ))}
      </div>

      {/* Key metrics row */}
      <div style={{ display: "flex", gap: 10, marginBottom: 20, flexWrap: "wrap" }}>
        {[
          { label: "10Y Yield", val: dgs10!=null?`${dgs10.toFixed(2)}%`:"—", color: "#C8A96E", sub: spread!=null?`Spread vs 2Y: ${spread>0?"+":""}${spread.toFixed(2)}pp`:"" },
          { label: "Fed Funds", val: fedfunds!=null?`${fedfunds.toFixed(2)}%`:"—", color: "#5DB87A", sub: "" },
          { label: "Real Yield", val: realYield!=null?`${realYield.toFixed(2)}%`:"—", color: realYield!=null&&realYield<0?"#E07B5A":"#7EB8C9", sub: realYield!=null&&realYield<0?"⚠ Financial repression":"Positive" },
          { label: "M2 Growth YoY", val: m2Yoy!=null?`${m2Yoy.toFixed(1)}%`:"—", color: m2Yoy!=null&&m2Yoy>10?"#E07B5A":m2Yoy!=null&&m2Yoy>5?"#E8C547":"#5DB87A", sub: m2Yoy!=null?`$${(m2Latest/1000).toFixed(1)}T total`:"" },
          { label: "CPI YoY", val: cpiYoy!=null?`${cpiYoy.toFixed(1)}%`:"—", color: cpiYoy!=null&&cpiYoy>4?"#E07B5A":cpiYoy!=null&&cpiYoy>2?"#E8C547":"#5DB87A", sub: cpiYoy!=null&&cpiYoy>2?"Above 2% target":"" },
          { label: "Dollar Index", val: dxyLatest!=null?dxyLatest.toFixed(1):"—", color: "#7EC4A0", sub: "" },
          { label: "US Gold", val: `${US_GOLD_TONNES.toLocaleString()}t`, color: "#C8A96E", sub: `$${((US_GOLD_TROY_OZ * SPOT_GOLD)/1e12).toFixed(2)}T at spot` },
          { label: "SPR Level", val: `${SPR_CURRENT_MB}M bbl`, color: SPR_CURRENT_MB < 400 ? "#E07B5A" : "#5DB87A", sub: `${((SPR_CURRENT_MB/SPR_CAPACITY_MB)*100).toFixed(0)}% of capacity (${SPR_CAPACITY_MB}M)` },
        ].map(s => (
          <div key={s.label} style={{ background:"#0F1923", border:"1px solid #1A2530", borderTop:`2px solid ${s.color}`, borderRadius:2, padding:"12px 16px", flex:"1 1 130px" }}>
            <div style={{ fontFamily:"monospace", fontSize:10, color:"#5A6878", textTransform:"uppercase", letterSpacing:"0.1em", marginBottom:4 }}>{s.label}</div>
            <div style={{ fontFamily:"monospace", fontSize:18, fontWeight:700, color:s.color }}>{s.val}</div>
            {s.sub && <div style={{ fontFamily:"monospace", fontSize:10, color:"#5A6878", marginTop:3 }}>{s.sub}</div>}
          </div>
        ))}
      </div>

      {/* ── BREAKING POINT CALCULATOR ── */}
      <div style={{ background:"#0A1520", border:`1px solid ${dangerColor}44`, borderLeft:`3px solid ${dangerColor}`, borderRadius:2, padding:"20px 24px", marginBottom:20 }}>
        <div style={{ display:"flex", alignItems:"center", justifyContent:"space-between", marginBottom:16, flexWrap:"wrap", gap:12 }}>
          <div>
            <div style={{ fontFamily:"monospace", fontSize:12, color:"#8A9BAC", letterSpacing:"0.1em", marginBottom:4 }}>FISCAL BREAKING POINT CALCULATOR</div>
            <div style={{ fontFamily:"monospace", fontSize:11, color:"#5A6878" }}>
              At $36.2T debt · $6T rolling over annually · $4.9T revenue · Every 100bps = <span style={{ color:"#C8A96E" }}>+$60B/yr in new interest</span>
            </div>
          </div>
          <div style={{ display:"flex", alignItems:"center", gap:12 }}>
            <span style={{ fontFamily:"monospace", fontSize:11, color:"#5A6878" }}>Model 10Y at:</span>
            <input type="range" min="1" max="12" step="0.25" value={customRate ?? activeYield}
              onChange={e => setCustomRate(parseFloat(e.target.value))}
              style={{ width:140, accentColor:"#C8A96E" }} />
            <span style={{ fontFamily:"monospace", fontSize:14, color:"#C8A96E", minWidth:40 }}>{(customRate??activeYield).toFixed(2)}%</span>
            {customRate && <button onClick={() => setCustomRate(null)} style={{ background:"transparent", border:"1px solid #1E2D3D", color:"#3A4D5C", borderRadius:2, padding:"3px 8px", cursor:"pointer", fontFamily:"monospace", fontSize:10 }}>reset</button>}
          </div>
        </div>

        {/* Live readout */}
        <div style={{ display:"flex", gap:16, marginBottom:20, flexWrap:"wrap" }}>
          {[
            { label:"Annual Interest Cost", val:`$${activeInterest.toFixed(2)}T`, color:dangerColor },
            { label:"% of Federal Revenue", val:`${activeInterestPct.toFixed(1)}%`, color:dangerColor },
            { label:"Warning zone (25%)", val:`${BREAK.toFixed(1)}% yield`, color:"#E07B5A" },
            { label:"Crisis zone (35%)", val:`${CRISIS.toFixed(1)}% yield`, color:"#FF4444" },
            { label:"Distance to warning", val: dgs10!=null?(BREAK-(customRate??dgs10)>0?`+${(BREAK-(customRate??dgs10)).toFixed(2)}pp headroom`:`${(BREAK-(customRate??dgs10)).toFixed(2)}pp BREACHED`):"—", color: dgs10!=null&&(customRate??dgs10)>=BREAK?"#FF4444":"#5DB87A" },
          ].map(s => (
            <div key={s.label} style={{ background:"#0F1923", borderRadius:2, padding:"10px 16px", flex:"1 1 140px" }}>
              <div style={{ fontFamily:"monospace", fontSize:10, color:"#5A6878", marginBottom:4 }}>{s.label}</div>
              <div style={{ fontFamily:"monospace", fontSize:16, fontWeight:700, color:s.color }}>{s.val}</div>
            </div>
          ))}
        </div>

        {/* Rate table */}
        <table style={{ width:"100%", borderCollapse:"collapse", marginBottom:12 }}>
          <thead>
            <tr>{["10Y Yield","Annual Interest","% of Revenue","Status"].map(h=>(
              <th key={h} style={{ fontFamily:"monospace", fontSize:10, color:"#3A4D5C", textTransform:"uppercase", padding:"6px 12px", textAlign:"right", borderBottom:"1px solid #1A2530" }}>{h}</th>
            ))}</tr>
          </thead>
          <tbody>
            {RATE_TABLE.map(row => {
              const isCurrent = Math.abs(row.rate - (customRate??dgs10??4.3)) < 0.3;
              const isBreak = row.rate >= BREAK && row.rate < BREAK + 0.6;
              const isCrisis = row.rate >= CRISIS && row.rate < CRISIS + 0.6;
              const statusColor = row.pct >= 35 ? "#FF4444" : row.pct >= 25 ? "#E07B5A" : row.pct >= 20 ? "#E8C547" : "#5DB87A";
              const status = row.pct >= 35 ? "⚡ CRISIS" : row.pct >= 25 ? "⚠ DANGER" : row.pct >= 20 ? "WATCH" : "OK";
              return (
                <tr key={row.rate} style={{ background: isCurrent ? "#C8A96E0D" : "transparent", borderBottom:"1px solid #0F1923" }}>
                  <td style={{ padding:"7px 12px", fontFamily:"monospace", fontSize:12, color:isCurrent?"#C8A96E":"#E8E0D0", textAlign:"right", fontWeight:isCurrent?700:400 }}>
                    {row.rate.toFixed(1)}% {isCurrent?"← current":""} {isBreak?"← warning threshold":""} {isCrisis?"← crisis threshold":""}
                  </td>
                  <td style={{ padding:"7px 12px", fontFamily:"monospace", fontSize:12, color:"#8A9BAC", textAlign:"right" }}>${row.cost.toFixed(2)}T/yr</td>
                  <td style={{ padding:"7px 12px", fontFamily:"monospace", fontSize:12, color:statusColor, textAlign:"right" }}>{row.pct.toFixed(1)}%</td>
                  <td style={{ padding:"7px 12px", textAlign:"right" }}>
                    <span style={{ fontFamily:"monospace", fontSize:10, color:statusColor, background:`${statusColor}18`, border:`1px solid ${statusColor}44`, borderRadius:2, padding:"1px 6px" }}>{status}</span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        <div style={{ fontFamily:"monospace", fontSize:10, color:"#2A3540" }}>
          Assumptions: $36.2T total debt · $6T annual rollover · $4.9T revenue · $0.55T existing locked-in interest · Danger = 25% interest/revenue (EM threshold) · Crisis = 35% (Japan-level)
        </div>
      </div>

      {/* Yield curve chart */}
      {yieldData.length > 0 && (
        <div style={{ background:"#0A1520", border:"1px solid #1A2530", borderRadius:2, padding:"20px 24px", marginBottom:20 }}>
          <div style={{ fontFamily:"monospace", fontSize:10, color:"#3A4D5C", letterSpacing:"0.1em", marginBottom:16 }}>YIELD CURVE & RATE STRUCTURE</div>
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={yieldData} margin={{ top:4, right:8, bottom:4, left:8 }}>
              <CartesianGrid strokeDasharray="2 6" stroke="#0F1923" vertical={false} />
              <XAxis dataKey="date" tickFormatter={formatDate} tick={{ fill:"#3A4D5C", fontFamily:"monospace", fontSize:10 }} axisLine={false} tickLine={false} minTickGap={60} />
              <YAxis tick={{ fill:"#3A4D5C", fontFamily:"monospace", fontSize:10 }} axisLine={false} tickLine={false} width={40} tickFormatter={v=>`${v}%`} />
              <ReferenceLine y={BREAK} stroke="#E07B5A" strokeDasharray="4 4" strokeOpacity={0.5} label={{ value:`${BREAK.toFixed(1)}% warning`, fill:"#E07B5A66", fontFamily:"monospace", fontSize:9, position:"right" }} />
              <ReferenceLine y={0} stroke="#2A3540" strokeDasharray="3 3" />
              <Tooltip contentStyle={{ background:"#0A1520", border:"1px solid #1E2D3D", borderRadius:2, fontFamily:"monospace", fontSize:11 }} labelStyle={{ color:"#5A6878" }} labelFormatter={formatDate} formatter={(v,n)=>[`${v?.toFixed(2)}%`,n]} />
              <Legend wrapperStyle={{ fontFamily:"monospace", fontSize:10, color:"#5A6878", paddingTop:12 }} />
              <Line type="monotone" dataKey="10Y" stroke="#C8A96E" strokeWidth={1.5} dot={false} connectNulls />
              <Line type="monotone" dataKey="2Y" stroke="#9B8EC4" strokeWidth={1.5} dot={false} connectNulls />
              <Line type="monotone" dataKey="Fed Funds" stroke="#5DB87A" strokeWidth={1.5} dot={false} connectNulls />
              <Line type="monotone" dataKey="Real Yield" stroke="#E8C547" strokeWidth={1} dot={false} connectNulls strokeDasharray="3 3" />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* M2 Growth chart */}
      {m2YoyData.length > 0 && (
        <div style={{ background:"#0A1520", border:"1px solid #1A2530", borderRadius:2, padding:"20px 24px", marginBottom:20 }}>
          <div style={{ display:"flex", alignItems:"center", gap:12, marginBottom:16 }}>
            <div style={{ fontFamily:"monospace", fontSize:10, color:"#3A4D5C", letterSpacing:"0.1em" }}>US M2 BROAD MONEY GROWTH (YoY %)</div>
            {m2Yoy!=null && <span style={{ fontFamily:"monospace", fontSize:10, color: m2Yoy>10?"#E07B5A":m2Yoy>5?"#E8C547":"#5DB87A", background:`${m2Yoy>10?"#E07B5A":m2Yoy>5?"#E8C547":"#5DB87A"}18`, border:`1px solid ${m2Yoy>10?"#E07B5A":m2Yoy>5?"#E8C547":"#5DB87A"}44`, borderRadius:2, padding:"1px 6px" }}>{m2Yoy.toFixed(1)}% current</span>}
          </div>
          <ResponsiveContainer width="100%" height={160}>
            <LineChart data={m2YoyData} margin={{ top:4, right:8, bottom:4, left:8 }}>
              <CartesianGrid strokeDasharray="2 6" stroke="#0F1923" vertical={false} />
              <XAxis dataKey="date" tickFormatter={formatDate} tick={{ fill:"#3A4D5C", fontFamily:"monospace", fontSize:10 }} axisLine={false} tickLine={false} minTickGap={60} />
              <YAxis tick={{ fill:"#3A4D5C", fontFamily:"monospace", fontSize:10 }} axisLine={false} tickLine={false} width={44} tickFormatter={v=>`${v.toFixed(0)}%`} />
              <ReferenceLine y={10} stroke="#E07B5A" strokeDasharray="4 4" strokeOpacity={0.5} label={{ value:"10%", fill:"#E07B5A66", fontFamily:"monospace", fontSize:9, position:"right" }} />
              <ReferenceLine y={0} stroke="#2A3540" strokeDasharray="3 3" />
              <Tooltip formatter={(v)=>[`${v?.toFixed(1)}%`,"M2 YoY"]} contentStyle={{ background:"#0A1520", border:"1px solid #1E2D3D", borderRadius:2, fontFamily:"monospace", fontSize:11 }} labelStyle={{ color:"#5A6878" }} labelFormatter={formatDate} />
              <Line type="monotone" dataKey="growth" stroke="#6A8FC4" strokeWidth={1.5} dot={false} connectNulls />
            </LineChart>
          </ResponsiveContainer>
          <div style={{ fontFamily:"monospace", fontSize:10, color:"#2A3540", marginTop:6 }}>The 2020-2022 surge (peak +27%) drove CPI to 9.1%. Current trajectory matters for foreign holders deciding whether dollar reserves are worth holding.</div>
        </div>
      )}

      {/* Rate scenario modeler */}
      <div style={{ background:"#0A1520", border:"1px solid #1A2530", borderRadius:2, padding:"20px 24px", marginBottom:20 }}>
        <div style={{ fontFamily:"monospace", fontSize:10, color:"#3A4D5C", letterSpacing:"0.1em", marginBottom:4 }}>RATE CUT SCENARIO ANALYSIS</div>
        <div style={{ fontFamily:"monospace", fontSize:11, color:"#5A6878", marginBottom:16 }}>The Fed controls the short end. The bond market controls the long end. These are not the same thing.</div>
        <div style={{ display:"flex", gap:8, marginBottom:16, flexWrap:"wrap" }}>
          {SCENARIOS.map(s => (
            <button key={s.label} onClick={() => setScenario(scenario?.label===s.label?null:s)}
              style={{ background:scenario?.label===s.label?`${s.color}18`:"transparent", border:`1px solid ${scenario?.label===s.label?s.color:"#1E2D3D"}`, color:scenario?.label===s.label?s.color:"#5A6878", borderRadius:2, padding:"6px 14px", cursor:"pointer", fontFamily:"monospace", fontSize:11 }}>
              {s.label}
            </button>
          ))}
        </div>
        {scenario ? (
          <div style={{ background:`${scenario.color}0D`, border:`1px solid ${scenario.color}33`, borderLeft:`3px solid ${scenario.color}`, borderRadius:2, padding:"16px 20px" }}>
            <div style={{ fontFamily:"monospace", fontSize:12, color:scenario.color, fontWeight:700, marginBottom:8 }}>{scenario.label}</div>
            <div style={{ fontFamily:"monospace", fontSize:12, color:"#8A9BAC", lineHeight:1.8, marginBottom:12 }}>{scenario.desc}</div>
            <div style={{ display:"flex", gap:20, flexWrap:"wrap" }}>
              {[
                { label:"Fed Funds Target", val:`${scenario.ff.toFixed(1)}%`, color:"#5DB87A" },
                { label:"Likely 10Y Response", val:scenario.ff<=0?"Rises 150-250bps":scenario.ff<=1?"Rises 100-200bps":scenario.ff<=2?"Rises 50-100bps":"Holds ±25bps", color:scenario.ff<=1?"#E07B5A":"#E8C547" },
                { label:"Yield Curve Shape", val:scenario.ff<=1?"Bear Steepener ⚠":scenario.ff<=2?"Steepens":"Flat", color:scenario.ff<=1?"#E07B5A":"#E8C547" },
                { label:"Dollar Effect", val:scenario.ff<=1?"Weakens sharply":scenario.ff<=2?"Weakens":"Stable", color:scenario.ff<=1?"#E07B5A":"#E8C547" },
                { label:"Foreign Selling", val:scenario.ff<=1?"Accelerates":"Continues", color:scenario.ff<=1?"#E07B5A":"#E8C547" },
                { label:"Breaking Point Risk", val:scenario.ff<=0?"CRISIS":scenario.ff<=1?"HIGH":"MODERATE", color:scenario.ff<=0?"#FF4444":scenario.ff<=1?"#E07B5A":"#E8C547" },
              ].map(s => (
                <div key={s.label}>
                  <div style={{ fontFamily:"monospace", fontSize:10, color:"#3A4D5C", marginBottom:2 }}>{s.label}</div>
                  <div style={{ fontFamily:"monospace", fontSize:12, color:s.color, fontWeight:600 }}>{s.val}</div>
                </div>
              ))}
            </div>
          </div>
        ) : (
          <div style={{ fontFamily:"monospace", fontSize:11, color:"#2A3540", padding:"8px 0" }}>Select a scenario to see bond market implications.</div>
        )}
      </div>

      {/* Doom loop */}
      <div style={{ background:"#0A1520", border:"1px solid #1A2530", borderRadius:2, padding:"20px 24px" }}>
        <div style={{ fontFamily:"monospace", fontSize:10, color:"#3A4D5C", letterSpacing:"0.1em", marginBottom:12 }}>THE FEEDBACK LOOP — HOW FOREIGN STRESS REACHES THE US</div>
        <div style={{ display:"flex", gap:6, flexWrap:"wrap", alignItems:"center", marginBottom:12 }}>
          {[
            { n:"1", t:"Foreign stress builds", d:"Countries need USD liquidity — sell Treasuries" },
            "→",
            { n:"2", t:"Treasury prices fall", d:"Yields rise as supply exceeds demand" },
            "→",
            { n:"3", t:"US borrowing costs rise", d:"$36T debt × higher yield = ballooning deficit" },
            "→",
            { n:"4", t:"More Treasuries issued", d:"To fund the expanding deficit" },
            "→",
            { n:"5", t:"Feedback tightens", d:"More supply → more yield pressure → back to step 2" },
          ].map((item, i) =>
            item === "→"
              ? <div key={i} style={{ fontFamily:"monospace", fontSize:16, color:"#1E2D3D" }}>→</div>
              : <div key={i} style={{ background:"#0F1923", border:"1px solid #1A2530", borderRadius:2, padding:"10px 12px", flex:"1 1 120px", marginBottom:6 }}>
                  <div style={{ fontFamily:"monospace", fontSize:10, color:"#C8A96E", marginBottom:3 }}>STEP {item.n}</div>
                  <div style={{ fontFamily:"monospace", fontSize:11, color:"#E8E0D0", fontWeight:600, marginBottom:2 }}>{item.t}</div>
                  <div style={{ fontFamily:"monospace", fontSize:10, color:"#5A6878" }}>{item.d}</div>
                </div>
          )}
        </div>
        <div style={{ fontFamily:"monospace", fontSize:11, color:"#3A4D5C", borderTop:"1px solid #1A2530", paddingTop:12 }}>
          Sentinel's stress signals across 34 countries are <span style={{ color:"#C8A96E" }}>Step 1</span> early indicators.
          The MARKETS tab yield data is <span style={{ color:"#C8A96E" }}>Step 2</span>.
          The breaking point calculator above shows where <span style={{ color:"#C8A96E" }}>Step 3</span> becomes irreversible.
          At {BREAK.toFixed(1)}% on the 10Y, the US crosses the emerging market danger threshold. At {CRISIS.toFixed(1)}%, it's Japan 2024.
        </div>
      </div>
    </div>
  );
}


function CountryTab({ initialIso, onIsoChange, latestAll = {} }) {
  const [countries, setCountries] = useState([]);
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState(initialIso || null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`${API}/countries`)
      .then(r => r.json())
      .then(d => { setCountries(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  const filtered = countries.filter(c =>
    c.name.toLowerCase().includes(search.toLowerCase()) ||
    c.iso_code.toLowerCase().includes(search.toLowerCase())
  );

  const byRegion = filtered.reduce((acc, c) => {
    const r = c.region || "Other";
    if (!acc[r]) acc[r] = [];
    acc[r].push(c);
    return acc;
  }, {});

  if (selected === "USA") {
    return (
      <div>
        <button onClick={() => { setSelected(null); if (onIsoChange) onIsoChange(null); }}
          style={{ background: "transparent", border: "1px solid #1E2D3D", color: "#5A6878", borderRadius: 2, padding: "6px 14px", cursor: "pointer", fontFamily: "monospace", fontSize: 12, marginBottom: 20 }}>
          ← all countries
        </button>
        <USADashboard />
      </div>
    );
  }

  if (selected) {
    return (
      <div>
        <button onClick={() => { setSelected(null); if (onIsoChange) onIsoChange(null); }}
          style={{ background: "transparent", border: "1px solid #1E2D3D", color: "#5A6878", borderRadius: 2, padding: "6px 14px", cursor: "pointer", fontFamily: "monospace", fontSize: 12, marginBottom: 20 }}>
          ← all countries
        </button>
        <CountryDetail iso={selected} onClose={() => setSelected(null)} standalone latestAll={latestAll} />
      </div>
    );
  }

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <input
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="Search country name or ISO code (e.g. Turkey, TUR, India, IND, USA)..."
          style={{ width: "100%", boxSizing: "border-box", background: "#0A1520", border: "1px solid #1A2530", borderRadius: 2, padding: "12px 16px", fontFamily: "monospace", fontSize: 13, color: "#E8E0D0", outline: "none" }}
          onFocus={e => e.target.style.borderColor = "#C8A96E"}
          onBlur={e => e.target.style.borderColor = "#1A2530"}
        />
        {search && <div style={{ fontFamily: "monospace", fontSize: 11, color: "#3A4D5C", marginTop: 6 }}>{filtered.length} countries found</div>}
      </div>

      {/* USA special card — always visible or when matching search */}
      {(!search || "united states usa america".includes(search.toLowerCase())) && (
        <div style={{ marginBottom: 28 }}>
          <div style={{ fontFamily: "monospace", fontSize: 10, color: "#3A4D5C", letterSpacing: "0.15em", textTransform: "uppercase", marginBottom: 10, borderBottom: "1px solid #1A2530", paddingBottom: 6 }}>
            United States <span style={{ color: "#C8A96E" }}>— Issuer Dashboard</span>
          </div>
          <button onClick={() => setSelected("USA")}
            style={{ background: "#0A1520", border: "1px solid #C8A96E44", borderRadius: 2, padding: "12px 20px", cursor: "pointer", fontFamily: "monospace", color: "#C8A96E", textAlign: "left", transition: "all 0.15s" }}
            onMouseEnter={e => { e.currentTarget.style.borderColor = "#C8A96E"; e.currentTarget.style.background = "#C8A96E0A"; }}
            onMouseLeave={e => { e.currentTarget.style.borderColor = "#C8A96E44"; e.currentTarget.style.background = "#0A1520"; }}>
            <span style={{ fontSize: 10, color: "#5A6878", display: "block", marginBottom: 2 }}>USA</span>
            <span style={{ fontSize: 13 }}>United States of America</span>
            <span style={{ marginLeft: 12, fontSize: 10, color: "#5A6878" }}>M2 · Real Yield · Dollar · CPI · Yield Curve · Rate Scenario Modeler</span>
          </button>
        </div>
      )}

      {loading ? (
        <div style={{ fontFamily: "monospace", color: "#3A4D5C" }}>loading countries...</div>
      ) : (
        <div>
          {Object.entries(byRegion).sort().map(([region, regionCountries]) => (
            <div key={region} style={{ marginBottom: 28 }}>
              <div style={{ fontFamily: "monospace", fontSize: 10, color: "#3A4D5C", letterSpacing: "0.15em", textTransform: "uppercase", marginBottom: 10, borderBottom: "1px solid #1A2530", paddingBottom: 6 }}>
                {region} <span style={{ color: "#1E2D3D" }}>({regionCountries.length})</span>
              </div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                {regionCountries.map(c => (
                  <button key={c.iso_code} onClick={() => setSelected(c.iso_code)}
                    style={{ background: "#0A1520", border: "1px solid #1A2530", borderRadius: 2, padding: "8px 14px", cursor: "pointer", fontFamily: "monospace", fontSize: 12, color: "#8A9BAC", textAlign: "left", transition: "all 0.15s" }}
                    onMouseEnter={e => { e.currentTarget.style.borderColor = "#C8A96E"; e.currentTarget.style.color = "#E8E0D0"; }}
                    onMouseLeave={e => { e.currentTarget.style.borderColor = "#1A2530"; e.currentTarget.style.color = "#8A9BAC"; }}>
                    <span style={{ color: "#5A6878", fontSize: 10, display: "block", marginBottom: 2 }}>{c.iso_code}</span>
                    {c.name}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}


// ── Cross-Asset Tab ───────────────────────────────────────────────────────────

function CrossAssetTab() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [view, setView] = useState("all");

  useEffect(() => {
    fetch(`${API}/holdings/cross-asset-stress`)
      .then(r => r.json())
      .then(d => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  if (loading) return <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: 300, fontFamily: "monospace", fontSize: 13, color: "#3A4D5C" }}>loading cross-asset signals...</div>;
  if (!data || data.detail) return <div style={{ fontFamily: "monospace", color: "#E07B5A", padding: 24 }}>No cross-asset data. Ensure TIC and gold reserves are loaded.</div>;

  const { summary } = data;
  const allStressed = [...(data.cross_asset_stress || []), ...(data.treasury_only_stress || []), ...(data.gold_only_stress || [])].sort((a, b) => b.stress_score - a.stress_score);
  const displayData = view === "cross" ? data.cross_asset_stress
    : view === "exited" ? data.gold_only_stress
    : view === "treasury" ? data.treasury_only_stress
    : allStressed;

  const spotRising = data.spot_gold_rising;
  const spotPrice = data.spot_gold_price;
  const spot3m = data.spot_gold_3m_pct;

  return (
    <div>
      {!spotPrice && (
        <div style={{ background: "#1A2530", border: "1px solid #2A3D50", borderLeft: "3px solid #3A4D5C", borderRadius: 2, padding: "10px 16px", marginBottom: 16, fontFamily: "monospace", fontSize: 12, color: "#5A6878" }}>
          ℹ Spot gold price not loaded — divergence multiplier inactive. Load gold price data to enable 2× signal.
        </div>
      )}
      {spotRising === true && summary?.cross_asset_stressed > 0 && (
        <AlertBanner message={`⚡ DIVERGENCE ACTIVE — ${summary.cross_asset_stressed} countr${summary.cross_asset_stressed === 1 ? "y" : "ies"} selling gold INTO rising spot price. Maximum distress.`} color="#FF4444" />
      )}
      {spotRising === true && summary?.cross_asset_stressed === 0 && (
        <AlertBanner message="Spot gold rising — 2× divergence multiplier activates if any country begins selling reserves." color="#C8A96E" />
      )}

      <div style={{ display: "flex", gap: 12, marginBottom: 20, flexWrap: "wrap" }}>
        {[
          { label: "Exited Position", val: (data.cross_asset_stress||[]).filter(c=>c.no_tic_holdings).length + (data.treasury_only_stress||[]).filter(c=>c.no_tic_holdings).length, alert: true, color: "#FF8C00" },
          { label: "Cross-Asset Stress", val: summary?.cross_asset_stressed ?? 0, alert: (summary?.cross_asset_stressed ?? 0) > 0, color: "#E07B5A" },
          { label: "Treasury-Only Stress", val: summary?.treasury_only ?? 0, alert: (summary?.treasury_only ?? 0) > 5, color: "#E8C547" },
          { label: "Gold-Only Stress", val: summary?.gold_only ?? 0, color: "#C8A96E" },
          { label: "Spot Gold 3M", val: spot3m != null ? `${spot3m > 0 ? "+" : ""}${spot3m}%` : "—", alert: spotRising, color: spotRising ? "#5DB87A" : "#E07B5A" },
          { label: "Gold Price", val: spotPrice != null ? `$${spotPrice.toLocaleString()}` : "—", color: "#C8A96E" },
        ].map(s => (
          <div key={s.label} style={{ background: "#0F1923", border: `1px solid ${s.alert ? `${s.color}33` : "#1A2530"}`, borderTop: `2px solid ${s.alert ? s.color : "#1A2530"}`, borderRadius: 2, padding: "14px 20px", flex: "1 1 140px" }}>
            <div style={{ fontFamily: "monospace", fontSize: 10, color: "#5A6878", textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 6 }}>{s.label}</div>
            <div style={{ fontFamily: "monospace", fontSize: 20, fontWeight: 700, color: s.alert ? s.color : "#E8E0D0" }}>{s.val}</div>
          </div>
        ))}
      </div>

      <div style={{ background: "#0A1520", border: "1px solid #1A2530", borderRadius: 2, padding: "16px 20px", marginBottom: 20, display: "flex", gap: 32, flexWrap: "wrap" }}>
        {[
          { label: "⚡ Divergence", desc: "Selling gold INTO rising spot. 2× score.", color: "#FF4444" },
          { label: "⚠ Cross-Asset", desc: "Selling both treasuries AND gold. 1.5×.", color: "#E07B5A" },
          { label: "🚨 Exited", desc: "Zero US Treasuries held + significant gold. Completed liquidation.", color: "#FF8C00" },
          { label: "T-Bills Only", desc: "Reducing treasury holdings. 1×.", color: "#E8C547" },
          { label: "Au Only", desc: "Reducing gold reserves only. 1×.", color: "#C8A96E" },
        ].map(s => (
          <div key={s.label} style={{ display: "flex", alignItems: "flex-start", gap: 10 }}>
            <span style={{ fontFamily: "monospace", fontSize: 10, color: s.color, background: `${s.color}18`, border: `1px solid ${s.color}44`, borderRadius: 2, padding: "2px 6px", whiteSpace: "nowrap", marginTop: 2 }}>{s.label}</span>
            <span style={{ fontFamily: "monospace", fontSize: 11, color: "#5A6878" }}>{s.desc}</span>
          </div>
        ))}
      </div>

      <div style={{ background: "#0A1520", border: "1px solid #1A2530", borderRadius: 2, padding: "20px 0" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "0 20px 16px" }}>
          <div style={{ fontFamily: "monospace", fontSize: 12, color: "#8A9BAC", letterSpacing: "0.1em" }}>CROSS-ASSET STRESS LEADERBOARD</div>
          <div style={{ display: "flex", gap: 6 }}>
            {[["all","ALL"],["exited","🚨 EXITED"],["cross","CROSS-ASSET"],["treasury","T-ONLY"]].map(([v,l]) => (
              <button key={v} onClick={() => setView(v)} style={{ background: view===v?"#1A2530":"transparent", border:`1px solid ${view===v?"#5A6878":"#1E2D3D"}`, color:view===v?"#C8A96E":"#3A4D5C", borderRadius:2, padding:"4px 10px", cursor:"pointer", fontFamily:"monospace", fontSize:11 }}>{l}</button>
            ))}
          </div>
        </div>
        {displayData.length === 0
          ? <div style={{ padding:"40px 20px", fontFamily:"monospace", fontSize:13, color:"#3A4D5C", textAlign:"center" }}>no countries in this view</div>
          : (
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr>
                    {["Country","Signal","T-Bills MoM","Consec ↓","Gold t","Gold MoM","Score"].map(h => (
                      <th key={h} style={{ fontFamily:"monospace", fontSize:10, color:"#3A4D5C", textTransform:"uppercase", padding:"8px 12px", textAlign:h==="Country"||h==="Signal"?"left":"right", borderBottom:"1px solid #1A2530", whiteSpace:"nowrap" }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {displayData.map(c => {
                    const tier = c.signal_tier || (c.divergence_signal ? "DIVERGENCE" : c.cross_asset_stress ? "CROSS_ASSET" : c.no_tic_holdings ? "EXITED" : c.selling_treasuries ? "TREASURY_ONLY" : "GOLD_ONLY");
                    const tc = tier==="DIVERGENCE"?"#FF4444":tier==="CROSS_ASSET"?"#E07B5A":tier==="EXITED"||tier==="EXITED+GOLD_SELL"?"#FF8C00":tier==="TREASURY_ONLY"?"#E8C547":"#C8A96E";
                    const tierLabel = tier==="DIVERGENCE"?"⚡ DIVERGENCE":tier==="CROSS_ASSET"?"⚠ CROSS-ASSET":tier==="EXITED"?"🚨 EXITED":tier==="EXITED+GOLD_SELL"?"🚨 EXITED+Au↓":tier==="TREASURY_ONLY"?"T-ONLY":"Au ONLY";
                    return (
                      <tr key={c.country_iso} style={{ borderBottom:"1px solid #0F1923" }}
                        onMouseEnter={e => e.currentTarget.style.background="#0D1820"}
                        onMouseLeave={e => e.currentTarget.style.background="transparent"}>
                        <td style={{ padding:"10px 12px", fontFamily:"monospace", fontSize:13, color:"#E8E0D0" }}>
                          {c.country_name}<span style={{ marginLeft:6, fontSize:10, color:"#3A4D5C" }}>{c.country_iso}</span>
                        </td>
                        <td style={{ padding:"10px 12px" }}>
                          <span style={{ fontFamily:"monospace", fontSize:10, color:tc, background:`${tc}18`, border:`1px solid ${tc}44`, borderRadius:2, padding:"2px 6px", whiteSpace:"nowrap" }}>{tierLabel}</span>
                        </td>
                        <td style={{ padding:"10px 12px", fontFamily:"monospace", fontSize:12, textAlign:"right", color:(c.tic_mom_pct??0)<0?"#E07B5A":"#5DB87A" }}>
                          {c.no_tic_holdings
                            ? <span style={{ color:"#FF8C00", fontSize:10 }}>EXITED ⚠</span>
                            : c.tic_mom_pct!=null?`${c.tic_mom_pct>0?"+":""}${c.tic_mom_pct.toFixed(2)}%`:"—"}
                        </td>
                        <td style={{ padding:"10px 12px", fontFamily:"monospace", fontSize:12, textAlign:"right", color:(c.tic_consecutive_months??0)>=3?"#E07B5A":"#8A9BAC" }}>{(c.tic_consecutive_months??0)>0?`${c.tic_consecutive_months}mo`:"—"}</td>
                        <td style={{ padding:"10px 12px", fontFamily:"monospace", fontSize:12, textAlign:"right", color:"#8A9BAC" }}>{c.gold_tonnes!=null?`${c.gold_tonnes.toLocaleString()}t`:"—"}</td>
                        <td style={{ padding:"10px 12px", fontFamily:"monospace", fontSize:12, textAlign:"right", color:c.gold_mom_pct==null?"#3A4D5C":c.gold_mom_pct<0?"#E07B5A":"#5DB87A" }}>
                          {c.gold_mom_pct!=null?`${c.gold_mom_pct>0?"+":""}${c.gold_mom_pct.toFixed(2)}%`:"—"}
                        </td>
                        <td style={{ padding:"10px 12px", minWidth:140 }}><StressBar score={c.stress_score??0} max={150} /></td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )
        }
      </div>
      <div style={{ marginTop:12, fontFamily:"monospace", fontSize:11, color:"#1E2D3D" }}>Sources: US Treasury TIC · World Gold Council · Data as of {data.as_of ?? "—"}</div>
    </div>
  );
}


// ── Composite Tab ─────────────────────────────────────────────────────────────

function CompositeTab({ onCountrySelect }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [view, setView] = useState("all");

  useEffect(() => {
    fetch(`${API}/stress/composite`)
      .then(r => r.json())
      .then(d => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  if (loading) return <div style={{ display:"flex", alignItems:"center", justifyContent:"center", height:300, fontFamily:"monospace", fontSize:13, color:"#3A4D5C" }}>computing composite stress...</div>;
  if (!data || data.error) return <div style={{ fontFamily:"monospace", color:"#E07B5A", padding:24 }}>Failed to load composite stress data. {data?.error ?? ""}</div>;

  const { summary } = data;
  const allResults = [...(data.crisis||[]), ...(data.stressed||[]), ...(data.elevated||[]), ...(data.watch||[])];
  const displayData = view==="crisis" ? data.crisis
    : view==="stressed" ? [...(data.crisis||[]),...(data.stressed||[])]
    : view==="elevated" ? [...(data.crisis||[]),...(data.stressed||[]),...(data.elevated||[])]
    : allResults;

  const TIER_COLORS = { CRISIS:"#FF4444", STRESSED:"#E07B5A", ELEVATED:"#E8C547", WATCH:"#5A6878" };

  return (
    <div>
      {summary?.crisis === 0 && summary?.stressed === 0 && (
        <div style={{ background:"#5DB87A15", border:"1px solid #5DB87A44", borderLeft:"3px solid #5DB87A", borderRadius:2, padding:"10px 16px", marginBottom:20, fontFamily:"monospace", fontSize:12, color:"#5DB87A" }}>
          ✓ No CRISIS or STRESSED signals active as of {data.as_of} — system monitoring {allResults.length} countries.
        </div>
      )}
      {(summary?.crisis??0) > 0 && (
        <AlertBanner message={`⚡ ${summary.crisis} CRISIS-tier countr${summary.crisis===1?"y":"ies"} — all stress dimensions firing.`} color="#FF4444" />
      )}

      {/* Score methodology */}
      <div style={{ background:"#0A1520", border:"1px solid #1A2530", borderRadius:2, padding:"14px 20px", marginBottom:20, display:"flex", gap:28, flexWrap:"wrap" }}>
        <div style={{ fontFamily:"monospace", fontSize:10, color:"#3A4D5C", letterSpacing:"0.1em", alignSelf:"center" }}>SCORE =</div>
        {[
          { label:"Treasury", desc:"MoM decline + consecutive months", max:"0–50 pts", color:"#C8A96E" },
          { label:"Gold Reserves", desc:"QoQ decline + consecutive quarters", max:"0–40 pts", color:"#E8C547" },
          { label:"Sovereign Spread", desc:">50bps vs US 10Y + widening", max:"0–20 pts", color:"#7EB8C9" },
          { label:"Petrodollar", desc:"Oil price drop for oil-dependent nations", max:"0–20 pts", color:"#E07B5A" },
        ].map(s => (
          <div key={s.label} style={{ display:"flex", alignItems:"center", gap:8 }}>
            <div style={{ width:8, height:8, borderRadius:"50%", background:s.color, flexShrink:0 }} />
            <div>
              <div style={{ fontFamily:"monospace", fontSize:11, color:"#E8E0D0" }}>{s.label} <span style={{ color:"#3A4D5C" }}>{s.max}</span></div>
              <div style={{ fontFamily:"monospace", fontSize:10, color:"#5A6878" }}>{s.desc}</div>
            </div>
          </div>
        ))}
        <div style={{ display:"flex", alignItems:"center", gap:8, borderLeft:"1px solid #1A2530", paddingLeft:20 }}>
          <div>
            <div style={{ fontFamily:"monospace", fontSize:11, color:"#E07B5A" }}>× 1.5 cross-asset (T + gold selling)</div>
            <div style={{ fontFamily:"monospace", fontSize:11, color:"#FF4444" }}>× 2.0 divergence (gold sold into rising price)</div>
          </div>
        </div>
      </div>

      {/* Summary cards */}
      <div style={{ display:"flex", gap:12, marginBottom:20, flexWrap:"wrap" }}>
        {[
          { label:"CRISIS", val:summary?.crisis??0, color:"#FF4444", desc:"All signals + multiplier" },
          { label:"STRESSED", val:summary?.stressed??0, color:"#E07B5A", desc:"Score 50–75" },
          { label:"ELEVATED", val:summary?.elevated??0, color:"#E8C547", desc:"Score 25–50" },
          { label:"WATCH", val:summary?.watch??0, color:"#5A6878", desc:"Score < 25" },
          { label:"Top Risk", val:summary?.highest_risk?.country_name??"—", color:"#C8A96E", desc:`Score: ${summary?.highest_risk?.composite_score?.toFixed(0)??"—"}` },
        ].map(s => (
          <div key={s.label} style={{ background:"#0F1923", border:`1px solid ${(s.val>0&&s.label!=="Top Risk")?`${s.color}33`:"#1A2530"}`, borderTop:`2px solid ${(s.val>0||s.label==="Top Risk")?s.color:"#1A2530"}`, borderRadius:2, padding:"14px 20px", flex:"1 1 140px" }}>
            <div style={{ fontFamily:"monospace", fontSize:10, color:"#5A6878", textTransform:"uppercase", letterSpacing:"0.1em", marginBottom:4 }}>{s.label}</div>
            <div style={{ fontFamily:"monospace", fontSize:20, fontWeight:700, color:(s.val>0||s.label==="Top Risk")?s.color:"#3A4D5C" }}>{s.val}</div>
            <div style={{ fontFamily:"monospace", fontSize:10, color:"#3A4D5C", marginTop:3 }}>{s.desc}</div>
          </div>
        ))}
      </div>

      {/* Leaderboard */}
      <div style={{ background:"#0A1520", border:"1px solid #1A2530", borderRadius:2, padding:"20px 0" }}>
        <div style={{ display:"flex", alignItems:"center", justifyContent:"space-between", padding:"0 20px 16px" }}>
          <div style={{ fontFamily:"monospace", fontSize:12, color:"#8A9BAC", letterSpacing:"0.1em" }}>
            COMPOSITE SOVEREIGN STRESS LEADERBOARD
            <span style={{ marginLeft:10, fontSize:10, color:"#3A4D5C" }}>click country to open full detail view</span>
          </div>
          <div style={{ display:"flex", gap:6 }}>
            {[["all","ALL"],["elevated","ELEVATED+"],["stressed","STRESSED+"],["crisis","CRISIS"]].map(([v,l]) => (
              <button key={v} onClick={() => setView(v)} style={{ background:view===v?"#1A2530":"transparent", border:`1px solid ${view===v?"#5A6878":"#1E2D3D"}`, color:view===v?"#C8A96E":"#3A4D5C", borderRadius:2, padding:"4px 10px", cursor:"pointer", fontFamily:"monospace", fontSize:11 }}>{l}</button>
            ))}
          </div>
        </div>
        {displayData.length === 0
          ? <div style={{ padding:"40px 20px", fontFamily:"monospace", fontSize:13, color:"#3A4D5C", textAlign:"center" }}>no countries in this tier</div>
          : (
            <div style={{ overflowX:"auto" }}>
              <table style={{ width:"100%", borderCollapse:"collapse" }}>
                <thead>
                  <tr>
                    {["Country","Tier","T-Bill MoM","Consec","Gold t","T","G","Spread","P","Mult","Score","Active Signals"].map(h => (
                      <th key={h} style={{ fontFamily:"monospace", fontSize:10, color:"#3A4D5C", textTransform:"uppercase", padding:"6px 8px", textAlign:h==="Country"||h==="Active Signals"||h==="Tier"?"left":"right", borderBottom:"1px solid #1A2530", whiteSpace:"nowrap" }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {displayData.map(c => {
                    const tc = TIER_COLORS[c.tier] || "#5A6878";
                    return (
                      <tr key={c.country_iso}
                        onClick={() => onCountrySelect(c.country_iso)}
                        style={{ borderBottom:"1px solid #0F1923", cursor:"pointer" }}
                        onMouseEnter={e => e.currentTarget.style.background="#0D1820"}
                        onMouseLeave={e => e.currentTarget.style.background="transparent"}>
                        <td style={{ padding:"7px 8px", fontFamily:"monospace", fontSize:12, color:"#E8E0D0", whiteSpace:"nowrap" }}>
                          {c.country_name}<span style={{ marginLeft:5, fontSize:10, color:"#3A4D5C" }}>{c.country_iso}</span>
                        </td>
                        <td style={{ padding:"7px 8px" }}>
                          <span style={{ fontFamily:"monospace", fontSize:10, color:tc, background:`${tc}18`, border:`1px solid ${tc}44`, borderRadius:2, padding:"1px 5px" }}>{c.tier}</span>
                        </td>
                        <td style={{ padding:"7px 8px", fontFamily:"monospace", fontSize:11, textAlign:"right", color:(c.tic_mom_pct??0)<0?"#E07B5A":"#5DB87A" }}>
                          {c.no_tic_holdings
                            ? <span style={{ color:"#FF4444", fontSize:10 }}>ZERO ⚠</span>
                            : c.tic_mom_pct!=null?`${c.tic_mom_pct>0?"+":""}${c.tic_mom_pct.toFixed(1)}%`:"—"}
                        </td>
                        <td style={{ padding:"7px 8px", fontFamily:"monospace", fontSize:11, textAlign:"right", color:(c.tic_consecutive_months??0)>=3?"#E07B5A":"#8A9BAC" }}>
                          {(c.tic_consecutive_months??0)>0?`${c.tic_consecutive_months}mo`:"—"}
                        </td>
                        <td style={{ padding:"7px 8px", fontFamily:"monospace", fontSize:11, textAlign:"right", color:c.selling_gold?"#E07B5A":"#5A6878" }}>
                          {c.gold_tonnes!=null?`${c.gold_tonnes.toLocaleString()}`:"—"}
                        </td>
                        <td style={{ padding:"7px 8px", fontFamily:"monospace", fontSize:11, textAlign:"right", color:"#C8A96E" }}>{c.tic_score?.toFixed(0)??0}</td>
                        <td style={{ padding:"7px 8px", fontFamily:"monospace", fontSize:11, textAlign:"right", color:"#E8C547" }}>{c.gold_score?.toFixed(0)??0}</td>
                        <td style={{ padding:"7px 8px", fontFamily:"monospace", fontSize:11, textAlign:"right", color:(c.spread_bps??0)>50?"#7EB8C9":"#3A4D5C" }}>
                          {c.spread_bps!=null?`${c.spread_bps>0?"+":""}${c.spread_bps.toFixed(0)}`:"—"}
                        </td>
                        <td style={{ padding:"7px 8px", fontFamily:"monospace", fontSize:11, textAlign:"right", color:(c.petro_score??0)>0?"#E07B5A":"#3A4D5C" }}>
                          {c.oil_dependent?(c.petro_score>0?c.petro_score:"🛢"):"—"}
                        </td>
                        <td style={{ padding:"7px 8px", fontFamily:"monospace", fontSize:11, textAlign:"right", color:(c.multiplier??1)>1?"#FF4444":"#3A4D5C" }}>
                          {(c.multiplier??1)>1?`${c.multiplier}×`:"—"}
                        </td>
                        <td style={{ padding:"7px 8px", minWidth:120 }}>
                          <div style={{ display:"flex", alignItems:"center", gap:6 }}>
                            <div style={{ flex:1, background:"#0F1923", borderRadius:2, height:5, overflow:"hidden" }}>
                              <div style={{ width:`${Math.min(100,c.composite_score)}%`, background:tc, height:"100%", borderRadius:2 }} />
                            </div>
                            <span style={{ fontFamily:"monospace", fontSize:11, color:tc, minWidth:28, textAlign:"right", fontWeight:700 }}>{c.composite_score?.toFixed(0)??0}</span>
                          </div>
                        </td>
                        <td style={{ padding:"7px 8px", fontFamily:"monospace", fontSize:11, color:"#5A6878", maxWidth:240 }}>
                          {(c.active_signals||[]).join(" · ") || "—"}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )
        }
      </div>
      <div style={{ marginTop:12, fontFamily:"monospace", fontSize:11, color:"#1E2D3D" }}>
        Data as of {data.as_of} · Sources: US Treasury TIC · World Gold Council · FRED
      </div>
    </div>
  );
}


// ── Gold Reserves Tab ────────────────────────────────────────────────────────

function GoldReservesTab({ onCountrySelect }) {
  const [reserves, setReserves] = useState(null);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState(null);

  useEffect(() => {
    fetch(`${API}/gold-reserves`)
      .then(r => r.json())
      .then(d => { setReserves(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  if (loading) return <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: 300, fontFamily: "monospace", fontSize: 13, color: "#3A4D5C" }}>loading gold reserves...</div>;
  if (!reserves) return <div style={{ fontFamily: "monospace", color: "#E07B5A", padding: 24 }}>No gold reserves data. Run POST /api/fetch/gold-reserves</div>;

  const rows = reserves.reserves || [];
  const total = reserves.total_metric_tonnes;

  return (
    <div>
      {/* Summary */}
      <div style={{ display: "flex", gap: 12, marginBottom: 20, flexWrap: "wrap" }}>
        {[
          { label: "Total CB Gold", val: `${total?.toLocaleString(undefined, { maximumFractionDigits: 0 })}t` },
          { label: "Countries Reporting", val: reserves.country_count },
          { label: "Top Holder", val: rows[0]?.country_code ?? "—" },
          { label: "US Share", val: rows.find(r => r.country_code === "USA") ? `${rows.find(r => r.country_code === "USA").percent_of_total.toFixed(1)}%` : "—" },
          { label: "Data", val: "Per-country latest" },
        ].map(s => (
          <div key={s.label} style={{ background: "#0F1923", border: "1px solid #1A2530", borderTop: "2px solid #C8A96E", borderRadius: 2, padding: "14px 20px", flex: "1 1 140px" }}>
            <div style={{ fontFamily: "monospace", fontSize: 10, color: "#5A6878", textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 6 }}>{s.label}</div>
            <div style={{ fontFamily: "monospace", fontSize: 20, fontWeight: 700, color: "#E8E0D0" }}>{s.val}</div>
          </div>
        ))}
      </div>

      {/* Top 8 quick cards */}
      <div style={{ display: "flex", gap: 8, marginBottom: 20, flexWrap: "wrap" }}>
        {rows.slice(0, 8).map(c => (
          <div key={c.country_code}
            onClick={() => onCountrySelect(c.country_code)}
            style={{ background: "#0A1520", border: "1px solid #1A2530", borderRadius: 2, padding: "8px 14px", cursor: "pointer", flex: "1 1 110px", maxWidth: 160 }}>
            <div style={{ fontFamily: "monospace", fontSize: 10, color: "#5A6878" }}>{c.country_code}</div>
            <div style={{ fontFamily: "monospace", fontSize: 13, color: "#E8E0D0", marginTop: 2 }}>{c.metric_tonnes.toFixed(0)}t</div>
            <div style={{ fontFamily: "monospace", fontSize: 11, color: "#C8A96E", marginTop: 2 }}>{c.percent_of_total.toFixed(1)}%</div>
          </div>
        ))}
      </div>

      {/* Inline country detail */}
      {selected && (
        <CountryDetail iso={selected.country_code} onClose={() => setSelected(null)} latestAll={{}} />
      )}

      {/* Bar chart top 20 */}
      <div style={{ background: "#0A1520", border: "1px solid #1A2530", borderRadius: 2, padding: "20px 24px", marginBottom: 16 }}>
        <div style={{ fontFamily: "monospace", fontSize: 11, color: "#5A6878", marginBottom: 16, letterSpacing: "0.1em" }}>CENTRAL BANK GOLD HOLDINGS — TOP 20 (metric tonnes)</div>
        <ResponsiveContainer width="100%" height={240}>
          <BarChart data={rows.slice(0, 20)} margin={{ top: 4, right: 8, bottom: 40, left: 8 }}>
            <CartesianGrid strokeDasharray="2 6" stroke="#0F1923" vertical={false} />
            <XAxis dataKey="country_code" tick={{ fill: "#5A6878", fontFamily: "monospace", fontSize: 10 }} axisLine={false} tickLine={false} angle={-45} textAnchor="end" />
            <YAxis tick={{ fill: "#3A4D5C", fontFamily: "monospace", fontSize: 10 }} axisLine={false} tickLine={false} width={52} tickFormatter={v => `${v.toLocaleString()}t`} />
            <Tooltip formatter={v => [`${v.toLocaleString()}t`, "Gold"]} contentStyle={{ background: "#0A1520", border: "1px solid #1E2D3D", borderRadius: 2, fontFamily: "monospace", fontSize: 11 }} labelStyle={{ color: "#5A6878" }} />
            <Bar dataKey="metric_tonnes" radius={[2, 2, 0, 0]} fill="#C8A96E" fillOpacity={0.8} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Full table */}
      <div style={{ background: "#0A1520", border: "1px solid #1A2530", borderRadius: 2, padding: "20px 0" }}>
        <div style={{ padding: "0 20px 16px", fontFamily: "monospace", fontSize: 12, color: "#8A9BAC", letterSpacing: "0.1em" }}>
          COMPLETE HOLDINGS TABLE
          <span style={{ marginLeft: 10, fontSize: 10, color: "#3A4D5C" }}>click row for country history</span>
        </div>
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr>
                {["#", "Country", "As Of", "Tonnes", "% of Total", "Share"].map(h => (
                  <th key={h} style={{ fontFamily: "monospace", fontSize: 10, color: "#3A4D5C", textTransform: "uppercase", padding: "8px 16px", textAlign: h === "Country" ? "left" : "right", borderBottom: "1px solid #1A2530", whiteSpace: "nowrap" }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((c, i) => {
                const isSelected = selected?.country_code === c.country_code;
                return (
                  <tr key={c.country_code}
                    onClick={() => setSelected(isSelected ? null : c)}
                    style={{ cursor: "pointer", background: isSelected ? "#0F1923" : "transparent", borderBottom: "1px solid #0F1923" }}
                    onMouseEnter={e => e.currentTarget.style.background = "#0D1820"}
                    onMouseLeave={e => e.currentTarget.style.background = isSelected ? "#0F1923" : "transparent"}>
                    <td style={{ padding: "8px 16px", fontFamily: "monospace", fontSize: 11, color: "#3A4D5C", textAlign: "right" }}>{i + 1}</td>
                    <td style={{ padding: "8px 16px", fontFamily: "monospace", fontSize: 13, color: "#E8E0D0" }}>
                      {c.country_name}
                      <span style={{ marginLeft: 8, fontSize: 10, color: "#3A4D5C" }}>{c.country_code}</span>
                    </td>
                    <td style={{ padding: "8px 16px", fontFamily: "monospace", fontSize: 11, color: "#3A4D5C", textAlign: "right" }}>{c.as_of_date ?? "—"}</td>
                    <td style={{ padding: "8px 16px", fontFamily: "monospace", fontSize: 13, color: "#C8A96E", textAlign: "right" }}>{c.metric_tonnes.toLocaleString(undefined, { maximumFractionDigits: 1 })}</td>
                    <td style={{ padding: "8px 16px", fontFamily: "monospace", fontSize: 12, color: "#8A9BAC", textAlign: "right" }}>{c.percent_of_total.toFixed(1)}%</td>
                    <td style={{ padding: "8px 16px" }}>
                      <div style={{ background: "#0F1923", borderRadius: 2, height: 5, overflow: "hidden" }}>
                        <div style={{ width: `${Math.min(100, c.percent_of_total * 4)}%`, background: i < 3 ? "#C8A96E" : i < 10 ? "#E8C547" : "#2A3D50", height: "100%", borderRadius: 2 }} />
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
      <div style={{ marginTop: 12, fontFamily: "monospace", fontSize: 11, color: "#1E2D3D" }}>Source: World Gold Council (IMF IFS) · Quarterly data · Reporting lag ~2 months</div>
    </div>
  );
}

// ── Main App ──────────────────────────────────────────────────────────────────

export default function App() {
  const [tab, setTab] = useState("MARKETS");
  const [countryIso, setCountryIso] = useState(null); // for cross-tab navigation
  const [activeMetrics, setActiveMetrics] = useState(["DGS10", "DGS2", "FEDFUNDS", "DCOILWTICO"]);
  const [range, setRange] = useState(RANGES[1]);
  const [chartData, setChartData] = useState([]);
  const [latestAll, setLatestAll] = useState({});
  const [stats, setStats] = useState(null);
  const [health, setHealth] = useState(null);
  const [loading, setLoading] = useState(false);
  const [normalized, setNormalized] = useState(false);

  // Navigate to country tab with a specific country
  const handleCountrySelect = (iso) => {
    setCountryIso(iso);
    setTab("COUNTRY");
  };

  useEffect(() => {
    const allCodes = [...METRICS.map(m => m.code),"IRLTLT01JPM156N","IRLTLT01DEM156N","IRLTLT01ITM156N","IRLTLT01FRM156N","IRLTLT01ESM156N","IRLTLT01GBM156N","IRLTLT01AUM156N","IRLTLT01CAM156N","IRLTLT01NLM156N","IRLTLT01NOM156N","IRLTLT01SEM156N","IRLTLT01CHM156N","IRLTLT01BEM156N","IRLTLT01KRM156N"].join(",");
    const end = new Date();
    const start = new Date();
    start.setDate(start.getDate() - 120);
    fetch(`${API}/timeseries?metric_codes=${allCodes}&start_date=${start.toISOString()}&end_date=${end.toISOString()}`)
      .then(r => r.json())
      .then(raw => {
        const byDate = {};
        raw.forEach(({ date, value, metric_code }) => {
          const d = date.split("T")[0];
          if (!byDate[d]) byDate[d] = { date: d };
          byDate[d][metric_code] = value;
        });
const rows = Object.values(byDate).sort((a, b) => a.date.localeCompare(b.date));
const latest = {}, month30 = {};
const allTrackedCodes = [...METRICS.map(m => m.code),
  "IRLTLT01JPM156N","IRLTLT01DEM156N","IRLTLT01ITM156N","IRLTLT01FRM156N",
  "IRLTLT01ESM156N","IRLTLT01GBM156N","IRLTLT01AUM156N","IRLTLT01CAM156N",
  "IRLTLT01NLM156N","IRLTLT01NOM156N","IRLTLT01SEM156N","IRLTLT01CHM156N",
  "IRLTLT01BEM156N","IRLTLT01KRM156N"
];
allTrackedCodes.forEach((code) => {
  const withVal = rows.filter(r => r[code] != null);
  if (withVal.length) latest[code] = withVal[withVal.length - 1][code];
  if (withVal.length > 1) month30[code] = withVal[Math.max(0, withVal.length - 2)][code];
});
setLatestAll({ latest, month30 });
      }).catch(() => {});
  }, []);

  const fetchChartData = useCallback(async () => {
    if (!activeMetrics.length) return;
    setLoading(true);
    try {
      const end = new Date();
      const start = new Date();
      start.setDate(start.getDate() - range.days);
      const res = await fetch(`${API}/timeseries?metric_codes=${activeMetrics.join(",")}&start_date=${start.toISOString()}&end_date=${end.toISOString()}`);
      const raw = await res.json();
      const byDate = {};
      raw.forEach(({ date, value, metric_code }) => {
        const d = date.split("T")[0];
        if (!byDate[d]) byDate[d] = { date: d };
        byDate[d][metric_code] = value;
      });
      let rows = Object.values(byDate).sort((a, b) => a.date.localeCompare(b.date));
      if (normalized && rows.length > 0) {
        const base = {};
        activeMetrics.forEach(m => { base[m] = rows.find(r => r[m] != null)?.[m]; });
        rows = rows.map(r => {
          const nr = { date: r.date };
          activeMetrics.forEach(m => { if (r[m] != null && base[m]) nr[m] = ((r[m] - base[m]) / base[m]) * 100; });
          return nr;
        });
      }
      setChartData(rows);
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  }, [activeMetrics, range, normalized]);

  useEffect(() => { fetchChartData(); }, [fetchChartData]);
  useEffect(() => {
    fetch(`${API}/stats`).then(r => r.json()).then(setStats).catch(() => {});
    fetch(`${API}/health`).then(r => r.json()).then(setHealth).catch(() => {});
  }, []);

  const { latest = {}, month30 } = latestAll;
  const getChange = (code, unit) => {
    if (!month30 || latest[code] == null || month30[code] == null) return null;
    if (unit === "%" || unit === "") return latest[code] - month30[code];
    return ((latest[code] - month30[code]) / month30[code]) * 100;
  };
  const tickerData = METRICS.map(m => ({ ...m, latest: latest[m.code] })).filter(m => m.latest != null);

  return (
    <div style={{ minHeight: "100vh", background: "#060D14", color: "#E8E0D0", fontFamily: "'Inter', system-ui, sans-serif" }}>
      {/* Header */}
      <div style={{ borderBottom: "1px solid #1A2530", padding: "0 32px", display: "flex", alignItems: "center", justifyContent: "space-between", height: 52 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <div style={{ width: 8, height: 8, borderRadius: "50%", background: "#C8A96E", boxShadow: "0 0 8px #C8A96E" }} />
          <span style={{ fontFamily: "monospace", fontSize: 13, letterSpacing: "0.15em", color: "#8A9BAC", textTransform: "uppercase" }}>Project Sentinel</span>
          <span style={{ color: "#1E2D3D", margin: "0 4px" }}>|</span>
          <span style={{ fontFamily: "monospace", fontSize: 11, color: "#3A4D5C", letterSpacing: "0.1em" }}>TREASURY MONITOR</span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          {health && <span style={{ fontFamily: "monospace", fontSize: 11, color: health.status === "healthy" ? "#5DB87A" : "#E07B5A" }}>● {health.status}</span>}
          {stats && <span style={{ fontFamily: "monospace", fontSize: 11, color: "#3A4D5C" }}>{stats.timeseries_records?.toLocaleString()} records</span>}
        </div>
      </div>

      <Ticker data={tickerData} />

      {/* Tabs */}
      <div style={{ borderBottom: "1px solid #1A2530", padding: "0 32px", display: "flex", gap: 0 }}>
        {TABS.map(t => (
          <button key={t} onClick={() => { setTab(t); if (t !== "COUNTRY") setCountryIso(null); }} style={{
            background: "transparent", border: "none",
            borderBottom: `2px solid ${tab === t ? "#C8A96E" : "transparent"}`,
            color: tab === t ? "#C8A96E" : "#3A4D5C",
            padding: "12px 20px", cursor: "pointer",
            fontFamily: "monospace", fontSize: 12, letterSpacing: "0.1em", marginBottom: -1,
          }}>{t}</button>
        ))}
      </div>

      <div style={{ padding: "28px 32px", maxWidth: 1400, margin: "0 auto" }}>

        {tab === "MARKETS" && (
          <>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 12, marginBottom: 28 }}>
              {METRICS.map(m => <StatCard key={m.code} label={m.label} value={latest[m.code]} unit={m.unit} change={getChange(m.code, m.unit)} color={m.color} />)}
            </div>
            <div style={{ background: "#0A1520", border: "1px solid #1A2530", borderRadius: 2, padding: "24px 28px" }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 24, flexWrap: "wrap", gap: 12 }}>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  {METRICS.map(m => {
                    const on = activeMetrics.includes(m.code);
                    return <button key={m.code} onClick={() => setActiveMetrics(prev => prev.includes(m.code) ? prev.filter(c => c !== m.code) : [...prev, m.code])} style={{ background: on ? `${m.color}18` : "transparent", border: `1px solid ${on ? m.color : "#1E2D3D"}`, color: on ? m.color : "#3A4D5C", borderRadius: 2, padding: "5px 12px", cursor: "pointer", fontFamily: "monospace", fontSize: 12, transition: "all 0.15s" }}>{m.label}</button>;
                  })}
                </div>
                <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                  <button onClick={() => setNormalized(p => !p)} style={{ background: normalized ? "#1A2530" : "transparent", border: `1px solid ${normalized ? "#5A6878" : "#1E2D3D"}`, color: normalized ? "#8A9BAC" : "#3A4D5C", borderRadius: 2, padding: "5px 12px", cursor: "pointer", fontFamily: "monospace", fontSize: 11 }}>% CHANGE</button>
                  <div style={{ display: "flex", border: "1px solid #1E2D3D", borderRadius: 2, overflow: "hidden" }}>
                    {RANGES.map(r => <button key={r.label} onClick={() => setRange(r)} style={{ background: range.label === r.label ? "#1A2530" : "transparent", border: "none", borderLeft: "1px solid #1E2D3D", color: range.label === r.label ? "#C8A96E" : "#3A4D5C", padding: "5px 12px", cursor: "pointer", fontFamily: "monospace", fontSize: 12 }}>{r.label}</button>)}
                  </div>
                </div>
              </div>
              {loading ? (
                <div style={{ height: 380, display: "flex", alignItems: "center", justifyContent: "center", color: "#2A3540", fontFamily: "monospace", fontSize: 13 }}>fetching data...</div>
              ) : (
                <ResponsiveContainer width="100%" height={380}>
                  <LineChart data={chartData} margin={{ top: 4, right: 8, bottom: 4, left: 8 }}>
                    <CartesianGrid strokeDasharray="2 6" stroke="#0F1923" vertical={false} />
                    <XAxis dataKey="date" tickFormatter={formatDate} tick={{ fill: "#3A4D5C", fontFamily: "monospace", fontSize: 11 }} axisLine={{ stroke: "#1A2530" }} tickLine={false} minTickGap={60} />
                    <YAxis tick={{ fill: "#3A4D5C", fontFamily: "monospace", fontSize: 11 }} axisLine={false} tickLine={false} tickFormatter={v => normalized ? `${v.toFixed(1)}%` : v.toFixed(2)} width={52} />
                    {normalized && <ReferenceLine y={0} stroke="#2A3540" strokeDasharray="4 4" />}
                    <Tooltip content={<CustomTooltip />} />
                    <Legend wrapperStyle={{ fontFamily: "monospace", fontSize: 11, color: "#5A6878", paddingTop: 16 }} formatter={(value) => METRICS.find(m => m.code === value)?.label || value} />
                    {activeMetrics.map(code => {
                      const m = METRICS.find(x => x.code === code);
                      return <Line key={code} type="monotone" dataKey={code} name={code} stroke={m?.color} strokeWidth={1.5} dot={false} activeDot={{ r: 3, strokeWidth: 0 }} connectNulls />;
                    })}
                  </LineChart>
                </ResponsiveContainer>
              )}
            </div>
            {!normalized && latest["DGS10"] != null && latest["DGS2"] != null && (
              <div style={{ marginTop: 12, background: "#0A1520", border: "1px solid #1A2530", borderRadius: 2, padding: "14px 28px", display: "flex", gap: 32, alignItems: "center", flexWrap: "wrap" }}>
                <span style={{ fontFamily: "monospace", fontSize: 11, color: "#3A4D5C", letterSpacing: "0.1em" }}>SPREAD</span>
                {[
                  { label: "10Y–2Y", val: latest["DGS10"] - latest["DGS2"] },
                  { label: "10Y–5Y", val: latest["DGS5"] != null ? latest["DGS10"] - latest["DGS5"] : null },
                  { label: "5Y–2Y", val: latest["DGS5"] != null ? latest["DGS5"] - latest["DGS2"] : null },
                  { label: "10Y–FF", val: latest["FEDFUNDS"] != null ? latest["DGS10"] - latest["FEDFUNDS"] : null },
                ].filter(s => s.val != null).map(s => (
                  <div key={s.label} style={{ fontFamily: "monospace" }}>
                    <span style={{ fontSize: 11, color: "#3A4D5C", marginRight: 8 }}>{s.label}</span>
                    <span style={{ fontSize: 15, color: s.val < 0 ? "#E07B5A" : "#5DB87A", fontWeight: 600 }}>{s.val > 0 ? "+" : ""}{s.val.toFixed(2)}pp</span>
                    {s.label === "10Y–2Y" && s.val < 0 && <span style={{ marginLeft: 8, fontSize: 10, color: "#E07B5A88" }}>INVERTED</span>}
                  </div>
                ))}
              </div>
            )}
            <div style={{ marginTop: 24, display: "flex", justifyContent: "space-between" }}>
              <span style={{ fontFamily: "monospace", fontSize: 11, color: "#1E2D3D" }}>Source: FRED / Federal Reserve Bank of St. Louis</span>
              {stats?.data_latest && <span style={{ fontFamily: "monospace", fontSize: 11, color: "#1E2D3D" }}>Last data point: {formatDate(stats.data_latest)}</span>}
            </div>
          </>
        )}

        {tab === "HOLDINGS" && <HoldingsTab onCountrySelect={handleCountrySelect} latestAll={latestAll} />}
        {tab === "CROSS-ASSET" && <CrossAssetTab />}
        {tab === "GOLD" && <GoldReservesTab onCountrySelect={handleCountrySelect} />}
        {tab === "COMPOSITE" && <CompositeTab onCountrySelect={handleCountrySelect} />}
        {tab === "STRESS" && <StressScoreTab />}
        {tab === "COUNTRY" && (
          <CountryTab
            initialIso={countryIso}
            onIsoChange={setCountryIso}
            latestAll={latest}
          />
        )}
        {tab === "ADMIN" && <AdminTab />}
        {tab === "ABOUT" && <AboutTab />}

      </div>
    </div>
  );
}

function StressScoreTab() {
  const [score, setScore] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`${API}/stress-score`)
      .then(r => r.json())
      .then(d => { setScore(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  if (loading) return <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: 300, fontFamily: "monospace", fontSize: 13, color: "#3A4D5C" }}>computing stress score...</div>;
  if (!score) return <div style={{ fontFamily: "monospace", color: "#E07B5A", padding: 24 }}>Failed to load stress score.</div>;

  const overall = score.overall_score;
  const scoreColor = overall >= 75 ? "#FF4444" : overall >= 50 ? "#E07B5A" : overall >= 25 ? "#E8C547" : "#5DB87A";
  const comps = score.components || {};
  const weights = score.weights || {};

  const FACTORS = [
    { key: "yield_curve", label: "Yield Curve", desc: "DGS10 - DGS2 spread", note: "Inverted curve = stress", color: "#7EB8C9", unit: "pp" },
    { key: "concentration", label: "Holdings Concentration", desc: "Top country % of total", note: "High concentration = stress", color: "#C8A96E", unit: "%" },
    { key: "commodity_volatility", label: "Commodity Volatility", desc: "30-day WTI std dev", note: "High volatility = stress", color: "#E07B5A", unit: "%" },
    { key: "gold_accumulation", label: "Gold Accumulation", desc: "CB gold YoY change", note: "Rapid buying = de-dollarization signal", color: "#E8C547", unit: "% YoY" },
  ];

  return (
    <div>
      {/* Overall score */}
      <div style={{ background: "#0A1520", border: `1px solid ${scoreColor}44`, borderLeft: `4px solid ${scoreColor}`, borderRadius: 2, padding: "28px 32px", marginBottom: 24 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 32, flexWrap: "wrap" }}>
          <div>
            <div style={{ fontFamily: "monospace", fontSize: 11, color: "#5A6878", letterSpacing: "0.15em", marginBottom: 8 }}>MACRO STRESS INDEX</div>
            <div style={{ display: "flex", alignItems: "baseline", gap: 12 }}>
              <span style={{ fontFamily: "monospace", fontSize: 56, fontWeight: 700, color: scoreColor, lineHeight: 1 }}>{overall.toFixed(1)}</span>
              <span style={{ fontFamily: "monospace", fontSize: 16, color: "#3A4D5C" }}>/ 100</span>
            </div>
            <div style={{ fontFamily: "monospace", fontSize: 13, color: scoreColor, marginTop: 8 }}>{score.interpretation}</div>
            <div style={{ fontFamily: "monospace", fontSize: 10, color: "#3A4D5C", marginTop: 4 }}>as of {new Date(score.timestamp).toLocaleString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}</div>
          </div>
          <div style={{ flex: 1, minWidth: 200 }}>
            <div style={{ background: "#080E14", borderRadius: 4, height: 12, overflow: "hidden", marginBottom: 8 }}>
              <div style={{ width: `${Math.min(100, overall)}%`, background: scoreColor, height: "100%", borderRadius: 4, transition: "width 0.5s" }} />
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", fontFamily: "monospace", fontSize: 10, color: "#3A4D5C" }}>
              <span>LOW</span><span>MODERATE</span><span>ELEVATED</span><span>SEVERE</span>
            </div>
          </div>
        </div>
      </div>

      {/* Component breakdown */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 16, marginBottom: 24 }}>
        {FACTORS.map(f => {
          const comp = comps[f.key] || {};
          const w = weights[f.key] ?? 0;
          const active = w > 0;
          return (
            <div key={f.key} style={{ background: "#0A1520", border: `1px solid ${active ? f.color + "33" : "#1A2530"}`, borderTop: `2px solid ${active ? f.color : "#1A2530"}`, borderRadius: 2, padding: "18px 20px", opacity: active ? 1 : 0.5 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 12 }}>
                <div>
                  <div style={{ fontFamily: "monospace", fontSize: 12, color: "#E8E0D0", fontWeight: 600 }}>{f.label}</div>
                  <div style={{ fontFamily: "monospace", fontSize: 10, color: "#5A6878", marginTop: 2 }}>{f.desc}</div>
                </div>
                <span style={{ fontFamily: "monospace", fontSize: 10, color: f.color, background: `${f.color}18`, border: `1px solid ${f.color}44`, borderRadius: 2, padding: "2px 7px", whiteSpace: "nowrap" }}>
                  {Math.round(w * 100)}% weight
                </span>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 10 }}>
                <div style={{ fontFamily: "monospace", fontSize: 28, fontWeight: 700, color: f.color }}>{(comp.score ?? 0).toFixed(0)}</div>
                <div>
                  <div style={{ fontFamily: "monospace", fontSize: 18, color: "#E8E0D0" }}>
                    {comp.value != null ? `${comp.value > 0 && f.unit !== "pp" ? "+" : ""}${comp.value.toFixed(2)}${f.unit}` : "—"}
                  </div>
                  <div style={{ fontFamily: "monospace", fontSize: 10, color: "#3A4D5C" }}>{f.note}</div>
                </div>
              </div>
              <div style={{ background: "#080E14", borderRadius: 2, height: 5, overflow: "hidden" }}>
                <div style={{ width: `${Math.min(100, comp.score ?? 0)}%`, background: f.color, height: "100%", borderRadius: 2 }} />
              </div>
            </div>
          );
        })}
      </div>

      {/* Methodology */}
      <div style={{ background: "#0A1520", border: "1px solid #1A2530", borderRadius: 2, padding: "20px 24px" }}>
        <div style={{ fontFamily: "monospace", fontSize: 10, color: "#3A4D5C", letterSpacing: "0.15em", textTransform: "uppercase", marginBottom: 16, borderBottom: "1px solid #1A2530", paddingBottom: 8 }}>MODEL METHODOLOGY</div>
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {[
            { factor: "Yield Curve (35%)", detail: "DGS10 - DGS2 spread. Maps -1% (fully inverted = 100 stress) to +1% (normal = 0 stress). At 0% = 50 stress.", color: "#7EB8C9" },
            { factor: "Concentration (30%)", detail: "Top country as % of total TIC holdings. Maps 30% = 100 stress to <10% = 0 stress. Tracks de-dollarization risk.", color: "#C8A96E" },
            { factor: "Commodity Volatility (20%)", detail: "30-day WTI crude oil price std dev. Maps 5%+ = 100 stress to <1% = 0 stress. Proxy for macro shock.", color: "#E07B5A" },
            { factor: "Gold Accumulation (15%)", detail: "YoY % change in total CB gold (common-country basis). Maps >3% = 100 stress to <0% = 0 stress. De-dollarization signal.", color: "#E8C547" },
          ].map(m => (
            <div key={m.factor} style={{ display: "flex", gap: 12, alignItems: "flex-start" }}>
              <div style={{ width: 8, height: 8, borderRadius: "50%", background: m.color, flexShrink: 0, marginTop: 4 }} />
              <div>
                <div style={{ fontFamily: "monospace", fontSize: 12, color: "#E8E0D0", fontWeight: 600 }}>{m.factor}</div>
                <div style={{ fontFamily: "monospace", fontSize: 11, color: "#5A6878", lineHeight: 1.6, marginTop: 2 }}>{m.detail}</div>
              </div>
            </div>
          ))}
        </div>
        <div style={{ fontFamily: "monospace", fontSize: 10, color: "#1E2D3D", marginTop: 16, borderTop: "1px solid #1A2530", paddingTop: 10 }}>
          Composite = weighted average of all active factors · Recalculated daily at 04:30 UTC · Data: FRED, US Treasury TIC, World Gold Council
        </div>
      </div>
    </div>
  );
}

function AdminTab() {
  const [logs, setLogs] = useState([]);
  const [running, setRunning] = useState({});
  const [results, setResults] = useState({});
  const [stats, setStats] = useState(null);

  const loadLogs = () => {
    fetch(`${API}/pipeline-logs?limit=20`)
      .then(r => r.json())
      .then(setLogs)
      .catch(() => {});
    fetch(`${API}/stats`).then(r => r.json()).then(setStats).catch(() => {});
  };

  useEffect(() => { loadLogs(); }, []);

  const runPipeline = async (name, endpoint, method = "POST") => {
    setRunning(p => ({ ...p, [name]: true }));
    setResults(p => ({ ...p, [name]: null }));
    try {
      const r = await fetch(`${API}${endpoint}`, { method });
      const data = await r.json();
      setResults(p => ({ ...p, [name]: { ok: r.ok, data } }));
    } catch (e) {
      setResults(p => ({ ...p, [name]: { ok: false, data: { error: e.message } } }));
    } finally {
      setRunning(p => ({ ...p, [name]: false }));
      setTimeout(loadLogs, 1000);
    }
  };

  const PIPELINES = [
    {
      group: "Automatic (runs on schedule)",
      items: [
        { name: "FRED Data", endpoint: "/fetch/fred", method: "POST", desc: "Fetch 24 FRED metrics (yields, oil, dollar, CPI, M2, sovereign yields). Runs daily at 2am.", schedule: "Daily 2:00am UTC" },
        { name: "TIC Holdings", endpoint: "/fetch/treasury-holdings", method: "POST", desc: "Fetch Treasury holdings from ticdata.treasury.gov. 45 countries, monthly.", schedule: "15th of month, 3:00am UTC" },
        { name: "Stress Score", endpoint: "/stress-score", method: "GET", desc: "Recalculate 4-factor macro stress index (yield curve, concentration, volatility, gold accumulation).", schedule: "Daily 4:30am UTC" },
      ]
    },
    {
      group: "Manual (CSV import)",
      items: [
        { name: "Gold Reserves", endpoint: "/fetch/gold-reserves", method: "POST", desc: "Import WGC gold reserves CSV from data/gold_reserves.csv. Re-download quarterly from gold.org.", schedule: "Manual — re-download CSV quarterly" },
      ]
    },
  ];

  return (
    <div>
      {/* Stats bar */}
      {stats && (
        <div style={{ display: "flex", gap: 12, marginBottom: 24, flexWrap: "wrap" }}>
          {[
            { label: "Total Records", val: stats.timeseries_records?.toLocaleString() },
            { label: "Metrics Tracked", val: stats.metrics },
            { label: "Countries", val: stats.countries },
            { label: "Data From", val: stats.data_earliest ? new Date(stats.data_earliest).getFullYear() : "—" },
            { label: "Latest Data", val: stats.data_latest ? new Date(stats.data_latest).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }) : "—" },
          ].map(s => (
            <div key={s.label} style={{ background: "#0F1923", border: "1px solid #1A2530", borderRadius: 2, padding: "12px 18px", flex: "1 1 140px" }}>
              <div style={{ fontFamily: "monospace", fontSize: 10, color: "#5A6878", textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 4 }}>{s.label}</div>
              <div style={{ fontFamily: "monospace", fontSize: 18, fontWeight: 700, color: "#E8E0D0" }}>{s.val}</div>
            </div>
          ))}
        </div>
      )}

      {/* Pipeline triggers */}
      {PIPELINES.map(group => (
        <div key={group.group} style={{ marginBottom: 28 }}>
          <div style={{ fontFamily: "monospace", fontSize: 10, color: "#3A4D5C", letterSpacing: "0.15em", textTransform: "uppercase", marginBottom: 12, borderBottom: "1px solid #1A2530", paddingBottom: 6 }}>{group.group}</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {group.items.map(p => {
              const res = results[p.name];
              const busy = running[p.name];
              return (
                <div key={p.name} style={{ background: "#0A1520", border: "1px solid #1A2530", borderRadius: 2, padding: "16px 20px" }}>
                  <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 16 }}>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontFamily: "monospace", fontSize: 13, color: "#E8E0D0", fontWeight: 600, marginBottom: 4 }}>{p.name}</div>
                      <div style={{ fontFamily: "monospace", fontSize: 11, color: "#5A6878", marginBottom: 4 }}>{p.desc}</div>
                      <div style={{ fontFamily: "monospace", fontSize: 10, color: "#3A4D5C" }}>⏱ {p.schedule}</div>
                    </div>
                    <button
                      onClick={() => runPipeline(p.name, p.endpoint, p.method ?? "POST")}
                      disabled={busy}
                      style={{
                        background: busy ? "#1A2530" : "#0F1923",
                        border: `1px solid ${busy ? "#3A4D5C" : "#C8A96E"}`,
                        color: busy ? "#3A4D5C" : "#C8A96E",
                        borderRadius: 2, padding: "8px 20px",
                        cursor: busy ? "not-allowed" : "pointer",
                        fontFamily: "monospace", fontSize: 12,
                        whiteSpace: "nowrap",
                      }}>
                      {busy ? "running..." : "▶ Run Now"}
                    </button>
                  </div>
                  {res && (
                    <div style={{ marginTop: 12, background: res.ok ? "#0D2010" : "#200D0D", border: `1px solid ${res.ok ? "#2A4A30" : "#4A2A2A"}`, borderRadius: 2, padding: "10px 14px" }}>
                      <div style={{ fontFamily: "monospace", fontSize: 11, color: res.ok ? "#5DB87A" : "#E07B5A", marginBottom: 4 }}>
                        {res.ok ? "✓ Success" : "✗ Failed"}
                      </div>
                      <div style={{ fontFamily: "monospace", fontSize: 11, color: "#5A6878" }}>
                        {res.ok
                          ? `Inserted: ${res.data.inserted ?? "—"} · Updated: ${res.data.updated ?? "—"} · Countries: ${res.data.countries_tracked ?? res.data.skipped !== undefined ? `${res.data.inserted + res.data.updated} records` : ""}`
                          : res.data.detail || JSON.stringify(res.data).slice(0, 120)
                        }
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      ))}

      {/* Pipeline logs */}
      <div style={{ background: "#0A1520", border: "1px solid #1A2530", borderRadius: 2, padding: "20px 0", marginTop: 8 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "0 20px 16px" }}>
          <div style={{ fontFamily: "monospace", fontSize: 12, color: "#8A9BAC", letterSpacing: "0.1em" }}>PIPELINE LOG</div>
          <button onClick={loadLogs} style={{ background: "transparent", border: "1px solid #1E2D3D", color: "#3A4D5C", borderRadius: 2, padding: "4px 10px", cursor: "pointer", fontFamily: "monospace", fontSize: 11 }}>↻ refresh</button>
        </div>
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr>
                {["Pipeline", "Status", "Inserted", "Updated", "Completed", "Error"].map(h => (
                  <th key={h} style={{ fontFamily: "monospace", fontSize: 10, color: "#3A4D5C", textTransform: "uppercase", padding: "6px 16px", textAlign: "left", borderBottom: "1px solid #1A2530", whiteSpace: "nowrap" }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {logs.map((log, i) => (
                <tr key={i} style={{ borderBottom: "1px solid #080E14" }}>
                  <td style={{ padding: "8px 16px", fontFamily: "monospace", fontSize: 12, color: "#E8E0D0" }}>{log.pipeline_name}</td>
                  <td style={{ padding: "8px 16px", fontFamily: "monospace", fontSize: 12, color: log.status === "success" ? "#5DB87A" : log.status === "partial" ? "#E8C547" : "#E07B5A" }}>{log.status}</td>
                  <td style={{ padding: "8px 16px", fontFamily: "monospace", fontSize: 12, color: "#8A9BAC" }}>{log.records_inserted?.toLocaleString()}</td>
                  <td style={{ padding: "8px 16px", fontFamily: "monospace", fontSize: 12, color: "#8A9BAC" }}>{log.records_updated?.toLocaleString()}</td>
                  <td style={{ padding: "8px 16px", fontFamily: "monospace", fontSize: 12, color: "#5A6878", whiteSpace: "nowrap" }}>
                    {log.completed_at ? new Date(log.completed_at).toLocaleString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "—"}
                  </td>
                  <td style={{ padding: "8px 16px", fontFamily: "monospace", fontSize: 11, color: "#E07B5A", maxWidth: 300, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{log.error_message || ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function AboutTab() {
  const SOURCES = [
    {
      name: "FRED — Federal Reserve Economic Data",
      url: "https://fred.stlouisfed.org",
      update: "Daily (auto)",
      lag: "1 day",
      coverage: "US only",
      metrics: ["10Y/5Y/2Y Treasury yields", "Fed Funds Rate", "Real Yield (TIPS)", "WTI Crude Oil", "Dollar Index (DXY)", "CPI", "M2 Money Supply"],
      notes: "Free API, no auth required. Key stored in .env as FRED_API_KEY. Runs automatically at 2am daily.",
      manual: false,
    },
    {
      name: "TIC — Treasury International Capital",
      url: "https://ticdata.treasury.gov",
      update: "Monthly (auto)",
      lag: "~45 days after month-end",
      coverage: "48 countries",
      metrics: ["Foreign holdings of US Treasury securities by country (monthly, in $B)"],
      notes: "Free, no auth. Parsed from mfhhis01.txt — tab-delimited historical file. Runs automatically on 15th of each month. Data as far back as 2016 for most countries.",
      manual: false,
    },
    {
      name: "World Gold Council — Gold Reserves",
      url: "https://www.gold.org/goldhub/data/gold-reserves-by-country",
      update: "Monthly (MANUAL)",
      lag: "~2 months after quarter-end",
      coverage: "120+ countries",
      metrics: ["Central bank gold reserves in tonnes (quarterly, back to Q4 2000)"],
      notes: "Requires free WGC account login. Download the historical CSV monthly and replace C:\\projects\\sentinel\\data\\gold_reserves.csv, then run POST /api/fetch/gold.",
      manual: true,
    },
    {
      name: "World Bank — Broad Money Growth",
      url: "https://api.worldbank.org/v2/country/all/indicator/FM.LBL.BMNY.ZG",
      update: "Annual (MANUAL)",
      lag: "~1 year",
      coverage: "48 countries",
      metrics: ["Annual % growth in broad money supply (M2/M3), back to 1961"],
      notes: "Free API, no auth. Download via curl and save to C:\\projects\\sentinel\\data\\money_supply.json, then run POST /api/fetch/money-supply. Re-download annually. Thresholds: >15% elevated, >30% significant debasement, >50% crisis-level.",
      manual: true,
    },
    {
      name: "World Gold Council — Spot Gold Price",
      url: "https://www.gold.org/goldhub/data/gold-prices",
      update: "Monthly (MANUAL)",
      lag: "1 month",
      coverage: "Global",
      metrics: ["Gold spot price USD/troy oz (monthly, back to January 1978)"],
      notes: "Download from WGC when logged in. Replace C:\\projects\\sentinel\\data\\gold_prices.csv and run POST /api/fetch/gold-price. Update quarterly is sufficient.",
      manual: true,
    },
  ];

  const SIGNALS = [
    {
      name: "Sovereign Stress Score",
      tier: 1,
      color: "#E8C547",
      formula: "MoM decline magnitude (0–40pts) + consecutive declining months (0–30pts) + acceleration (0–20pts)",
      threshold: "Alert: score ≥ 25 OR 3+ consecutive declining months",
      interpretation: "A country reducing treasury holdings. Could be strategic repositioning or liquidity need. Watch for persistence.",
    },
    {
      name: "Cross-Asset Stress (1.5×)",
      tier: 2,
      color: "#E07B5A",
      formula: "Treasury stress score × 1.5 when country is ALSO reducing gold reserves",
      threshold: "Fires when selling_treasuries AND selling_gold simultaneously",
      interpretation: "Selling both assets = more than repositioning. Reduced optionality. Country is drawing down its strategic reserve base.",
    },
    {
      name: "Divergence Signal (2×)",
      tier: 3,
      color: "#FF4444",
      formula: "Cross-asset score × 2 when spot gold is rising (>2% over 3 months)",
      threshold: "Fires when cross-asset AND spot_gold_rising",
      interpretation: "Selling gold INTO a rising gold price. This is the forced seller signal. A country only does this if it desperately needs USD liquidity. Maximum distress indicator.",
    },
  ];

  const FUTURE = [
    { name: "Country M2 / Broad Money Growth", why: "Sharp M2 expansion signals monetary debasement. When a country is selling reserves AND printing money, currency crisis typically follows. Best source: World Bank API (annual data free, monthly requires subscription)." },
    { name: "Currency Exchange Rates", why: "USD/local currency depreciation confirms reserve selling thesis. FRED has some pairs; full coverage needs a forex API." },
    { name: "CDS Spreads", why: "Sovereign credit default swap spreads are the market's own stress signal. Spikes often precede reserve selling. Requires Bloomberg or Markit data." },
    { name: "IMF Reserve Adequacy", why: "Ratio of reserves to short-term external debt. When this falls below 1.0, the country is vulnerable. IMF publishes annually." },
  ];

  return (
    <div>
      <div style={{ fontFamily: "monospace", fontSize: 11, color: "#5A6878", marginBottom: 28, lineHeight: 1.8, maxWidth: 800 }}>
        Project Sentinel monitors sovereign stress signals in global treasury markets. The core thesis: countries that are
        <span style={{ color: "#C8A96E" }}> forced sellers</span> of US Treasuries reveal themselves through the data before it becomes news.
        The highest-conviction signal is simultaneous selling of both treasuries and gold — especially into a rising gold price.
      </div>

      {/* Data Sources */}
      <div style={{ marginBottom: 32 }}>
        <div style={{ fontFamily: "monospace", fontSize: 10, color: "#3A4D5C", letterSpacing: "0.15em", textTransform: "uppercase", marginBottom: 16, borderBottom: "1px solid #1A2530", paddingBottom: 6 }}>DATA SOURCES</div>
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {SOURCES.map(s => (
            <div key={s.name} style={{ background: "#0A1520", border: `1px solid ${s.manual ? "#E8C54733" : "#1A2530"}`, borderLeft: `3px solid ${s.manual ? "#E8C547" : "#1A2530"}`, borderRadius: 2, padding: "16px 20px" }}>
              <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 16, flexWrap: "wrap" }}>
                <div style={{ flex: 1 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6 }}>
                    <span style={{ fontFamily: "monospace", fontSize: 13, color: "#E8E0D0", fontWeight: 600 }}>{s.name}</span>
                    <span style={{ fontFamily: "monospace", fontSize: 10, color: s.manual ? "#E8C547" : "#5DB87A", background: s.manual ? "#E8C54718" : "#5DB87A18", border: `1px solid ${s.manual ? "#E8C54744" : "#5DB87A44"}`, borderRadius: 2, padding: "1px 6px" }}>
                      {s.manual ? "⚠ MANUAL UPDATE" : "● AUTO"}
                    </span>
                  </div>
                  <div style={{ display: "flex", gap: 24, marginBottom: 8, flexWrap: "wrap" }}>
                    {[["Update", s.update], ["Lag", s.lag], ["Coverage", s.coverage]].map(([l, v]) => (
                      <div key={l}>
                        <span style={{ fontFamily: "monospace", fontSize: 10, color: "#3A4D5C" }}>{l}: </span>
                        <span style={{ fontFamily: "monospace", fontSize: 10, color: "#8A9BAC" }}>{v}</span>
                      </div>
                    ))}
                  </div>
                  <div style={{ fontFamily: "monospace", fontSize: 11, color: "#5A6878", marginBottom: 8 }}>
                    {s.metrics.map((m, i) => <div key={i}>· {m}</div>)}
                  </div>
                  <div style={{ fontFamily: "monospace", fontSize: 11, color: s.manual ? "#E8C547" : "#3A4D5C", lineHeight: 1.6 }}>{s.notes}</div>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Manual Update Checklist */}
      <div style={{ background: "#0A1520", border: "1px solid #E8C54744", borderLeft: "3px solid #E8C547", borderRadius: 2, padding: "16px 20px", marginBottom: 32 }}>
        <div style={{ fontFamily: "monospace", fontSize: 12, color: "#E8C547", marginBottom: 12, letterSpacing: "0.1em" }}>⚠ MONTHLY MANUAL UPDATE CHECKLIST</div>
        {[
          { task: "Download WGC gold reserves CSV (quarterly)", url: "https://www.gold.org/goldhub/data/gold-reserves-by-country", action: "Save as data/gold_reserves.csv in repo → commit → deploy OR run POST /api/fetch/gold-reserves" },
          { task: "Verify TIC auto-refresh ran (15th of month)", url: null, action: "Check GET /api/health — last_treasury_update should be recent" },
          { task: "Verify FRED auto-refresh ran (daily)", url: null, action: "Check GET /api/health — last_fred_update should be within 24 hrs" },
          { task: "Verify stress score recalculated", url: null, action: "GET /api/stress-score — timestamp should be today" },
        ].map((item, i) => (
          <div key={i} style={{ display: "flex", gap: 12, marginBottom: 10, alignItems: "flex-start" }}>
            <span style={{ fontFamily: "monospace", fontSize: 12, color: "#E8C547", marginTop: 1 }}>□</span>
            <div>
              <div style={{ fontFamily: "monospace", fontSize: 12, color: "#E8E0D0" }}>{item.task}</div>
              <div style={{ fontFamily: "monospace", fontSize: 11, color: "#5A6878", marginTop: 2 }}>{item.action}</div>
            </div>
          </div>
        ))}
      </div>

      {/* Signal Methodology */}
      <div style={{ marginBottom: 32 }}>
        <div style={{ fontFamily: "monospace", fontSize: 10, color: "#3A4D5C", letterSpacing: "0.15em", textTransform: "uppercase", marginBottom: 16, borderBottom: "1px solid #1A2530", paddingBottom: 6 }}>SIGNAL METHODOLOGY</div>
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {SIGNALS.map(s => (
            <div key={s.name} style={{ background: "#0A1520", border: `1px solid ${s.color}33`, borderLeft: `3px solid ${s.color}`, borderRadius: 2, padding: "16px 20px" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
                <span style={{ fontFamily: "monospace", fontSize: 10, color: s.color, background: `${s.color}18`, border: `1px solid ${s.color}44`, borderRadius: 2, padding: "1px 6px" }}>TIER {s.tier}</span>
                <span style={{ fontFamily: "monospace", fontSize: 13, color: "#E8E0D0", fontWeight: 600 }}>{s.name}</span>
              </div>
              <div style={{ fontFamily: "monospace", fontSize: 11, color: "#5A6878", marginBottom: 6 }}>Formula: {s.formula}</div>
              <div style={{ fontFamily: "monospace", fontSize: 11, color: "#5A6878", marginBottom: 6 }}>Threshold: {s.threshold}</div>
              <div style={{ fontFamily: "monospace", fontSize: 11, color: "#8A9BAC", lineHeight: 1.6 }}>{s.interpretation}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Future Pipelines */}
      <div style={{ marginBottom: 32 }}>
        <div style={{ fontFamily: "monospace", fontSize: 10, color: "#3A4D5C", letterSpacing: "0.15em", textTransform: "uppercase", marginBottom: 16, borderBottom: "1px solid #1A2530", paddingBottom: 6 }}>PLANNED PIPELINES</div>
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {FUTURE.map(f => (
            <div key={f.name} style={{ background: "#0A1520", border: "1px solid #1A2530", borderLeft: "3px solid #1E2D3D", borderRadius: 2, padding: "14px 20px" }}>
              <div style={{ fontFamily: "monospace", fontSize: 12, color: "#8A9BAC", fontWeight: 600, marginBottom: 4 }}>{f.name}</div>
              <div style={{ fontFamily: "monospace", fontSize: 11, color: "#5A6878", lineHeight: 1.6 }}>{f.why}</div>
            </div>
          ))}
        </div>
      </div>

      <div style={{ fontFamily: "monospace", fontSize: 11, color: "#1E2D3D", borderTop: "1px solid #1A2530", paddingTop: 16 }}>
        Project Sentinel · Built with FastAPI + PostgreSQL + React · Data: FRED, TIC, WGC
      </div>
    </div>
  );
}
