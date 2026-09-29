import { useState } from "react";
import { XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, BarChart, Bar } from "recharts";
import { useApiResource } from "../hooks/useApiResource";
import { ColHeader } from "../components/ColHeader";
import { CountryDetail } from "../components/CountryDetail";
import { LoadFailure } from "../components/LoadFailure";

export function GoldReservesTab({ onCountrySelect, latestAll = {} }) {
  const { data: reserves, error, loading } = useApiResource(`/gold-reserves`);
  const [selected, setSelected] = useState(null);

  if (loading) return <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: 300, fontFamily: "monospace", fontSize: 13, color: "#3A4D5C" }}>loading gold reserves...</div>;
  if (error || !reserves) {
    return <LoadFailure what="gold reserves" error={error}
      detail="If the table is genuinely empty, run POST /api/fetch/gold-reserves." />;
  }

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
        <CountryDetail iso={selected.country_code} onClose={() => setSelected(null)} latestAll={latestAll} />
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
                <ColHeader label="#" tip="Rank by gold holdings, largest to smallest." align="right" />
                <ColHeader label="Country" tip="Sovereign nation or monetary authority (e.g. IMF, ECB) reporting central bank gold reserves to the IMF IFS database, as compiled by the World Gold Council." align="left" />
                <ColHeader label="As Of" tip="Quarter of the most recent data point for this country. Gold reserves are reported quarterly. Some countries lag 1–2 quarters behind due to reporting delays — dates vary by country." align="right" />
                <ColHeader label="Tonnes" tip="Gold holdings in metric tonnes. 1 metric tonne = 32,150 troy ounces. The US holds ~8,133t — the largest national gold reserve in the world. Russia and China have been the most consistent accumulators since 2014." align="right" />
                <ColHeader label="% of Total" tip="This country's share of all reported central bank gold holdings worldwide. A rising share indicates active accumulation relative to peers." align="right" />
                <ColHeader label="Share" tip="Visual bar representing proportional gold holdings. Top 3 holders shown in gold, top 10 in amber, remainder in slate." align="right" />
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
