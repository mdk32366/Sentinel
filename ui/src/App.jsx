import { useState } from "react";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, ReferenceLine } from "recharts";

import { METRICS, RANGES, TABS } from "./lib/constants";
import { formatDate } from "./lib/format";
import { changeBetween, changeSuffix, changeWindowLabel } from "./lib/series";
// ORDER-03 Part F step 4: App owns which tab is open and what is selected.
// Everything that talks to the API lives in a hook (F-0063).
import { useApiResource } from "./hooks/useApiResource";
import { useChartSeries } from "./hooks/useChartSeries";
import { useMarketSeries } from "./hooks/useMarketSeries";
import { CustomTooltip } from "./components/CustomTooltip";
import { StatCard } from "./components/StatCard";
import { Ticker } from "./components/Ticker";
import { AboutTab } from "./pages/AboutTab";
import { AdminTab } from "./pages/AdminTab";
import { CDSTab } from "./pages/CDSTab";
import { CompositeTab } from "./pages/CompositeTab";
import { CountryTab } from "./pages/CountryTab";
import { CrossAssetTab } from "./pages/CrossAssetTab";
import { GoldReservesTab } from "./pages/GoldReservesTab";
import { HoldingsTab } from "./pages/HoldingsTab";



export default function App() {
  const [tab, setTab] = useState("MARKETS");
  const [countryIso, setCountryIso] = useState(null); // for cross-tab navigation
  const [activeMetrics, setActiveMetrics] = useState(["DGS10", "DGS2", "FEDFUNDS", "DCOILWTICO"]);
  const [range, setRange] = useState(RANGES[1]);
  const [normalized, setNormalized] = useState(false);

  const { latest, prior } = useMarketSeries();
  const { rows: chartData, loading } = useChartSeries({ activeMetrics, range, normalized });
  const { data: stats } = useApiResource(`/stats`);
  const { data: health } = useApiResource(`/health`);

  // Navigate to country tab with a specific country
  const handleCountrySelect = (iso) => {
    setCountryIso(iso);
    setTab("COUNTRY");
  };

  const getChange = (code, unit) => {
    const previous = prior[code];
    if (!previous || latest[code] == null) return null;
    const value = changeBetween(latest[code], previous.value, unit);
    if (value == null) return null;
    return { value, suffix: changeSuffix(unit), window: changeWindowLabel(previous.actualDays) };
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
            <div style={{ display: "grid", gridTemplateColumns: "repeat(6, 1fr)", gap: 12, marginBottom: 28 }}>
              {METRICS.map(m => (
                <StatCard
                  key={m.code}
                  label={m.label}
                  value={latest[m.code]}
                  unit={m.unit}
                  change={getChange(m.code, m.unit)}
                  color={m.color}
                  tip={m.tip}
                  stressRole={m.stressRole}
                  scored={m.scored}
                />
              ))}
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
                    <XAxis dataKey="date" tickFormatter={formatDate} tick={{ fill: "#3A4D5C", fontFamily: "monospace", fontSize: 11 }} axisLine={{ stroke: "#1A2530" }} tickLine={false} minTickGap={60} interval="preserveStartEnd" />
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
                  { label: "30Y–10Y", val: latest["DGS30"] != null ? latest["DGS30"] - latest["DGS10"] : null },
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
        {tab === "GOLD" && <GoldReservesTab onCountrySelect={handleCountrySelect} latestAll={latest} />}
        {tab === "COMPOSITE" && <CompositeTab onCountrySelect={handleCountrySelect} />}
        {tab === "CDS" && <CDSTab onCountrySelect={handleCountrySelect} />}
        {tab === "COUNTRY" && (
          <CountryTab initialIso={countryIso} onIsoChange={setCountryIso} latestAll={latest} />
        )}
        {tab === "ADMIN" && <AdminTab />}
        {tab === "ABOUT" && <AboutTab />}

      </div>
    </div>
  );
}

