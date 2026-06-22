import { useState, useEffect, useCallback } from "react";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, ReferenceLine, BarChart, Bar, Cell } from "recharts";

const API = "http://localhost:8000/api";

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

const TABS = ["MARKETS", "HOLDINGS", "CROSS-ASSET", "COMPOSITE", "COUNTRY", "ADMIN", "ABOUT"];

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
};

async function generateCountryNarrative(countryData) {
  const { iso, name, ticData, goldData, moneyData, spreadBps, spreadTrend, compositeData } = countryData;
  const latestTic = ticData?.history?.slice(-1)[0];
  const prevYearTic = ticData?.history?.slice(-13, -12)[0];
  const spreadStr = spreadBps != null
    ? `${spreadBps > 0 ? "+" : ""}${spreadBps.toFixed(0)}bps vs US 10Y (${spreadTrend})`
    : "not available";

  const prompt = `You are a financial journalist writing for a sophisticated but non-specialist audience — think Bloomberg Businessweek, not the IMF. Generate a 250-350 word analyst brief for ${name} (${iso}) that makes the situation feel real and urgent, not academic.

DATA AS OF ${latestTic?.date ?? "recent"}:
TREASURY HOLDINGS: $${ticData?.summary?.latest_holdings_bn?.toFixed(1)}B current (peak was $${ticData?.summary?.peak_holdings_bn?.toFixed(1)}B), MoM ${latestTic?.mom_change_pct != null ? (latestTic.mom_change_pct > 0 ? "+" : "") + latestTic.mom_change_pct.toFixed(2) + "%" : "unknown"}, ${compositeData?.tic_consecutive_months ?? 0} consecutive months of selling, YoY: ${prevYearTic && latestTic ? (((latestTic.holdings_bn - prevYearTic.holdings_bn) / prevYearTic.holdings_bn) * 100).toFixed(1) + "%" : "n/a"}
GOLD RESERVES: ${goldData?.summary?.latest_tonnes?.toFixed(0) ?? "no data"}t (peak ${goldData?.summary?.peak_tonnes?.toFixed(0) ?? "n/a"}t, ${goldData?.summary?.drawdown_from_peak_pct?.toFixed(1) ?? "0"}% below peak)
BROAD MONEY GROWTH: ${moneyData.length > 0 ? moneyData[moneyData.length-1].pct.toFixed(1) + "% per year (" + moneyData[moneyData.length-1].date + ")" : "no data"}
SOVEREIGN BOND SPREAD: ${spreadStr}
STRESS TIER: ${compositeData?.tier ?? "WATCH"} (score ${compositeData?.composite_score?.toFixed(1) ?? "n/a"})
ACTIVE SIGNALS: ${compositeData?.active_signals?.join("; ") || "none"}

Write four short sections with these exact headers. Use plain English. Explain what the numbers mean in human terms — what is actually happening, why it matters, what the risk is. Use analogies if helpful. Avoid jargon like "MoM", "basis points", "liquidity", "repositioning" without explaining them first.

SITUATION
What is this country actually doing right now with its dollar reserves and gold? Give the reader a clear picture in 2-3 sentences. Use the real numbers but explain what they mean — e.g. "has sold X% of its peak holdings" not just the raw figure.

WHAT THIS MEANS
Is this country in trouble, or just making a strategic choice? Explain the difference between a country that is choosing to sell versus one that is forced to sell. What does the bond spread (if available) tell us about what markets think? 2-3 sentences in plain language.

THE RISK
What could go wrong from here, and what would it look like? Be specific about what threshold or event would signal things are getting worse. 2-3 sentences.

WATCH FOR
Name 2-3 specific things to check next month. Write them as plain sentences, not bullet points with jargon.  Be direct, no hedging.  Do not use markdown formatting like ##, #, ---, or ** in your response. Use plain text only.`;

const response = await fetch(`${API}/analyze/country`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt })
  });
  const data = await response.json();
  return data.text || "Analysis unavailable.";
}

function CountryDetail({ iso, onClose, standalone = false, latestAll = {} }) {
  const [ticData, setTicData] = useState(null);
  const [goldData, setGoldData] = useState(null);
  const [moneyData, setMoneyData] = useState([]);
  const [compositeData, setCompositeData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [histRange, setHistRange] = useState(120);
  const [narrative, setNarrative] = useState(null);
  const [narrativeLoading, setNarrativeLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    setNarrative(null);
    const start = new Date();
    start.setFullYear(start.getFullYear() - 30);
    Promise.all([
      fetch(`${API}/holdings/country/${iso}?months=${histRange}`).then(r => r.json()).catch(() => null),
      fetch(`${API}/holdings/gold/${iso}?months=120`).then(r => r.json()).catch(() => null),
      fetch(`${API}/timeseries?metric_codes=BROAD_MONEY_GROWTH&country_iso=${iso}&start_date=${start.toISOString()}`).then(r => r.json()).catch(() => []),
      fetch(`${API}/stress/composite`).then(r => r.json()).catch(() => null),
    ]).then(([tic, gold, money, composite]) => {
      setTicData(tic);
      setGoldData(gold);
      const moneyRows = Array.isArray(money)
        ? money.map(r => ({ date: r.date.split("T")[0].slice(0, 4), pct: parseFloat(r.value) })).filter(r => !isNaN(r.pct)).sort((a, b) => a.date.localeCompare(b.date))
        : [];
      setMoneyData(moneyRows);
      if (composite) {
        const all = [...(composite.crisis||[]), ...(composite.stressed||[]), ...(composite.elevated||[]), ...(composite.watch||[])];
        setCompositeData(all.find(c => c.country_iso === iso) || null);
      }
      setLoading(false);
    });
  }, [iso, histRange]);

  const handleGenerateNarrative = async () => {
    setNarrativeLoading(true);
    setNarrative(null);
    try {
      const yieldCode = SOVEREIGN_YIELD_CODES[iso];
      const us10y = latestAll["DGS10"];
      const countryYield = yieldCode ? latestAll[yieldCode] : null;
      const spreadBps = countryYield != null && us10y != null ? (countryYield - us10y) * 100 : null;
      const spreadTrend = spreadBps == null ? "n/a" : spreadBps > 150 ? "elevated — significant risk premium" : spreadBps > 50 ? "slight premium" : spreadBps > 0 ? "marginal premium" : spreadBps < -100 ? "deeply negative (safe-haven/YCC)" : "negative (below US)";
      const text = await generateCountryNarrative({ iso, name: ticData?.country?.name, ticData, goldData, moneyData, spreadBps, spreadTrend, compositeData });
      setNarrative(text);
    } catch (e) { setNarrative("Failed to generate analysis. Please try again."); }
    setNarrativeLoading(false);
  };

  if (loading) return <div style={{ padding: 24, fontFamily: "monospace", fontSize: 13, color: "#3A4D5C" }}>loading {iso}...</div>;
  if (!ticData) return null;

  const ticChart = ticData.history?.map(h => ({ date: h.date, holdings: h.holdings_bn, mom: h.mom_change_pct })) || [];
  const goldChart = goldData?.history?.map(h => ({ date: h.date, tonnes: h.tonnes })) || [];
  const latestMoney = moneyData.length > 0 ? moneyData[moneyData.length - 1] : null;
  const yieldCode = SOVEREIGN_YIELD_CODES[iso];
  const us10y = latestAll["DGS10"];
  const countryYield = yieldCode ? latestAll[yieldCode] : null;
  const spreadBps = countryYield != null && us10y != null ? (countryYield - us10y) * 100 : null;
  const spreadColor = spreadBps == null ? "#3A4D5C" : spreadBps > 150 ? "#FF4444" : spreadBps > 50 ? "#E07B5A" : spreadBps > 0 ? "#E8C547" : spreadBps < -100 ? "#7EB8C9" : "#5A6878";
  const tierColor = compositeData ? (compositeData.tier === "CRISIS" ? "#FF4444" : compositeData.tier === "STRESSED" ? "#E07B5A" : compositeData.tier === "ELEVATED" ? "#E8C547" : "#5A6878") : "#5A6878";

  const container = standalone ? { background: "#080E14", minHeight: "100%" } : { background: "#0A1520", border: "1px solid #1A2530", borderRadius: 2, padding: 24, marginTop: 12 };

const formatNarrative = (text) => text.split("\n").map((line, i) => {
  const trimmed = line.trim();
  if (!trimmed || trimmed === "---") return <div key={i} style={{ height: 4 }} />;
  if (trimmed.startsWith("#")) return <div key={i} style={{ fontFamily:"monospace", fontSize:11, color:"#5A6878", marginBottom:8 }}>{trimmed.replace(/^#+\s*/,"")}</div>;
  const isHeader = /^(SITUATION|WHAT THIS MEANS|THE RISK|WATCH FOR)/i.test(trimmed);
  if (isHeader) return <div key={i} style={{ fontFamily:"monospace", fontSize:10, color:"#C8A96E", letterSpacing:"0.1em", textTransform:"uppercase", marginBottom:4, marginTop: i > 0 ? 14 : 0 }}>{trimmed}</div>;
  return <div key={i} style={{ fontFamily:"monospace", fontSize:12, color:"#8A9BAC", lineHeight:1.8, marginBottom:2 }}>{trimmed}</div>;
}).filter(Boolean);

  return (
    <div style={container}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 20 }}>
        <div>
          <div style={{ fontFamily: "monospace", fontSize: standalone ? 20 : 16, color: "#E8E0D0", fontWeight: 700 }}>
            {ticData.country?.name}
            <span style={{ marginLeft: 10, fontSize: 11, color: "#3A4D5C" }}>{ticData.country?.iso} · {ticData.country?.region}</span>
            {compositeData && <span style={{ marginLeft: 12, fontFamily: "monospace", fontSize: 10, color: tierColor, background: `${tierColor}18`, border: `1px solid ${tierColor}44`, borderRadius: 2, padding: "2px 7px" }}>{compositeData.tier} · {compositeData.composite_score?.toFixed(0)}</span>}
          </div>
          <div style={{ display: "flex", gap: 24, marginTop: 12, flexWrap: "wrap" }}>
            {[
              { label: "Treasury", val: ticData.summary?.latest_holdings_bn != null ? `$${ticData.summary.latest_holdings_bn.toFixed(1)}B` : "—", color: "#C8A96E" },
              { label: "Peak", val: ticData.summary?.peak_holdings_bn != null ? `$${ticData.summary.peak_holdings_bn.toFixed(1)}B` : "—", color: "#5A6878" },
              { label: "Consec ↓", val: `${compositeData?.tic_consecutive_months ?? 0}mo`, color: (compositeData?.tic_consecutive_months ?? 0) >= 3 ? "#E07B5A" : "#5A6878" },
              { label: "Gold", val: goldData?.summary?.latest_tonnes != null ? `${goldData.summary.latest_tonnes.toFixed(0)}t` : "—", color: "#C8A96E" },
              { label: "M2 Growth", val: latestMoney ? `${latestMoney.pct.toFixed(1)}% (${latestMoney.date})` : "—", color: latestMoney?.pct > 30 ? "#E07B5A" : latestMoney?.pct > 15 ? "#E8C547" : "#5DB87A" },
              { label: "Bond Spread", val: spreadBps != null ? `${spreadBps > 0 ? "+" : ""}${spreadBps.toFixed(0)}bps` : "—", color: spreadColor },
            ].map(s => <div key={s.label}><div style={{ fontFamily: "monospace", fontSize: 10, color: "#3A4D5C", letterSpacing: "0.1em", textTransform: "uppercase" }}>{s.label}</div><div style={{ fontFamily: "monospace", fontSize: 15, color: s.color, marginTop: 2 }}>{s.val}</div></div>)}
          </div>
        </div>
        <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
          {[[24,"2Y"],[60,"5Y"],[120,"10Y"]].map(([m, l]) => <button key={l} onClick={() => setHistRange(m)} style={{ background: histRange===m?"#1A2530":"transparent", border:`1px solid ${histRange===m?"#5A6878":"#1E2D3D"}`, color:histRange===m?"#C8A96E":"#3A4D5C", borderRadius:2, padding:"3px 8px", cursor:"pointer", fontFamily:"monospace", fontSize:11 }}>{l}</button>)}
          {!standalone && onClose && <button onClick={onClose} style={{ background:"transparent", border:"1px solid #1E2D3D", color:"#5A6878", borderRadius:2, padding:"4px 10px", cursor:"pointer", fontFamily:"monospace", fontSize:12 }}>✕</button>}
        </div>
      </div>

      {/* AI Narrative */}
      <div style={{ background:"#060D14", border:"1px solid #C8A96E33", borderLeft:"3px solid #C8A96E", borderRadius:2, padding:"16px 20px", marginBottom:20 }}>
        <div style={{ display:"flex", alignItems:"center", justifyContent:"space-between", marginBottom: narrative||narrativeLoading ? 16 : 0 }}>
          <div>
            <div style={{ fontFamily:"monospace", fontSize:11, color:"#C8A96E", letterSpacing:"0.1em", marginBottom:2 }}>SENTINEL ANALYST BRIEF</div>
            {!narrative && !narrativeLoading && <div style={{ fontFamily:"monospace", fontSize:11, color:"#3A4D5C" }}>AI-generated narrative using all available data — treasury, gold, M2, sovereign spread, composite score</div>}
          </div>
          <button onClick={handleGenerateNarrative} disabled={narrativeLoading} style={{ background:narrativeLoading?"#0F1923":"#C8A96E18", border:`1px solid ${narrativeLoading?"#1E2D3D":"#C8A96E"}`, color:narrativeLoading?"#3A4D5C":"#C8A96E", borderRadius:2, padding:"8px 16px", cursor:narrativeLoading?"not-allowed":"pointer", fontFamily:"monospace", fontSize:12, whiteSpace:"nowrap" }}>
            {narrativeLoading ? "⟳ Generating..." : narrative ? "↻ Regenerate" : "▶ Generate Analysis"}
          </button>
        </div>
        {narrativeLoading && <div style={{ fontFamily:"monospace", fontSize:12, color:"#3A4D5C", lineHeight:1.8 }}>Analyzing treasury data, gold reserves, monetary policy, sovereign spreads, and composite stress signals...</div>}
        {narrative && !narrativeLoading && (
          <div style={{ borderTop:"1px solid #1A2530", paddingTop:14 }}>
            {formatNarrative(narrative)}
            <div style={{ fontFamily:"monospace", fontSize:10, color:"#1E2D3D", marginTop:12, borderTop:"1px solid #1A2530", paddingTop:8 }}>
              Generated by Claude · Data: US Treasury TIC · World Gold Council · World Bank · OECD/FRED · Project Sentinel composite scorer
            </div>
          </div>
        )}
      </div>

      {/* Sovereign spread */}
      {spreadBps != null && (
        <div style={{ background:"#0A1520", border:`1px solid ${spreadColor}33`, borderRadius:2, padding:"12px 16px", marginBottom:16 }}>
          <div style={{ display:"flex", alignItems:"center", gap:16, flexWrap:"wrap" }}>
            <div>
              <div style={{ fontFamily:"monospace", fontSize:10, color:"#3A4D5C", letterSpacing:"0.1em", marginBottom:3 }}>SOVEREIGN BOND SPREAD VS US 10Y</div>
              <span style={{ fontFamily:"monospace", fontSize:18, fontWeight:700, color:spreadColor }}>{spreadBps>0?"+":""}{spreadBps.toFixed(0)}bps</span>
              <span style={{ fontFamily:"monospace", fontSize:11, color:"#5A6878", marginLeft:12 }}>
                {spreadBps>150?"⚠ ELEVATED — market pricing significant risk premium":spreadBps>50?"Mild premium — slight credit/inflation concern":spreadBps>0?"Negligible premium vs US":spreadBps<-100?"Deeply negative — safe-haven or YCC effect":"Negative — policy divergence or safe-haven flow"}
              </span>
            </div>
            <div style={{ fontFamily:"monospace", fontSize:10, color:"#3A4D5C", lineHeight:1.6 }}>
              {countryYield?.toFixed(2)}% ({iso} 10Y) − {us10y?.toFixed(2)}% (US 10Y) = {spreadBps>0?"+":""}{spreadBps.toFixed(0)}bps · Positive = country pays more · Widening = rising market concern
            </div>
          </div>
        </div>
      )}

      {/* Treasury chart */}
      <div style={{ marginBottom:8 }}>
        <div style={{ fontFamily:"monospace", fontSize:10, color:"#3A4D5C", letterSpacing:"0.1em", marginBottom:8 }}>TREASURY HOLDINGS (USD billions) — red = declining month</div>
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={ticChart} margin={{ top:4, right:8, bottom:4, left:8 }}>
            <CartesianGrid strokeDasharray="2 6" stroke="#0F1923" vertical={false} />
            <XAxis dataKey="date" tick={{ fill:"#3A4D5C", fontFamily:"monospace", fontSize:10 }} axisLine={false} tickLine={false} minTickGap={40} />
            <YAxis tick={{ fill:"#3A4D5C", fontFamily:"monospace", fontSize:10 }} axisLine={false} tickLine={false} width={52} tickFormatter={v=>`$${v}B`} />
            <Tooltip formatter={(val)=>[`$${val?.toFixed(1)}B`,"Holdings"]} contentStyle={{ background:"#0A1520", border:"1px solid #1E2D3D", borderRadius:2, fontFamily:"monospace", fontSize:12 }} labelStyle={{ color:"#5A6878" }} />
            <Bar dataKey="holdings" radius={[2,2,0,0]}>
              {ticChart.map((e,i)=><Cell key={i} fill={e.mom!=null&&e.mom<0?"#E07B5A":"#5DB87A"} fillOpacity={0.75}/>)}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Gold chart */}
      {goldChart.length > 0 && (
        <div style={{ marginBottom:20 }}>
          <div style={{ fontFamily:"monospace", fontSize:10, color:"#3A4D5C", letterSpacing:"0.1em", marginBottom:8 }}>GOLD RESERVES (tonnes) — quarterly</div>
          <ResponsiveContainer width="100%" height={160}>
            <LineChart data={goldChart} margin={{ top:4, right:8, bottom:4, left:8 }}>
              <CartesianGrid strokeDasharray="2 6" stroke="#0F1923" vertical={false} />
              <XAxis dataKey="date" tick={{ fill:"#3A4D5C", fontFamily:"monospace", fontSize:10 }} axisLine={false} tickLine={false} minTickGap={40} />
              <YAxis tick={{ fill:"#3A4D5C", fontFamily:"monospace", fontSize:10 }} axisLine={false} tickLine={false} width={52} tickFormatter={v=>`${v}t`} />
              <Tooltip formatter={(val)=>[`${val?.toFixed(1)}t`,"Gold"]} contentStyle={{ background:"#0A1520", border:"1px solid #1E2D3D", borderRadius:2, fontFamily:"monospace", fontSize:12 }} labelStyle={{ color:"#5A6878" }} />
              <Line type="monotone" dataKey="tonnes" stroke="#C8A96E" strokeWidth={1.5} dot={false} connectNulls />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* M2 chart */}
      {moneyData.length > 0 && (
        <div style={{ marginBottom:20 }}>
          <div style={{ display:"flex", alignItems:"center", gap:12, marginBottom:8 }}>
            <div style={{ fontFamily:"monospace", fontSize:10, color:"#3A4D5C", letterSpacing:"0.1em" }}>BROAD MONEY GROWTH (% YoY)</div>
            {latestMoney && <span style={{ fontFamily:"monospace", fontSize:10, color:latestMoney.pct>30?"#E07B5A":latestMoney.pct>15?"#E8C547":"#5DB87A", background:`${latestMoney.pct>30?"#E07B5A":latestMoney.pct>15?"#E8C547":"#5DB87A"}18`, border:`1px solid ${latestMoney.pct>30?"#E07B5A":latestMoney.pct>15?"#E8C547":"#5DB87A"}44`, borderRadius:2, padding:"1px 6px" }}>{latestMoney.pct.toFixed(1)}% in {latestMoney.date}{latestMoney.pct>50?" ⚠ CRISIS":latestMoney.pct>30?" ⚠ HIGH":latestMoney.pct>15?" ELEVATED":""}</span>}
          </div>
          <ResponsiveContainer width="100%" height={160}>
            <LineChart data={moneyData} margin={{ top:4, right:8, bottom:4, left:8 }}>
              <CartesianGrid strokeDasharray="2 6" stroke="#0F1923" vertical={false} />
              <XAxis dataKey="date" tick={{ fill:"#3A4D5C", fontFamily:"monospace", fontSize:10 }} axisLine={false} tickLine={false} minTickGap={30} />
              <YAxis tick={{ fill:"#3A4D5C", fontFamily:"monospace", fontSize:10 }} axisLine={false} tickLine={false} width={44} tickFormatter={v=>`${v}%`} />
              <ReferenceLine y={20} stroke="#E07B5A" strokeDasharray="4 4" strokeOpacity={0.5} />
              <Tooltip formatter={(v)=>[`${v?.toFixed(1)}%`,"M2 Growth"]} contentStyle={{ background:"#0A1520", border:"1px solid #1E2D3D", borderRadius:2, fontFamily:"monospace", fontSize:12 }} labelStyle={{ color:"#5A6878" }} />
              <Line type="monotone" dataKey="pct" stroke="#9B8EC4" strokeWidth={1.5} dot={(props)=>{ const {cx,cy,payload}=props; const c=payload.pct>30?"#E07B5A":payload.pct>15?"#E8C547":"#9B8EC4"; return <circle key={`d${cx}${cy}`} cx={cx} cy={cy} r={3} fill={c}/>; }} connectNulls />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* History table */}
      <div style={{ overflowX:"auto", maxHeight:360, overflowY:"auto" }}>
        <table style={{ width:"100%", borderCollapse:"collapse" }}>
          <thead style={{ position:"sticky", top:0, background:standalone?"#080E14":"#0A1520" }}>
            <tr>{["Date","Holdings $B","MoM %","Trend"].map(h=><th key={h} style={{ fontFamily:"monospace", fontSize:10, color:"#3A4D5C", textTransform:"uppercase", padding:"6px 10px", textAlign:h==="Date"?"left":"right", borderBottom:"1px solid #1A2530" }}>{h}</th>)}</tr>
          </thead>
          <tbody>
            {[...(ticData.history||[])].reverse().map((row,i)=>(
              <tr key={i} style={{ borderBottom:"1px solid #080E14" }}>
                <td style={{ padding:"6px 10px", fontFamily:"monospace", fontSize:12, color:"#8A9BAC" }}>{row.date}</td>
                <td style={{ padding:"6px 10px", fontFamily:"monospace", fontSize:12, color:"#E8E0D0", textAlign:"right" }}>${row.holdings_bn.toFixed(1)}B</td>
                <td style={{ padding:"6px 10px", fontFamily:"monospace", fontSize:12, textAlign:"right", color:row.mom_change_pct==null?"#3A4D5C":row.mom_change_pct<0?"#E07B5A":"#5DB87A" }}>{row.mom_change_pct!=null?`${row.mom_change_pct>0?"+":""}${row.mom_change_pct.toFixed(2)}%`:"—"}</td>
                <td style={{ padding:"6px 10px", textAlign:"right" }}>{row.mom_change_pct!=null&&<span style={{ fontFamily:"monospace", fontSize:14, color:row.mom_change_pct<0?"#E07B5A":"#5DB87A" }}>{row.mom_change_pct<0?"▼":"▲"}</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
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
  const [summary, setSummary] = useState(null);
  const [stress, setStress] = useState(null);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState(null);
  const [view, setView] = useState("stress");

  useEffect(() => {
    Promise.all([
      fetch(`${API}/holdings/summary`).then(r => r.json()),
      fetch(`${API}/holdings/stress`).then(r => r.json()),
    ]).then(([s, st]) => { setSummary(s); setStress(st); setLoading(false); }).catch(() => setLoading(false));
  }, []);

  if (loading) return <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: 300, fontFamily: "monospace", fontSize: 13, color: "#3A4D5C" }}>loading...</div>;
  if (!summary || summary.error) return <div style={{ fontFamily: "monospace", color: "#E07B5A", padding: 24 }}>No TIC data. Run POST /api/fetch/tic</div>;

  const stressCountries = stress ? [...(stress.alerts || []), ...(stress.watch_list || [])] : [];
  const allCountries = summary.top_holders ? [
    ...summary.most_stressed,
    ...summary.top_holders.filter(c => !summary.most_stressed.find(s => s.iso === c.iso))
  ].map(c => ({ country_iso: c.iso, country_name: c.name, region: c.region, latest_holdings_bn: c.holdings_bn, mom_change_pct: c.mom_change_pct, consecutive_declining_months: c.consecutive_declining ?? 0, stress_score: c.stress_score ?? 0, alert: c.alert ?? false })) : [];

  const displayCountries = view === "stress" ? stressCountries : allCountries;
  const noBuyers = summary.biggest_buyers?.length === 0;
  const alertCount = stress?.alerts?.length ?? 0;

  const handleSelect = (c) => {
    setSelected(c?.country_iso === selected?.country_iso ? null : c);
  };

  return (
    <div>
      <div style={{ display: "flex", gap: 12, marginBottom: 20, flexWrap: "wrap" }}>
        {[
          { label: "Total Foreign Holdings", val: `$${(summary.total_foreign_holdings_bn / 1000).toFixed(2)}T` },
          { label: "Countries Reporting", val: summary.countries_reporting },
          { label: "Countries Under Stress", val: stressCountries.length, alert: stressCountries.length > 10 },
          { label: "Active Alerts", val: alertCount, alert: alertCount > 0 },
          { label: "Data As Of", val: summary.as_of },
        ].map(s => (
          <div key={s.label} style={{ background: "#0F1923", border: `1px solid ${s.alert ? "#E07B5A33" : "#1A2530"}`, borderTop: `2px solid ${s.alert ? "#E07B5A" : "#1A2530"}`, borderRadius: 2, padding: "14px 20px", flex: "1 1 140px" }}>
            <div style={{ fontFamily: "monospace", fontSize: 10, color: "#5A6878", textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 6 }}>{s.label}</div>
            <div style={{ fontFamily: "monospace", fontSize: 20, fontWeight: 700, color: s.alert ? "#E07B5A" : "#E8E0D0" }}>{s.val}</div>
          </div>
        ))}
      </div>

      {noBuyers && <AlertBanner message={`No net buyers in ${summary.as_of} — all tracked countries reducing or flat.`} color="#E07B5A" />}
      {alertCount >= 5 && <AlertBanner message={`${alertCount} countries on active stress alert.`} color="#E8C547" />}

      {/* Top holders quick cards */}
      <div style={{ display: "flex", gap: 8, marginBottom: 20, flexWrap: "wrap" }}>
        {(summary.top_holders || []).slice(0, 8).map(c => (
          <div key={c.iso}
            onClick={() => onCountrySelect(c.iso)}
            style={{ background: "#0A1520", border: `1px solid ${c.alert ? "#E07B5A44" : "#1A2530"}`, borderRadius: 2, padding: "8px 14px", cursor: "pointer", flex: "1 1 110px", maxWidth: 160 }}>
            <div style={{ fontFamily: "monospace", fontSize: 10, color: "#5A6878" }}>{c.iso}</div>
            <div style={{ fontFamily: "monospace", fontSize: 13, color: "#E8E0D0", marginTop: 2 }}>${c.holdings_bn?.toFixed(0)}B</div>
            <div style={{ fontFamily: "monospace", fontSize: 11, color: c.mom_change_pct == null ? "#3A4D5C" : c.mom_change_pct < 0 ? "#E07B5A" : "#5DB87A", marginTop: 2 }}>
              {c.mom_change_pct != null ? `${c.mom_change_pct > 0 ? "+" : ""}${c.mom_change_pct.toFixed(1)}%` : "—"}
            </div>
          </div>
        ))}
      </div>

      {/* Inline country detail */}
      {selected && (
        <CountryDetail iso={selected.country_iso ?? selected.iso} onClose={() => setSelected(null)} latestAll={latest} />
      )}

      {/* Stress leaderboard */}
      <div style={{ background: "#0A1520", border: "1px solid #1A2530", borderRadius: 2, padding: "20px 0" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "0 20px 16px" }}>
          <div style={{ fontFamily: "monospace", fontSize: 12, color: "#8A9BAC", letterSpacing: "0.1em" }}>
            SOVEREIGN STRESS LEADERBOARD
            <span style={{ marginLeft: 10, fontSize: 10, color: "#3A4D5C" }}>click row · click ISO card for full view</span>
          </div>
          <div style={{ display: "flex", gap: 6 }}>
            {[["stress", "STRESSED"], ["all", "ALL"]].map(([v, l]) => (
              <button key={v} onClick={() => setView(v)} style={{ background: view === v ? "#1A2530" : "transparent", border: `1px solid ${view === v ? "#5A6878" : "#1E2D3D"}`, color: view === v ? "#C8A96E" : "#3A4D5C", borderRadius: 2, padding: "4px 10px", cursor: "pointer", fontFamily: "monospace", fontSize: 11 }}>{l}</button>
            ))}
          </div>
        </div>
        {displayCountries.length === 0
          ? <div style={{ padding: "40px 20px", fontFamily: "monospace", fontSize: 13, color: "#3A4D5C", textAlign: "center" }}>no countries in this view</div>
          : <StressTable countries={displayCountries} onSelect={handleSelect} selected={selected} />}
      </div>
      <div style={{ marginTop: 12, fontFamily: "monospace", fontSize: 11, color: "#1E2D3D" }}>Source: US Treasury TIC · Data as of {summary.as_of}</div>
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

function SpotGoldChart() {
  const [chartData, setChartData] = useState([]);
  const [range, setRange] = useState(365);

  useEffect(() => {
    const end = new Date();
    const start = new Date();
    start.setDate(start.getDate() - range);
    fetch(`${API}/timeseries?metric_codes=GOLD_SPOT_USD&start_date=${start.toISOString()}&end_date=${end.toISOString()}`)
      .then(r => r.json())
      .then(rows => setChartData(rows.map(r => ({ date: r.date.split("T")[0], price: parseFloat(r.value) }))))
      .catch(() => {});
  }, [range]);

  if (!chartData.length) return (
    <div style={{ height: 100, display: "flex", alignItems: "center", justifyContent: "center", fontFamily: "monospace", fontSize: 12, color: "#3A4D5C", background: "#0A1520", border: "1px solid #1A2530", borderRadius: 2, marginBottom: 20 }}>
      no gold price data — run POST /api/fetch/gold-price
    </div>
  );

  const latest = chartData[chartData.length - 1]?.price;
  const start = chartData[0]?.price;
  const changePct = start ? ((latest - start) / start * 100).toFixed(1) : null;
  const rising = changePct > 0;

  return (
    <div style={{ background: "#0A1520", border: "1px solid #1A2530", borderRadius: 2, padding: "20px 24px", marginBottom: 20 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 16 }}>
          <span style={{ fontFamily: "monospace", fontSize: 12, color: "#8A9BAC", letterSpacing: "0.1em" }}>SPOT GOLD</span>
          {latest && <span style={{ fontFamily: "monospace", fontSize: 22, color: "#C8A96E", fontWeight: 700 }}>${latest.toLocaleString()}</span>}
          {changePct && <span style={{ fontFamily: "monospace", fontSize: 13, color: rising ? "#5DB87A" : "#E07B5A" }}>{rising ? "▲" : "▼"} {Math.abs(changePct)}%</span>}
        </div>
        <div style={{ display: "flex", gap: 6 }}>
          {[["3M", 90], ["6M", 180], ["1Y", 365], ["5Y", 1825]].map(([l, d]) => (
            <button key={l} onClick={() => setRange(d)} style={{ background: range === d ? "#1A2530" : "transparent", border: `1px solid ${range === d ? "#5A6878" : "#1E2D3D"}`, color: range === d ? "#C8A96E" : "#3A4D5C", borderRadius: 2, padding: "3px 10px", cursor: "pointer", fontFamily: "monospace", fontSize: 11 }}>{l}</button>
          ))}
        </div>
      </div>
      <ResponsiveContainer width="100%" height={160}>
        <LineChart data={chartData} margin={{ top: 4, right: 8, bottom: 4, left: 8 }}>
          <CartesianGrid strokeDasharray="2 6" stroke="#0F1923" vertical={false} />
          <XAxis dataKey="date" tickFormatter={formatDate} tick={{ fill: "#3A4D5C", fontFamily: "monospace", fontSize: 10 }} axisLine={false} tickLine={false} minTickGap={60} />
          <YAxis tick={{ fill: "#3A4D5C", fontFamily: "monospace", fontSize: 10 }} axisLine={false} tickLine={false} width={56} tickFormatter={v => `$${v.toLocaleString()}`} />
          <Tooltip formatter={(v) => [`$${v.toLocaleString()}`, "Gold"]} contentStyle={{ background: "#0A1520", border: "1px solid #1E2D3D", borderRadius: 2, fontFamily: "monospace", fontSize: 12 }} labelStyle={{ color: "#5A6878" }} labelFormatter={formatDate} />
          <Line type="monotone" dataKey="price" stroke="#C8A96E" strokeWidth={1.5} dot={false} activeDot={{ r: 3 }} connectNulls />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

function CrossAssetTable({ data }) {
  const [sort, setSort] = useState("stress_score");
  const sorted = [...data].sort((a, b) => {
    if (sort === "stress_score") return b.stress_score - a.stress_score;
    if (sort === "tic") return a.tic_mom_pct - b.tic_mom_pct;
    if (sort === "gold") return (a.gold_mom_pct ?? 0) - (b.gold_mom_pct ?? 0);
    if (sort === "consec") return b.tic_consecutive_months - a.tic_consecutive_months;
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
            <th style={{ fontFamily: "monospace", fontSize: 10, color: "#3A4D5C", textTransform: "uppercase", padding: "8px 12px", textAlign: "left", borderBottom: "1px solid #1A2530" }}>Signal</th>
            {col("T-Bills MoM", "tic")}
            {col("Consec ↓", "consec")}
            {col("Gold t", "gold")}
            {col("Gold MoM", "gold")}
            <th style={{ fontFamily: "monospace", fontSize: 10, color: "#3A4D5C", textTransform: "uppercase", padding: "8px 12px", borderBottom: "1px solid #1A2530", minWidth: 120 }}>Score</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map(c => {
            const tc = tierColor(c.signal_tier);
            return (
              <tr key={c.country_iso} style={{ borderBottom: "1px solid #0F1923" }}
                onMouseEnter={e => e.currentTarget.style.background = "#0D1820"}
                onMouseLeave={e => e.currentTarget.style.background = "transparent"}>
                <td style={{ padding: "10px 12px", fontFamily: "monospace", fontSize: 13, color: "#E8E0D0" }}>
                  {c.country_name}<span style={{ marginLeft: 6, fontSize: 10, color: "#3A4D5C" }}>{c.country_iso}</span>
                </td>
                <td style={{ padding: "10px 12px" }}>
                  <span style={{ fontFamily: "monospace", fontSize: 10, color: tc, background: `${tc}18`, border: `1px solid ${tc}44`, borderRadius: 2, padding: "2px 6px", whiteSpace: "nowrap" }}>{tierLabel(c.signal_tier)}</span>
                </td>
                <td style={{ padding: "10px 12px", fontFamily: "monospace", fontSize: 12, textAlign: "right", color: c.tic_mom_pct < 0 ? "#E07B5A" : "#5DB87A" }}>{c.tic_mom_pct > 0 ? "+" : ""}{c.tic_mom_pct.toFixed(2)}%</td>
                <td style={{ padding: "10px 12px", fontFamily: "monospace", fontSize: 12, textAlign: "right", color: c.tic_consecutive_months >= 3 ? "#E07B5A" : "#8A9BAC" }}>{c.tic_consecutive_months > 0 ? `${c.tic_consecutive_months}mo` : "—"}</td>
                <td style={{ padding: "10px 12px", fontFamily: "monospace", fontSize: 12, textAlign: "right", color: "#8A9BAC" }}>{c.gold_tonnes != null ? `${c.gold_tonnes.toLocaleString()}t` : "—"}</td>
                <td style={{ padding: "10px 12px", fontFamily: "monospace", fontSize: 12, textAlign: "right", color: c.gold_mom_pct == null ? "#3A4D5C" : c.gold_mom_pct < 0 ? "#E07B5A" : "#5DB87A" }}>
                  {c.gold_mom_pct != null ? `${c.gold_mom_pct > 0 ? "+" : ""}${c.gold_mom_pct.toFixed(2)}%` : "—"}
                </td>
                <td style={{ padding: "10px 12px", minWidth: 140 }}><StressBar score={c.stress_score} max={150} /></td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

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

  if (loading) return <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: 300, fontFamily: "monospace", fontSize: 13, color: "#3A4D5C" }}>loading...</div>;
  if (!data) return <div style={{ fontFamily: "monospace", color: "#E07B5A", padding: 24 }}>Failed to load cross-asset data.</div>;

  const { summary } = data;
  const allStressed = [...(data.cross_asset_stress || []), ...(data.treasury_only_stress || []), ...(data.gold_only_stress || [])];
  const displayData = view === "cross" ? data.cross_asset_stress : view === "treasury" ? data.treasury_only_stress : allStressed;
  const spotRising = allStressed[0]?.spot_gold_rising;
  const spotPrice = allStressed[0]?.spot_gold_price;
  const spot3m = allStressed[0]?.spot_gold_3m_pct;

  return (
    <div>
      <SpotGoldChart />
      {spotRising === false && summary.cross_asset_stressed === 0 && (
        <AlertBanner message="Spot gold declining — divergence signal inactive. Scoring at base multipliers." color="#5A6878" />
      )}
      {spotRising === true && summary.cross_asset_stressed > 0 && (
        <AlertBanner message={`⚡ DIVERGENCE ACTIVE — ${summary.cross_asset_stressed} countr${summary.cross_asset_stressed === 1 ? "y" : "ies"} selling gold INTO rising spot price. Maximum distress.`} color="#FF4444" />
      )}
      {spotRising === true && summary.cross_asset_stressed === 0 && (
        <AlertBanner message="Spot gold rising — 2x divergence multiplier activates if any country begins selling reserves." color="#C8A96E" />
      )}

      <div style={{ display: "flex", gap: 12, marginBottom: 20, flexWrap: "wrap" }}>
        {[
          { label: "Cross-Asset Stress", val: summary.cross_asset_stressed, alert: summary.cross_asset_stressed > 0, color: "#E07B5A" },
          { label: "Treasury-Only Stress", val: summary.treasury_only, alert: summary.treasury_only > 5, color: "#E8C547" },
          { label: "Gold-Only Stress", val: summary.gold_only, alert: false, color: "#C8A96E" },
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
          { tier: "DIVERGENCE", label: "⚡ Divergence", desc: "Selling gold INTO rising spot. 2x score.", color: "#FF4444" },
          { tier: "CROSS_ASSET", label: "⚠ Cross-Asset", desc: "Selling both treasuries AND gold. 1.5x score.", color: "#E07B5A" },
          { tier: "TREASURY_ONLY", label: "T-Bills Only", desc: "Reducing treasury holdings. 1x.", color: "#E8C547" },
          { tier: "GOLD_ONLY", label: "Au Only", desc: "Reducing gold reserves only. 1x.", color: "#C8A96E" },
        ].map(s => (
          <div key={s.tier} style={{ display: "flex", alignItems: "flex-start", gap: 10 }}>
            <span style={{ fontFamily: "monospace", fontSize: 10, color: s.color, background: `${s.color}18`, border: `1px solid ${s.color}44`, borderRadius: 2, padding: "2px 6px", whiteSpace: "nowrap", marginTop: 2 }}>{s.label}</span>
            <span style={{ fontFamily: "monospace", fontSize: 11, color: "#5A6878" }}>{s.desc}</span>
          </div>
        ))}
      </div>

      <div style={{ background: "#0A1520", border: "1px solid #1A2530", borderRadius: 2, padding: "20px 0" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "0 20px 16px" }}>
          <div style={{ fontFamily: "monospace", fontSize: 12, color: "#8A9BAC", letterSpacing: "0.1em" }}>CROSS-ASSET STRESS LEADERBOARD</div>
          <div style={{ display: "flex", gap: 6 }}>
            {[["all", "ALL"], ["cross", "CROSS-ASSET"], ["treasury", "T-ONLY"]].map(([v, l]) => (
              <button key={v} onClick={() => setView(v)} style={{ background: view === v ? "#1A2530" : "transparent", border: `1px solid ${view === v ? "#5A6878" : "#1E2D3D"}`, color: view === v ? "#C8A96E" : "#3A4D5C", borderRadius: 2, padding: "4px 10px", cursor: "pointer", fontFamily: "monospace", fontSize: 11 }}>{l}</button>
            ))}
          </div>
        </div>
        {displayData.length === 0
          ? <div style={{ padding: "40px 20px", fontFamily: "monospace", fontSize: 13, color: "#3A4D5C", textAlign: "center" }}>no countries in this view</div>
          : <CrossAssetTable data={displayData} />}
      </div>
      <div style={{ marginTop: 12, fontFamily: "monospace", fontSize: 11, color: "#1E2D3D" }}>Sources: US Treasury TIC · World Gold Council · WGC/ICE spot gold</div>
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
    const allCodes = [...METRICS.map(m => m.code),"IRLTLT01JPM156N","IRLTLT01DEM156N","IRLTLT01ITM156N","IRLTLT01FRM156N","IRLTLT01ESM156N","IRLTLT01GBM156N","IRLTLT01AUM156N","IRLTLT01CAM156N"].join(",");
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
  "IRLTLT01ESM156N","IRLTLT01GBM156N","IRLTLT01AUM156N","IRLTLT01CAM156N"
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

        {tab === "HOLDINGS" && <HoldingsTab onCountrySelect={handleCountrySelect} latestAll={latest} />}
        {tab === "CROSS-ASSET" && <CrossAssetTab />}
        {tab === "COMPOSITE" && <CompositeTab onCountrySelect={handleCountrySelect} />}
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

  if (loading) return <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: 300, fontFamily: "monospace", fontSize: 13, color: "#3A4D5C" }}>computing composite stress...</div>;
  if (!data) return <div style={{ fontFamily: "monospace", color: "#E07B5A", padding: 24 }}>Failed to load composite stress data.</div>;

  const { summary } = data;
  const allResults = [...(data.crisis||[]), ...(data.stressed||[]), ...(data.elevated||[]), ...(data.watch||[])];
  const displayData = view === "crisis" ? data.crisis
    : view === "stressed" ? [...(data.crisis||[]), ...(data.stressed||[])]
    : view === "elevated" ? [...(data.crisis||[]), ...(data.stressed||[]), ...(data.elevated||[])]
    : allResults;

  const TIER_COLORS = { CRISIS: "#FF4444", STRESSED: "#E07B5A", ELEVATED: "#E8C547", WATCH: "#5A6878" };

  return (
    <div>
      {/* Context banner */}
      {summary.crisis === 0 && summary.stressed === 0 && (
        <div style={{ background: "#5DB87A15", border: "1px solid #5DB87A44", borderLeft: "3px solid #5DB87A", borderRadius: 2, padding: "10px 16px", marginBottom: 20, fontFamily: "monospace", fontSize: 12, color: "#5DB87A" }}>
          ✓ No CRISIS or STRESSED signals active as of {data.as_of} — system is calibrated and monitoring. Broad-based low-grade stress across {allResults.length} countries.
        </div>
      )}
      {summary.crisis > 0 && (
        <AlertBanner message={`⚡ ${summary.crisis} CRISIS-tier countr${summary.crisis === 1 ? "y" : "ies"} — all three stress dimensions firing with multipliers active.`} color="#FF4444" />
      )}

      {/* Score methodology explainer */}
      <div style={{ background: "#0A1520", border: "1px solid #1A2530", borderRadius: 2, padding: "14px 20px", marginBottom: 20, display: "flex", gap: 28, flexWrap: "wrap" }}>
        <div style={{ fontFamily: "monospace", fontSize: 10, color: "#3A4D5C", letterSpacing: "0.1em", alignSelf: "center" }}>SCORE =</div>
        {[
          { label: "Treasury", desc: "MoM decline + consecutive months", max: "0–50 pts", color: "#C8A96E" },
          { label: "Gold Reserves", desc: "QoQ decline + consecutive quarters", max: "0–40 pts", color: "#E8C547" },
          { label: "M2 Growth", desc: ">15%=10, >30%=20, >50%=35 pts", max: "0–35 pts", color: "#9B8EC4" },
        ].map(s => (
          <div key={s.label} style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <div style={{ width: 8, height: 8, borderRadius: "50%", background: s.color, flexShrink: 0 }} />
            <div>
              <div style={{ fontFamily: "monospace", fontSize: 11, color: "#E8E0D0" }}>{s.label} <span style={{ color: "#3A4D5C" }}>{s.max}</span></div>
              <div style={{ fontFamily: "monospace", fontSize: 10, color: "#5A6878" }}>{s.desc}</div>
            </div>
          </div>
        ))}
        <div style={{ display: "flex", alignItems: "center", gap: 8, borderLeft: "1px solid #1A2530", paddingLeft: 20 }}>
          <div>
            <div style={{ fontFamily: "monospace", fontSize: 11, color: "#E07B5A" }}>× 1.5 all three firing</div>
            <div style={{ fontFamily: "monospace", fontSize: 11, color: "#FF4444" }}>× 2.0 gold sold into rising price</div>
          </div>
        </div>
      </div>

      {/* Summary cards */}
      <div style={{ display: "flex", gap: 12, marginBottom: 20, flexWrap: "wrap" }}>
        {[
          { label: "CRISIS", val: summary.crisis, color: "#FF4444", desc: "All 3 signals + multiplier" },
          { label: "STRESSED", val: summary.stressed, color: "#E07B5A", desc: "Score 50–75" },
          { label: "ELEVATED", val: summary.elevated, color: "#E8C547", desc: "Score 25–50" },
          { label: "WATCH", val: summary.watch, color: "#5A6878", desc: "Score < 25" },
          { label: "Top Risk", val: summary.highest_risk?.country_name ?? "—", color: "#C8A96E", desc: `Score: ${summary.highest_risk?.composite_score ?? "—"}` },
        ].map(s => (
          <div key={s.label} style={{ background: "#0F1923", border: `1px solid ${s.val > 0 && s.label !== "Top Risk" ? `${s.color}33` : "#1A2530"}`, borderTop: `2px solid ${s.val > 0 || s.label === "Top Risk" ? s.color : "#1A2530"}`, borderRadius: 2, padding: "14px 20px", flex: "1 1 140px" }}>
            <div style={{ fontFamily: "monospace", fontSize: 10, color: "#5A6878", textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 4 }}>{s.label}</div>
            <div style={{ fontFamily: "monospace", fontSize: 20, fontWeight: 700, color: s.val > 0 || s.label === "Top Risk" ? s.color : "#3A4D5C" }}>{s.val}</div>
            <div style={{ fontFamily: "monospace", fontSize: 10, color: "#3A4D5C", marginTop: 3 }}>{s.desc}</div>
          </div>
        ))}
      </div>

      {/* Leaderboard */}
      <div style={{ background: "#0A1520", border: "1px solid #1A2530", borderRadius: 2, padding: "20px 0" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "0 20px 16px" }}>
          <div style={{ fontFamily: "monospace", fontSize: 12, color: "#8A9BAC", letterSpacing: "0.1em" }}>
            COMPOSITE SOVEREIGN STRESS LEADERBOARD
            <span style={{ marginLeft: 10, fontSize: 10, color: "#3A4D5C" }}>click country to open full detail view</span>
          </div>
          <div style={{ display: "flex", gap: 6 }}>
            {[["all","ALL"],["elevated","ELEVATED+"],["stressed","STRESSED+"],["crisis","CRISIS"]].map(([v,l]) => (
              <button key={v} onClick={() => setView(v)} style={{ background: view === v ? "#1A2530" : "transparent", border: `1px solid ${view === v ? "#5A6878" : "#1E2D3D"}`, color: view === v ? "#C8A96E" : "#3A4D5C", borderRadius: 2, padding: "4px 10px", cursor: "pointer", fontFamily: "monospace", fontSize: 11 }}>{l}</button>
            ))}
          </div>
        </div>

        {displayData.length === 0 ? (
          <div style={{ padding: "40px 20px", fontFamily: "monospace", fontSize: 13, color: "#3A4D5C", textAlign: "center" }}>no countries in this tier</div>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr>
                  {["Country", "Tier", "T-Bill MoM", "Consec", "Gold t", "M2 YoY", "T", "G", "M", "Spread","Mult", "Score", "Active Signals"].map(h => (
                    <th key={h} style={{ fontFamily: "monospace", fontSize: 10, color: "#3A4D5C", textTransform: "uppercase", padding: "6px 8px", textAlign: h === "Country" || h === "Active Signals" ? "left" : "right", borderBottom: "1px solid #1A2530", whiteSpace: "nowrap" }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {displayData.map(c => {
                  const tc = TIER_COLORS[c.tier] || "#5A6878";
                  return (
                    <tr key={c.country_iso}
                      onClick={() => onCountrySelect(c.country_iso)}
                      style={{ borderBottom: "1px solid #0F1923", cursor: "pointer" }}
                      onMouseEnter={e => e.currentTarget.style.background = "#0D1820"}
                      onMouseLeave={e => e.currentTarget.style.background = "transparent"}>
                      <td style={{ padding: "7px 8px", fontFamily: "monospace", fontSize: 12, color: "#E8E0D0", whiteSpace: "nowrap" }}>
                        {c.country_name}<span style={{ marginLeft: 5, fontSize: 10, color: "#3A4D5C" }}>{c.country_iso}</span>
                      </td>
                      <td style={{ padding: "7px 8px" }}>
                        <span style={{ fontFamily: "monospace", fontSize: 10, color: tc, background: `${tc}18`, border: `1px solid ${tc}44`, borderRadius: 2, padding: "1px 5px" }}>{c.tier}</span>
                      </td>
                      <td style={{ padding: "7px 8px", fontFamily: "monospace", fontSize: 11, textAlign: "right", color: c.tic_mom_pct < 0 ? "#E07B5A" : "#5DB87A" }}>
                        {c.tic_mom_pct > 0 ? "+" : ""}{c.tic_mom_pct.toFixed(1)}%
                      </td>
                      <td style={{ padding: "7px 8px", fontFamily: "monospace", fontSize: 11, textAlign: "right", color: c.tic_consecutive_months >= 3 ? "#E07B5A" : "#8A9BAC" }}>
                        {c.tic_consecutive_months > 0 ? `${c.tic_consecutive_months}mo` : "—"}
                      </td>
                      <td style={{ padding: "7px 8px", fontFamily: "monospace", fontSize: 11, textAlign: "right", color: c.selling_gold ? "#E07B5A" : "#5A6878" }}>
                        {c.gold_tonnes != null ? `${c.gold_tonnes.toLocaleString()}` : "—"}
                      </td>
                      <td style={{ padding: "7px 8px", fontFamily: "monospace", fontSize: 11, textAlign: "right", color: c.m2_growth_pct == null ? "#3A4D5C" : c.m2_growth_pct > 30 ? "#E07B5A" : c.m2_growth_pct > 15 ? "#E8C547" : "#5DB87A" }}>
                        {c.m2_growth_pct != null ? `${c.m2_growth_pct.toFixed(1)}% '${String(c.m2_year).slice(2)}` : "—"}
                      </td>
                      <td style={{ padding: "7px 8px", fontFamily: "monospace", fontSize: 11, textAlign: "right", color: "#C8A96E" }}>{c.tic_score}</td>
                      <td style={{ padding: "7px 8px", fontFamily: "monospace", fontSize: 11, textAlign: "right", color: "#E8C547" }}>{c.gold_score}</td>
                      <td style={{ padding: "7px 8px", fontFamily: "monospace", fontSize: 11, textAlign: "right", color: "#9B8EC4" }}>{c.monetary_score}</td>
                      <td style={{ padding: "7px 8px", fontFamily: "monospace", fontSize: 11, textAlign: "right", color: "#9B8EC4" }}>{c.monetary_score}</td>
                      <td style={{ padding: "7px 8px", fontFamily: "monospace", fontSize: 11, textAlign: "right", color: c.spread_score > 0 ? "#7EB8C9" : "#3A4D5C" }}>
                          {c.spread_bps != null ? `${c.spread_bps > 0 ? "+" : ""}${c.spread_bps.toFixed(0)}` : "—"}
</td>
                      <td style={{ padding: "7px 8px", fontFamily: "monospace", fontSize: 11, textAlign: "right", color: c.multiplier > 1 ? "#FF4444" : "#3A4D5C" }}>
                        {c.multiplier > 1 ? `${c.multiplier}×` : "—"}
                      </td>
                      <td style={{ padding: "7px 8px", minWidth: 120 }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                          <div style={{ flex: 1, background: "#0F1923", borderRadius: 2, height: 5, overflow: "hidden" }}>
                            <div style={{ width: `${Math.min(100, c.composite_score)}%`, background: tc, height: "100%", borderRadius: 2 }} />
                          </div>
                          <span style={{ fontFamily: "monospace", fontSize: 11, color: tc, minWidth: 28, textAlign: "right", fontWeight: 700 }}>{c.composite_score.toFixed(0)}</span>
                        </div>
                      </td>
                      <td style={{ padding: "7px 8px", fontFamily: "monospace", fontSize: 11, color: "#5A6878", maxWidth: 240 }}>
                        {c.active_signals.join(" · ") || "—"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
      <div style={{ marginTop: 12, fontFamily: "monospace", fontSize: 11, color: "#1E2D3D" }}>
        Data as of {data.as_of} · Sources: US Treasury TIC · World Gold Council · World Bank/IMF IFS
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
        { name: "FRED Data", endpoint: "/fetch/fred", desc: "Fetch 9 FRED metrics (yields, oil, dollar, CPI, M2). Runs daily at 2am.", schedule: "Daily 2:00am" },
        { name: "TIC Holdings", endpoint: "/fetch/tic", desc: "Fetch Treasury holdings from ticdata.treasury.gov. 48 countries, monthly.", schedule: "15th of month, 3:00am" },
        { name: "Gold Reserves", endpoint: "/fetch/gold", desc: "Import WGC gold reserves CSV from C:\\projects\\sentinel\\data\\gold_reserves.csv.", schedule: "Manual — re-download CSV monthly" },
      ]
    },
    {
      group: "Manual (CSV import)",
      items: [
        { name: "Spot Gold Price", endpoint: "/fetch/gold-price", desc: "Import WGC spot gold history from C:\\projects\\sentinel\\data\\gold_prices.csv.", schedule: "Manual — re-download CSV quarterly" },
        { name: "Broad Money Growth", endpoint: "/fetch/money-supply", desc: "Import World Bank broad money growth JSON from C:\\projects\\sentinel\\data\\money_supply.json.", schedule: "Manual — re-download JSON annually" },
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
                      onClick={() => runPipeline(p.name, p.endpoint)}
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
          { task: "Download WGC gold reserves CSV", url: "https://www.gold.org/goldhub/data/gold-reserves-by-country", action: "Save as C:\\projects\\sentinel\\data\\gold_reserves.csv → run POST /api/fetch/gold" },
          { task: "Trigger TIC data refresh (if not on scheduler)", url: null, action: "POST /api/fetch/tic  — or wait for auto-run on 15th" },
          { task: "Trigger FRED refresh (if not on scheduler)", url: null, action: "POST /api/fetch/fred — or wait for auto-run at 2am" },
          { task: "Update spot gold price CSV (quarterly)", url: "https://www.gold.org/goldhub/data/gold-prices", action: "Save as C:\\projects\\sentinel\\data\\gold_prices.csv → run POST /api/fetch/gold-price" },
          { task: "Refresh broad money growth JSON (annually)", url: null, action: 'curl "https://api.worldbank.org/v2/country/JP;CN;GB;...all codes.../indicator/FM.LBL.BMNY.ZG?format=json&mrv=30&per_page=2000" -o data\\money_supply.json → POST /api/fetch/money-supply' },
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
