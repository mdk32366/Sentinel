import { useState, useEffect } from "react";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import { apiFetch } from "../lib/api";
import { formatDate, spreadBasisPoints, spreadColor } from "../lib/format";
import { SOVEREIGN_YIELD_CODES, TRESEG_CODES } from "../lib/constants";

export function CountryDetail({ iso, onClose, standalone = false, latestAll = {} }) {
  const [ticHistory, setTicHistory] = useState(null);
  const [goldHistory, setGoldHistory] = useState(null);
  const [reservesHistory, setReservesHistory] = useState(null);
  const [loading, setLoading] = useState(true);
  const [narrative, setNarrative] = useState(null);
  const [narrativeLoading, setNarrativeLoading] = useState(false);
  const [cdsData, setCdsData] = useState({ cds5y: null, cds10y: null, termSpread: null });

  useEffect(() => {
    // F-0056: reset-then-load on a changed `iso`. Costs one extra render;
    // cannot loop, since neither setter feeds this effect's dependency.
    // Restructuring it means reworking effects in a component with no coverage.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLoading(true);
    setNarrative(null);
    const end = new Date();
    const start = new Date();
    start.setFullYear(start.getFullYear() - 3);
    const tresegCode = TRESEG_CODES[iso];
    Promise.all([
      apiFetch(`/holdings/${iso}?start_date=${start.toISOString()}&end_date=${end.toISOString()}`).then(r => r.json()).catch(() => null),
      apiFetch(`/gold-reserves/${iso}`).then(r => r.json()).catch(() => null),
      tresegCode
        ? apiFetch(`/timeseries?metric_codes=${tresegCode}&start_date=${start.toISOString()}&end_date=${end.toISOString()}`).then(r => r.json()).catch(() => null)
        : Promise.resolve(null),
    ]).then(([tic, gold, reserves]) => {
      setTicHistory(tic);
      setGoldHistory(gold);
      setReservesHistory(reserves);
      setLoading(false);
    });

    // Fetch latest CDS for the coverage tile (independent of narrative generation)
    apiFetch(`/cds?country=${iso}`)
      .then(r => r.ok ? r.json() : null)
      .then(d => {
        if (!d) { setCdsData({ cds5y: null, cds10y: null, termSpread: null }); return; }
        const c5 = d?.["5Y"]?.value ?? null;
        const c10 = d?.["10Y"]?.value ?? null;
        setCdsData({
          cds5y: c5,
          cds10y: c10,
          termSpread: (c5 != null && c10 != null) ? c10 - c5 : null,
        });
      })
      .catch(() => setCdsData({ cds5y: null, cds10y: null, termSpread: null }));
  }, [iso]);

  // ORDER-03 A2 / F-0013: the brief's prompt is assembled server-side from the
  // database. This sends a country code and nothing else - the endpoint rejects
  // a free-form `prompt` with 422.
  const handleGenerateNarrative = async () => {
  setNarrativeLoading(true);
  setNarrative(null);

  try {
    const r = await apiFetch(`/analyze/country`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ country: iso }),
    });

    if (!r.ok) {
      setNarrative(
        r.status === 429
          ? "Brief limit reached. Try again later."
          : "Analysis unavailable."
      );
      setNarrativeLoading(false);
      return;
    }

    const data = await r.json();
    setNarrative(data.text || "Analysis unavailable.");

  } catch {
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

  const reservesChart = Array.isArray(reservesHistory)
    ? reservesHistory.map(h => ({ date: h.date.split("T")[0], value: parseFloat(h.value) })).filter(h => !isNaN(h.value))
    : [];

  const latestTic = ticChart[ticChart.length - 1];
  const prevTic = ticChart[ticChart.length - 2];
  const ticMom = latestTic && prevTic ? ((latestTic.holdings - prevTic.holdings) / prevTic.holdings * 100) : null;
  const latestGold = goldChart[goldChart.length - 1];
  const yieldCode = SOVEREIGN_YIELD_CODES[iso];
  const countryYield = yieldCode ? latestAll[yieldCode] : null;
  const us10y = latestAll["DGS10"];
  const spreadBps = spreadBasisPoints(countryYield, us10y);
  const spreadStroke = spreadColor(spreadBps);

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
          { label: "Spread vs US 10Y", val: spreadBps != null ? `${spreadBps > 0 ? "+" : ""}${spreadBps.toFixed(0)}bps` : "—", color: spreadStroke },
          {
            label: "5Y CDS",
            val: cdsData.cds5y != null ? `${cdsData.cds5y.toFixed(0)}bps` : "No coverage",
            color: cdsData.cds5y == null ? "#3A4D5C" : cdsData.cds5y > 250 ? "#E07B5A" : cdsData.cds5y > 100 ? "#C8A96E" : "#7EB8C9",
            sub: cdsData.cds5y == null
              ? "Not factored into stress score"
              : (cdsData.termSpread != null
                  ? `Term ${cdsData.termSpread > 0 ? "+" : ""}${cdsData.termSpread.toFixed(0)}bps${cdsData.termSpread < 0 ? " (inverted)" : ""}`
                  : null),
          },
        ].map(s => (
          <div key={s.label} style={{ background: "#0F1923", border: `1px solid ${s.color}22`, borderTop: `2px solid ${s.color}`, borderRadius: 2, padding: "12px 16px", flex: "1 1 120px" }}>
            <div style={{ fontFamily: "monospace", fontSize: 10, color: "#5A6878", textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 4 }}>{s.label}</div>
            <div style={{ fontFamily: "monospace", fontSize: 16, fontWeight: 700, color: s.color }}>{s.val}</div>
            {s.sub && <div style={{ fontFamily: "monospace", fontSize: 10, color: s.color, marginTop: 3, opacity: 0.8 }}>{s.sub}</div>}
          </div>
        ))}
      </div>

      {/* Charts */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))", gap: 16 }}>
        {ticChart.length > 0 && (
          <div style={{ background: "#0F1923", border: "1px solid #1A2530", borderRadius: 2, padding: "16px 20px" }}>
            <div style={{ fontFamily: "monospace", fontSize: 11, color: "#5A6878", marginBottom: 12, letterSpacing: "0.1em" }}>TREASURY HOLDINGS ($B) — {ticHistory?.data_points} months</div>
            <ResponsiveContainer width="100%" height={160}>
              <LineChart data={ticChart} margin={{ top: 4, right: 8, bottom: 4, left: 8 }}>
                <CartesianGrid strokeDasharray="2 6" stroke="#0A1520" vertical={false} />
                <XAxis dataKey="date" tickFormatter={formatDate} tick={{ fill: "#3A4D5C", fontFamily: "monospace", fontSize: 10 }} axisLine={false} tickLine={false} minTickGap={60} interval="preserveStartEnd" />
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
                <XAxis dataKey="date" tickFormatter={formatDate} tick={{ fill: "#3A4D5C", fontFamily: "monospace", fontSize: 10 }} axisLine={false} tickLine={false} minTickGap={60} interval="preserveStartEnd" />
                <YAxis tick={{ fill: "#3A4D5C", fontFamily: "monospace", fontSize: 10 }} axisLine={false} tickLine={false} width={48} tickFormatter={v => `${v.toFixed(0)}t`} />
                <Tooltip formatter={v => [`${v.toFixed(1)}t`, "Gold"]} contentStyle={{ background: "#0A1520", border: "1px solid #1E2D3D", borderRadius: 2, fontFamily: "monospace", fontSize: 11 }} labelFormatter={formatDate} labelStyle={{ color: "#5A6878" }} />
                <Line type="monotone" dataKey="tonnes" stroke="#E8C547" strokeWidth={1.5} dot={false} activeDot={{ r: 3 }} connectNulls />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
        {reservesChart.length > 0 && (
          <div style={{ background: "#0F1923", border: "1px solid #1A2530", borderRadius: 2, padding: "16px 20px" }}>
            <div style={{ fontFamily: "monospace", fontSize: 11, color: "#5A6878", marginBottom: 12, letterSpacing: "0.1em" }}>
              TOTAL RESERVES EX-GOLD ($M) — non-dollar reserve diversification
            </div>
            <ResponsiveContainer width="100%" height={160}>
              <LineChart data={reservesChart} margin={{ top: 4, right: 8, bottom: 4, left: 8 }}>
                <CartesianGrid strokeDasharray="2 6" stroke="#0A1520" vertical={false} />
                <XAxis dataKey="date" tickFormatter={formatDate} tick={{ fill: "#3A4D5C", fontFamily: "monospace", fontSize: 10 }} axisLine={false} tickLine={false} minTickGap={60} interval="preserveStartEnd" />
                <YAxis tick={{ fill: "#3A4D5C", fontFamily: "monospace", fontSize: 10 }} axisLine={false} tickLine={false} width={56} tickFormatter={v => `$${(v/1000).toFixed(0)}B`} />
                <Tooltip formatter={v => [`$${(v/1000).toFixed(1)}B`, "Reserves ex-Gold"]} contentStyle={{ background: "#0A1520", border: "1px solid #1E2D3D", borderRadius: 2, fontFamily: "monospace", fontSize: 11 }} labelFormatter={formatDate} labelStyle={{ color: "#5A6878" }} />
                <Line type="monotone" dataKey="value" stroke="#7EB8C9" strokeWidth={1.5} dot={false} activeDot={{ r: 3 }} connectNulls />
              </LineChart>
            </ResponsiveContainer>
            <div style={{ fontFamily: "monospace", fontSize: 10, color: "#1E2D3D", marginTop: 8 }}>
              Source: IMF IFS · Includes FX, SDRs, IMF positions · Excludes gold · Monthly
            </div>
          </div>
        )}
      </div>

      {!ticChart.length && !goldChart.length && !reservesChart.length && (
        <div style={{ fontFamily: "monospace", fontSize: 13, color: "#3A4D5C", padding: 24, textAlign: "center" }}>No data available for {iso}</div>
      )}

      {/* AI Narrative */}
      {(ticChart.length > 0 || goldChart.length > 0 || reservesChart.length > 0) && (
        <div style={{ background: "#060D14", border: "1px solid #C8A96E33", borderLeft: "3px solid #C8A96E", borderRadius: 2, padding: "16px 20px", marginTop: 16 }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: narrative || narrativeLoading ? 16 : 0 }}>
            <div>
              <div style={{ fontFamily: "monospace", fontSize: 11, color: "#C8A96E", letterSpacing: "0.1em", marginBottom: 2 }}>SENTINEL ANALYST BRIEF</div>
              {!narrative && !narrativeLoading && <div style={{ fontFamily: "monospace", fontSize: 11, color: "#3A4D5C" }}>AI-generated analysis using treasury, gold, and yield spread data</div>}
            </div>
            <button
              onClick={() => handleGenerateNarrative()}
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
