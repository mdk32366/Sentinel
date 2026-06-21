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

const TABS = ["MARKETS", "HOLDINGS"];

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

// ── Holdings Tab Components ────────────────────────────────────────────────

function AlertBanner({ message, color = "#E07B5A" }) {
  return (
    <div style={{ background: `${color}15`, border: `1px solid ${color}44`, borderLeft: `3px solid ${color}`, borderRadius: 2, padding: "10px 16px", marginBottom: 12, fontFamily: "monospace", fontSize: 12, color }}>
      ⚠ {message}
    </div>
  );
}

function StressBar({ score }) {
  const w = Math.min(100, score);
  const color = scoreColor(score);
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <div style={{ flex: 1, background: "#0F1923", borderRadius: 2, height: 6, overflow: "hidden" }}>
        <div style={{ width: `${w}%`, background: color, height: "100%", borderRadius: 2, transition: "width 0.3s" }} />
      </div>
      <span style={{ fontFamily: "monospace", fontSize: 11, color, minWidth: 28, textAlign: "right" }}>{score.toFixed(0)}</span>
    </div>
  );
}

function StressTable({ countries, onSelect, selected }) {
  const [sort, setSort] = useState("stress_score");

  const sorted = [...countries].sort((a, b) => {
    if (sort === "stress_score") return b.stress_score - a.stress_score;
    if (sort === "mom") return (a.mom_change_pct ?? 0) - (b.mom_change_pct ?? 0);
    if (sort === "consecutive") return b.consecutive_declining_months - a.consecutive_declining_months;
    if (sort === "holdings") return b.latest_holdings_bn - a.latest_holdings_bn;
    return 0;
  });

  const col = (label, key, title) => (
    <th onClick={() => setSort(key)} title={title} style={{
      fontFamily: "monospace", fontSize: 10, letterSpacing: "0.1em", color: sort === key ? "#C8A96E" : "#3A4D5C",
      textTransform: "uppercase", padding: "8px 12px", textAlign: "right", cursor: "pointer",
      borderBottom: "1px solid #1A2530", whiteSpace: "nowrap",
    }}>{label} {sort === key ? "↓" : ""}</th>
  );

  return (
    <div style={{ overflowX: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr>
            <th style={{ fontFamily: "monospace", fontSize: 10, letterSpacing: "0.1em", color: "#3A4D5C", textTransform: "uppercase", padding: "8px 12px", textAlign: "left", borderBottom: "1px solid #1A2530" }}>Country</th>
            <th style={{ fontFamily: "monospace", fontSize: 10, color: "#3A4D5C", textTransform: "uppercase", padding: "8px 12px", textAlign: "left", borderBottom: "1px solid #1A2530" }}>Region</th>
            {col("Holdings $B", "holdings", "Latest holdings in billions USD")}
            {col("MoM %", "mom", "Month-over-month change")}
            {col("Consec ↓", "consecutive", "Consecutive declining months")}
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
                onMouseLeave={e => e.currentTarget.style.background = isSelected ? "#0F1923" : "transparent"}
              >
                <td style={{ padding: "10px 12px", fontFamily: "monospace", fontSize: 13, color: "#E8E0D0" }}>
                  {c.alert && <span style={{ color: alertColor, marginRight: 6 }}>●</span>}
                  {c.country_name}
                  <span style={{ marginLeft: 6, fontSize: 10, color: "#3A4D5C" }}>{c.country_iso}</span>
                </td>
                <td style={{ padding: "10px 12px", fontFamily: "monospace", fontSize: 11, color: "#5A6878" }}>{c.region}</td>
                <td style={{ padding: "10px 12px", fontFamily: "monospace", fontSize: 13, color: "#8A9BAC", textAlign: "right" }}>
                  {c.latest_holdings_bn != null ? `$${c.latest_holdings_bn.toFixed(1)}B` : "—"}
                </td>
                <td style={{ padding: "10px 12px", fontFamily: "monospace", fontSize: 13, textAlign: "right", color: c.mom_change_pct == null ? "#3A4D5C" : c.mom_change_pct < 0 ? "#E07B5A" : "#5DB87A" }}>
                  {c.mom_change_pct != null ? `${c.mom_change_pct > 0 ? "+" : ""}${c.mom_change_pct.toFixed(2)}%` : "—"}
                </td>
                <td style={{ padding: "10px 12px", fontFamily: "monospace", fontSize: 13, textAlign: "right", color: c.consecutive_declining_months >= 3 ? "#E07B5A" : "#8A9BAC" }}>
                  {c.consecutive_declining_months > 0 ? `${c.consecutive_declining_months}mo` : "—"}
                </td>
                <td style={{ padding: "10px 12px", minWidth: 140 }}>
                  <StressBar score={c.stress_score} />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function CountryDetail({ iso, onClose }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    fetch(`${API}/holdings/country/${iso}`)
      .then(r => r.json())
      .then(d => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, [iso]);

  if (loading) return <div style={{ padding: 24, fontFamily: "monospace", fontSize: 13, color: "#3A4D5C" }}>loading...</div>;
  if (!data) return null;

  const chartData = data.history.map(h => ({
    date: h.date,
    holdings: h.holdings_bn,
    mom: h.mom_change_pct,
  }));

  return (
    <div style={{ background: "#0A1520", border: "1px solid #1A2530", borderRadius: 2, padding: 24, marginTop: 12 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 20 }}>
        <div>
          <div style={{ fontFamily: "monospace", fontSize: 16, color: "#E8E0D0", fontWeight: 700 }}>
            {data.country.name}
            <span style={{ marginLeft: 10, fontSize: 11, color: "#3A4D5C" }}>{data.country.iso} · {data.country.region}</span>
          </div>
          <div style={{ display: "flex", gap: 24, marginTop: 12 }}>
            {[
              { label: "Latest", val: data.summary.latest_holdings_bn != null ? `$${data.summary.latest_holdings_bn.toFixed(1)}B` : "—" },
              { label: "Peak", val: data.summary.peak_holdings_bn != null ? `$${data.summary.peak_holdings_bn.toFixed(1)}B` : "—" },
              { label: "Declining months", val: `${data.summary.declining_months_in_period} / ${data.history.length}` },
              { label: "% of months", val: data.summary.pct_of_months_declining != null ? `${data.summary.pct_of_months_declining}%` : "—" },
            ].map(s => (
              <div key={s.label}>
                <div style={{ fontFamily: "monospace", fontSize: 10, color: "#3A4D5C", letterSpacing: "0.1em", textTransform: "uppercase" }}>{s.label}</div>
                <div style={{ fontFamily: "monospace", fontSize: 15, color: "#E8E0D0", marginTop: 2 }}>{s.val}</div>
              </div>
            ))}
          </div>
        </div>
        <button onClick={onClose} style={{ background: "transparent", border: "1px solid #1E2D3D", color: "#5A6878", borderRadius: 2, padding: "4px 10px", cursor: "pointer", fontFamily: "monospace", fontSize: 12 }}>✕ close</button>
      </div>

      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={chartData} margin={{ top: 4, right: 8, bottom: 4, left: 8 }}>
          <CartesianGrid strokeDasharray="2 6" stroke="#0F1923" vertical={false} />
          <XAxis dataKey="date" tick={{ fill: "#3A4D5C", fontFamily: "monospace", fontSize: 10 }} axisLine={false} tickLine={false} minTickGap={40} />
          <YAxis tick={{ fill: "#3A4D5C", fontFamily: "monospace", fontSize: 10 }} axisLine={false} tickLine={false} width={48} tickFormatter={v => `$${v}B`} />
          <Tooltip
            formatter={(val) => [`$${val?.toFixed(1)}B`, "Holdings"]}
            contentStyle={{ background: "#0A1520", border: "1px solid #1E2D3D", borderRadius: 2, fontFamily: "monospace", fontSize: 12 }}
            labelStyle={{ color: "#5A6878" }}
          />
          <Bar dataKey="holdings" radius={[2, 2, 0, 0]}>
            {chartData.map((entry, i) => (
              <Cell key={i} fill={entry.mom != null && entry.mom < 0 ? "#E07B5A" : "#5DB87A"} fillOpacity={0.7} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>

      <div style={{ marginTop: 16, overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr>
              {["Date", "Holdings $B", "MoM Change", "Trend"].map(h => (
                <th key={h} style={{ fontFamily: "monospace", fontSize: 10, color: "#3A4D5C", textTransform: "uppercase", padding: "6px 10px", textAlign: h === "Date" ? "left" : "right", borderBottom: "1px solid #1A2530" }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {[...data.history].reverse().slice(0, 24).map((row, i) => (
              <tr key={i} style={{ borderBottom: "1px solid #080E14" }}>
                <td style={{ padding: "6px 10px", fontFamily: "monospace", fontSize: 12, color: "#8A9BAC" }}>{row.date}</td>
                <td style={{ padding: "6px 10px", fontFamily: "monospace", fontSize: 12, color: "#E8E0D0", textAlign: "right" }}>${row.holdings_bn.toFixed(1)}B</td>
                <td style={{ padding: "6px 10px", fontFamily: "monospace", fontSize: 12, textAlign: "right", color: row.mom_change_pct == null ? "#3A4D5C" : row.mom_change_pct < 0 ? "#E07B5A" : "#5DB87A" }}>
                  {row.mom_change_pct != null ? `${row.mom_change_pct > 0 ? "+" : ""}${row.mom_change_pct.toFixed(2)}%` : "—"}
                </td>
                <td style={{ padding: "6px 10px", textAlign: "right" }}>
                  {row.mom_change_pct != null && (
                    <span style={{ fontFamily: "monospace", fontSize: 14, color: row.mom_change_pct < 0 ? "#E07B5A" : "#5DB87A" }}>
                      {row.mom_change_pct < 0 ? "▼" : "▲"}
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function HoldingsTab() {
  const [summary, setSummary] = useState(null);
  const [stress, setStress] = useState(null);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState(null);
  const [view, setView] = useState("stress"); // "stress" | "all"

  useEffect(() => {
    Promise.all([
      fetch(`${API}/holdings/summary`).then(r => r.json()),
      fetch(`${API}/holdings/stress`).then(r => r.json()),
    ]).then(([s, st]) => {
      setSummary(s);
      setStress(st);
      setLoading(false);
    }).catch(() => setLoading(false));
  }, []);

  if (loading) return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: 300, fontFamily: "monospace", fontSize: 13, color: "#3A4D5C" }}>
      loading holdings data...
    </div>
  );

  if (!summary || summary.error) return (
    <div style={{ fontFamily: "monospace", fontSize: 13, color: "#E07B5A", padding: 24 }}>
      No TIC data loaded. Go to <a href="http://localhost:8000/docs" style={{ color: "#C8A96E" }}>API docs</a> and run POST /api/fetch/tic
    </div>
  );

  const allCountries = summary.top_holders ? [
    ...summary.most_stressed,
    ...summary.top_holders.filter(c => !summary.most_stressed.find(s => s.iso === c.iso))
  ].map(c => ({
    country_iso: c.iso,
    country_name: c.name,
    region: c.region,
    latest_holdings_bn: c.holdings_bn,
    mom_change_pct: c.mom_change_pct,
    consecutive_declining_months: c.consecutive_declining ?? 0,
    stress_score: c.stress_score ?? 0,
    alert: c.alert ?? false,
  })) : [];

  const stressCountries = stress ? [
    ...(stress.alerts || []),
    ...(stress.watch_list || []),
  ] : [];

  const displayCountries = view === "stress" ? stressCountries : allCountries;
  const noBuyers = summary.biggest_buyers?.length === 0;
  const alertCount = stress?.alerts?.length ?? 0;

  return (
    <div>
      {/* Summary bar */}
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

      {/* Alert banners */}
      {noBuyers && <AlertBanner message={`No net buyers in ${summary.as_of} — all tracked countries were reducing or flat. Broad-based demand weakness.`} color="#E07B5A" />}
      {alertCount >= 5 && <AlertBanner message={`${alertCount} countries on active stress alert — elevated systemic risk signal.`} color="#E8C547" />}

      {/* Top holders quick view */}
      <div style={{ display: "flex", gap: 8, marginBottom: 20, flexWrap: "wrap" }}>
        {(summary.top_holders || []).slice(0, 8).map(c => (
          <div key={c.iso} onClick={() => setSelected(selected?.country_iso === c.iso ? null : { country_iso: c.iso, ...c })}
            style={{ background: "#0A1520", border: `1px solid ${c.alert ? "#E07B5A44" : "#1A2530"}`, borderRadius: 2, padding: "8px 14px", cursor: "pointer", flex: "1 1 120px", maxWidth: 160 }}>
            <div style={{ fontFamily: "monospace", fontSize: 10, color: "#5A6878" }}>{c.iso}</div>
            <div style={{ fontFamily: "monospace", fontSize: 13, color: "#E8E0D0", marginTop: 2 }}>${c.holdings_bn?.toFixed(0)}B</div>
            <div style={{ fontFamily: "monospace", fontSize: 11, color: c.mom_change_pct == null ? "#3A4D5C" : c.mom_change_pct < 0 ? "#E07B5A" : "#5DB87A", marginTop: 2 }}>
              {c.mom_change_pct != null ? `${c.mom_change_pct > 0 ? "+" : ""}${c.mom_change_pct.toFixed(1)}%` : "—"}
            </div>
          </div>
        ))}
      </div>

      {/* Country detail */}
      {selected && <CountryDetail iso={selected.country_iso ?? selected.iso} onClose={() => setSelected(null)} />}

      {/* Stress table */}
      <div style={{ background: "#0A1520", border: "1px solid #1A2530", borderRadius: 2, padding: "20px 0" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "0 20px 16px" }}>
          <div style={{ fontFamily: "monospace", fontSize: 12, color: "#8A9BAC", letterSpacing: "0.1em" }}>
            SOVEREIGN STRESS LEADERBOARD
            <span style={{ marginLeft: 10, fontSize: 10, color: "#3A4D5C" }}>click row to expand history</span>
          </div>
          <div style={{ display: "flex", gap: 6 }}>
            {[["stress", "STRESSED"], ["all", "ALL"]].map(([v, l]) => (
              <button key={v} onClick={() => setView(v)} style={{
                background: view === v ? "#1A2530" : "transparent",
                border: `1px solid ${view === v ? "#5A6878" : "#1E2D3D"}`,
                color: view === v ? "#C8A96E" : "#3A4D5C",
                borderRadius: 2, padding: "4px 10px", cursor: "pointer", fontFamily: "monospace", fontSize: 11,
              }}>{l}</button>
            ))}
          </div>
        </div>
        {displayCountries.length === 0 ? (
          <div style={{ padding: "40px 20px", fontFamily: "monospace", fontSize: 13, color: "#3A4D5C", textAlign: "center" }}>no countries in this view</div>
        ) : (
          <StressTable countries={displayCountries} onSelect={setSelected} selected={selected} />
        )}
      </div>

      <div style={{ marginTop: 12, fontFamily: "monospace", fontSize: 11, color: "#1E2D3D" }}>
        Source: US Treasury TIC data · Published ~45 days after month-end · Data as of {summary.as_of}
      </div>
    </div>
  );
}

// ── Main App ───────────────────────────────────────────────────────────────

export default function App() {
  const [tab, setTab] = useState("MARKETS");
  const [activeMetrics, setActiveMetrics] = useState(["DGS10", "DGS2", "FEDFUNDS", "DCOILWTICO"]);
  const [range, setRange] = useState(RANGES[1]);
  const [chartData, setChartData] = useState([]);
  const [latestAll, setLatestAll] = useState({});
  const [stats, setStats] = useState(null);
  const [health, setHealth] = useState(null);
  const [loading, setLoading] = useState(false);
  const [normalized, setNormalized] = useState(false);

  useEffect(() => {
    const allCodes = METRICS.map(m => m.code).join(",");
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
        METRICS.forEach(({ code }) => {
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
          activeMetrics.forEach(m => {
            if (r[m] != null && base[m]) nr[m] = ((r[m] - base[m]) / base[m]) * 100;
          });
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

      {/* Tab nav */}
      <div style={{ borderBottom: "1px solid #1A2530", padding: "0 32px", display: "flex", gap: 0 }}>
        {TABS.map(t => (
          <button key={t} onClick={() => setTab(t)} style={{
            background: "transparent", border: "none",
            borderBottom: `2px solid ${tab === t ? "#C8A96E" : "transparent"}`,
            color: tab === t ? "#C8A96E" : "#3A4D5C",
            padding: "12px 20px", cursor: "pointer",
            fontFamily: "monospace", fontSize: 12, letterSpacing: "0.1em",
            marginBottom: -1,
          }}>{t}</button>
        ))}
      </div>

      <div style={{ padding: "28px 32px", maxWidth: 1400, margin: "0 auto" }}>

        {tab === "MARKETS" && (
          <>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 12, marginBottom: 28 }}>
              {METRICS.map(m => (
                <StatCard key={m.code} label={m.label} value={latest[m.code]} unit={m.unit} change={getChange(m.code, m.unit)} color={m.color} />
              ))}
            </div>

            <div style={{ background: "#0A1520", border: "1px solid #1A2530", borderRadius: 2, padding: "24px 28px" }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 24, flexWrap: "wrap", gap: 12 }}>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  {METRICS.map(m => {
                    const on = activeMetrics.includes(m.code);
                    return (
                      <button key={m.code} onClick={() => setActiveMetrics(prev => prev.includes(m.code) ? prev.filter(c => c !== m.code) : [...prev, m.code])} style={{
                        background: on ? `${m.color}18` : "transparent", border: `1px solid ${on ? m.color : "#1E2D3D"}`,
                        color: on ? m.color : "#3A4D5C", borderRadius: 2, padding: "5px 12px",
                        cursor: "pointer", fontFamily: "monospace", fontSize: 12, letterSpacing: "0.05em", transition: "all 0.15s",
                      }}>{m.label}</button>
                    );
                  })}
                </div>
                <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                  <button onClick={() => setNormalized(p => !p)} style={{
                    background: normalized ? "#1A2530" : "transparent", border: `1px solid ${normalized ? "#5A6878" : "#1E2D3D"}`,
                    color: normalized ? "#8A9BAC" : "#3A4D5C", borderRadius: 2, padding: "5px 12px",
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
                  { label: "5Y–2Y",  val: latest["DGS5"] != null ? latest["DGS5"] - latest["DGS2"] : null },
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

            <div style={{ marginTop: 24, display: "flex", justifyContent: "space-between" }}>
              <span style={{ fontFamily: "monospace", fontSize: 11, color: "#1E2D3D" }}>Source: FRED / Federal Reserve Bank of St. Louis</span>
              {stats?.data_latest && <span style={{ fontFamily: "monospace", fontSize: 11, color: "#1E2D3D" }}>Last data point: {formatDate(stats.data_latest)}</span>}
            </div>
          </>
        )}

        {tab === "HOLDINGS" && <HoldingsTab />}

      </div>
    </div>
  );
}
