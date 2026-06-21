import { useState, useEffect, useCallback } from "react";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, ReferenceLine } from "recharts";

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

function StatCard({ label, value, unit, change, color }) {
  const up = change >= 0;
  return (
    <div style={{
      background: "#0F1923",
      border: `1px solid ${color}33`,
      borderTop: `2px solid ${color}`,
      borderRadius: 2,
      padding: "18px 22px",
      minWidth: 0,
    }}>
      <div style={{ fontSize: 11, letterSpacing: "0.12em", color: "#5A6878", textTransform: "uppercase", marginBottom: 8, fontFamily: "monospace" }}>
        {label}
      </div>
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
      <div style={{
        display: "flex", gap: 48, whiteSpace: "nowrap",
        animation: "ticker 40s linear infinite",
        width: "max-content",
      }}>
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
    <div style={{
      background: "#0A1520", border: "1px solid #1E2D3D", borderRadius: 2,
      padding: "10px 14px", fontFamily: "monospace", fontSize: 12,
    }}>
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

export default function App() {
  const [activeMetrics, setActiveMetrics] = useState(["DGS10", "DGS2", "FEDFUNDS", "DCOILWTICO"]);
  const [range, setRange] = useState(RANGES[1]);
  const [chartData, setChartData] = useState([]);
  const [latestAll, setLatestAll] = useState({});
  const [stats, setStats] = useState(null);
  const [health, setHealth] = useState(null);
  const [loading, setLoading] = useState(false);
  const [normalized, setNormalized] = useState(false);

  // Fetch all metrics for stat cards (independent of chart selection)
  useEffect(() => {
    const allCodes = METRICS.map(m => m.code).join(",");
    const end = new Date();
    const start = new Date();
    start.setDate(start.getDate() - 120); // just need ~45 days for latest + 30d change
    const url = `${API}/timeseries?metric_codes=${allCodes}&start_date=${start.toISOString()}&end_date=${end.toISOString()}`;
    fetch(url)
      .then(r => r.json())
      .then(raw => {
        const byDate = {};
        raw.forEach(({ date, value, metric_code }) => {
          const d = date.split("T")[0];
          if (!byDate[d]) byDate[d] = { date: d };
          byDate[d][metric_code] = value;
        });
const rows = Object.values(byDate).sort((a, b) => a.date.localeCompare(b.date));
        // Find last non-null value per metric independently
        const latest = {};
        const month30 = {};
        METRICS.forEach(({ code }) => {
          const withVal = rows.filter(r => r[code] != null);
          if (withVal.length) latest[code] = withVal[withVal.length - 1][code];
          if (withVal.length > 1) month30[code] = withVal[Math.max(0, withVal.length - 2)][code];
        });
        setLatestAll({ latest, month30, rows });
      })
      .catch(() => {});
  }, []);

  const fetchChartData = useCallback(async () => {
    if (!activeMetrics.length) return;
    setLoading(true);
    try {
      const end = new Date();
      const start = new Date();
      start.setDate(start.getDate() - range.days);
      const codes = activeMetrics.join(",");
      const url = `${API}/timeseries?metric_codes=${codes}&start_date=${start.toISOString()}&end_date=${end.toISOString()}`;
      const res = await fetch(url);
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
          activeMetrics.forEach(m => {
            if (r[m] != null && base[m]) nr[m] = ((r[m] - base[m]) / base[m]) * 100;
          });
          return nr;
        });
      }
      setChartData(rows);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, [activeMetrics, range, normalized]);

  useEffect(() => { fetchChartData(); }, [fetchChartData]);

  useEffect(() => {
    fetch(`${API}/stats`).then(r => r.json()).then(setStats).catch(() => {});
    fetch(`${API}/health`).then(r => r.json()).then(setHealth).catch(() => {});
  }, []);

  const toggleMetric = (code) => {
    setActiveMetrics(prev =>
      prev.includes(code) ? prev.filter(c => c !== code) : [...prev, code]
    );
  };

  const { latest = {}, month30 } = latestAll;

  const getChange = (code, unit) => {
    if (!month30 || latest[code] == null || month30[code] == null) return null;
    if (unit === "%" || unit === "") return latest[code] - month30[code];
    return ((latest[code] - month30[code]) / month30[code]) * 100;
  };

  // Ticker uses all latest values
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

      <div style={{ padding: "28px 32px", maxWidth: 1400, margin: "0 auto" }}>

        {/* Stat Cards — always show all metrics */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 12, marginBottom: 28 }}>
          {METRICS.map(m => (
            <StatCard
              key={m.code}
              label={m.label}
              value={latest[m.code]}
              unit={m.unit}
              change={getChange(m.code, m.unit)}
              color={m.color}
            />
          ))}
        </div>

        {/* Chart Panel */}
        <div style={{ background: "#0A1520", border: "1px solid #1A2530", borderRadius: 2, padding: "24px 28px" }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 24, flexWrap: "wrap", gap: 12 }}>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              {METRICS.map(m => {
                const on = activeMetrics.includes(m.code);
                return (
                  <button key={m.code} onClick={() => toggleMetric(m.code)} style={{
                    background: on ? `${m.color}18` : "transparent",
                    border: `1px solid ${on ? m.color : "#1E2D3D"}`,
                    color: on ? m.color : "#3A4D5C",
                    borderRadius: 2, padding: "5px 12px",
                    cursor: "pointer", fontFamily: "monospace", fontSize: 12,
                    letterSpacing: "0.05em", transition: "all 0.15s",
                  }}>
                    {m.label}
                  </button>
                );
              })}
            </div>
            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <button onClick={() => setNormalized(p => !p)} style={{
                background: normalized ? "#1A2530" : "transparent",
                border: `1px solid ${normalized ? "#5A6878" : "#1E2D3D"}`,
                color: normalized ? "#8A9BAC" : "#3A4D5C",
                borderRadius: 2, padding: "5px 12px",
                cursor: "pointer", fontFamily: "monospace", fontSize: 11,
              }}>% CHANGE</button>
              <div style={{ display: "flex", border: "1px solid #1E2D3D", borderRadius: 2, overflow: "hidden" }}>
                {RANGES.map(r => (
                  <button key={r.label} onClick={() => setRange(r)} style={{
                    background: range.label === r.label ? "#1A2530" : "transparent",
                    border: "none", borderLeft: "1px solid #1E2D3D",
                    color: range.label === r.label ? "#C8A96E" : "#3A4D5C",
                    padding: "5px 12px", cursor: "pointer", fontFamily: "monospace", fontSize: 12,
                  }}>{r.label}</button>
                ))}
              </div>
            </div>
          </div>

          {loading ? (
            <div style={{ height: 380, display: "flex", alignItems: "center", justifyContent: "center", color: "#2A3540", fontFamily: "monospace", fontSize: 13 }}>fetching data...</div>
          ) : chartData.length === 0 ? (
            <div style={{ height: 380, display: "flex", alignItems: "center", justifyContent: "center", color: "#2A3540", fontFamily: "monospace", fontSize: 13 }}>no data — select a metric above</div>
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

        {/* Spread bar */}
        {!normalized && latest["DGS10"] != null && latest["DGS2"] != null && (
          <div style={{ marginTop: 12, background: "#0A1520", border: "1px solid #1A2530", borderRadius: 2, padding: "14px 28px", display: "flex", gap: 32, alignItems: "center", flexWrap: "wrap" }}>
            <span style={{ fontFamily: "monospace", fontSize: 11, color: "#3A4D5C", letterSpacing: "0.1em" }}>SPREAD</span>
            {[
              { label: "10Y–2Y", val: latest["DGS10"] - latest["DGS2"] },
              { label: "10Y–5Y", val: latest["DGS10"] != null && latest["DGS5"] != null ? latest["DGS10"] - latest["DGS5"] : null },
              { label: "5Y–2Y",  val: latest["DGS5"]  != null && latest["DGS2"] != null ? latest["DGS5"]  - latest["DGS2"] : null },
              { label: "10Y–FF", val: latest["FEDFUNDS"] != null ? latest["DGS10"] - latest["FEDFUNDS"] : null },
            ].filter(s => s.val != null).map(s => (
              <div key={s.label} style={{ fontFamily: "monospace" }}>
                <span style={{ fontSize: 11, color: "#3A4D5C", marginRight: 8 }}>{s.label}</span>
                <span style={{ fontSize: 15, color: s.val < 0 ? "#E07B5A" : "#5DB87A", fontWeight: 600 }}>
                  {s.val > 0 ? "+" : ""}{s.val.toFixed(2)}pp
                </span>
                {s.label === "10Y–2Y" && s.val < 0 && <span style={{ marginLeft: 8, fontSize: 10, color: "#E07B5A88" }}>INVERTED</span>}
              </div>
            ))}
          </div>
        )}

        <div style={{ marginTop: 24, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <span style={{ fontFamily: "monospace", fontSize: 11, color: "#1E2D3D" }}>Source: FRED / Federal Reserve Bank of St. Louis</span>
          {stats?.data_latest && <span style={{ fontFamily: "monospace", fontSize: 11, color: "#1E2D3D" }}>Last data point: {formatDate(stats.data_latest)}</span>}
        </div>
      </div>
    </div>
  );
}
