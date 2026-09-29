import { useState, useEffect, useCallback } from "react";
// ORDER-03 Part F step 1: one module owns the base URL (F-0052).
import { apiFetch } from "./lib/api";
import { METRICS, RANGES, SOVEREIGN_YIELD_CODES, TABS } from "./lib/constants";
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
import { formatDate } from "./lib/format";
import { seriesByCode, latestByCode, pivotByDate, priorObservation, changeBetween, changeSuffix, changeWindowLabel } from "./lib/series";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, ReferenceLine } from "recharts";



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
    // F-0062: the fourteen sovereign codes are SOVEREIGN_YIELD_CODES. They
    // were inlined here twice, and the constant existed the whole time.
    const allTrackedCodes = [...METRICS.map(m => m.code), ...Object.values(SOVEREIGN_YIELD_CODES)];
    const end = new Date();
    const start = new Date();
    start.setDate(start.getDate() - 120);
    apiFetch(`/timeseries?metric_codes=${allTrackedCodes.join(",")}&start_date=${start.toISOString()}&end_date=${end.toISOString()}`)
      .then(r => r.json())
      .then(raw => {
        const rows = pivotByDate(raw);
        // F-0055: `prior` is the observation ~30 days back BY DATE, and it
        // carries the gap it actually found. This used to be points.at(-2) -
        // the previous row - which on a daily series is yesterday, while the
        // card said "vs 30d".
        const series = seriesByCode(rows, allTrackedCodes);
        const latest = latestByCode(series);
        const prior = {};
        allTrackedCodes.forEach((code) => {
          const found = priorObservation(series[code], 30);
          if (found) prior[code] = found;
        });
        setLatestAll({ latest, prior });
      }).catch(() => {});
  }, []);

  const fetchChartData = useCallback(async () => {
    if (!activeMetrics.length) return;
    setLoading(true);
    try {
      const end = new Date();
      const start = new Date();
      start.setDate(start.getDate() - range.days);
      const res = await apiFetch(`/timeseries?metric_codes=${activeMetrics.join(",")}&start_date=${start.toISOString()}&end_date=${end.toISOString()}`);
      let rows = pivotByDate(await res.json());
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

  // F-0056: fetchChartData is a useCallback over [activeMetrics, range,
  // normalized]; none of its setters touch those, so this cannot loop.
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { fetchChartData(); }, [fetchChartData]);
  useEffect(() => {
    apiFetch(`/stats`).then(r => r.json()).then(setStats).catch(() => {});
    apiFetch(`/health`).then(r => r.json()).then(setHealth).catch(() => {});
  }, []);

  const { latest = {}, prior = {} } = latestAll;
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

        {tab === "HOLDINGS" && <HoldingsTab onCountrySelect={handleCountrySelect} latestAll={latestAll} />}
        {tab === "CROSS-ASSET" && <CrossAssetTab />}
        {tab === "GOLD" && <GoldReservesTab onCountrySelect={handleCountrySelect} />}
        {tab === "COMPOSITE" && <CompositeTab onCountrySelect={handleCountrySelect} />}
        {tab === "CDS" && <CDSTab onCountrySelect={handleCountrySelect} />}
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

