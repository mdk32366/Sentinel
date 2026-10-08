import { useState } from "react";
import { XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, BarChart, Bar } from "recharts";
import { useApiResource } from "../hooks/useApiResource";
import { ColHeader } from "../components/ColHeader";
import { MovementCell } from "../components/MovementCell";
import { DataConfidence } from "../components/DataConfidence";
import { CountryDetail } from "../components/CountryDetail";
import { CountryAxisTick } from "../components/CountryAxisTick";
import { CountryLink } from "../components/CountryLink";
import { navigateToCountry } from "../lib/countryRoute";
import { LoadFailure } from "../components/LoadFailure";
import { InfoTip } from "../components/InfoTip";

export function GoldReservesTab({ latestAll = {} }) {
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
      <DataConfidence sourceKeys={["gold_reserves", "gold_price"]} />
      {/* Summary */}
      <div style={{ display: "flex", gap: 12, marginBottom: 20, flexWrap: "wrap" }}>
        {[
          { label: "Total CB Gold", val: `${total?.toLocaleString(undefined, { maximumFractionDigits: 0 })}t`,
            tip: "The sum of each country's most recent official gold reading, in metric tonnes. The source is the IMF IRFCL monthly return, converted from fine troy ounces, with the World Gold Council series as backfill (D-0076). Countries file at different times, so this adds readings from different months rather than giving a single-date world total." },
          { label: "Countries Reporting", val: reserves.country_count,
            tip: "Countries with at least one official gold reading on record, each counted once at its latest. Not all of them filed this month: the As Of column gives each one's month." },
          // D-0091: opens the top holder's card (USA -> the USA dashboard).
          { label: "Top Holder", val: rows[0]
            ? <CountryLink iso={rows[0].country_code} name={rows[0].country_code} showCode={false} />
            : "—",
            tip: "The country with the largest latest gold holding. Click to open its card (D-0091)." },
          { label: "US Share", tip: "United States holdings as a share of the Total CB Gold figure, using each country's latest reading.", val: rows.find(r => r.country_code === "USA") ? `${rows.find(r => r.country_code === "USA").percent_of_total.toFixed(1)}%` : "—" },
          { label: "Data", val: "Per-country latest",
            tip: "Every figure on this tab uses each country's most recent reading, whatever month it is from, because reporting lags differ by country. The As Of column gives each country's month." },
        ].map(s => (
          <div key={s.label} style={{ background: "#0F1923", border: "1px solid #1A2530", borderTop: "2px solid #C8A96E", borderRadius: 2, padding: "14px 20px", flex: "1 1 140px" }}>
            <InfoTip title={s.label} tip={s.tip} placement="below" as="div" style={{ fontFamily: "monospace", fontSize: 10, color: "#5A6878", textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 6 }}>
              <span style={{ borderBottom: "1px dashed #2A3D50", paddingBottom: 1 }}>{s.label}</span>
            </InfoTip>
            <div style={{ fontFamily: "monospace", fontSize: 20, fontWeight: 700, color: "#E8E0D0" }}>{s.val}</div>
          </div>
        ))}
      </div>

      {/* Top 8 quick cards */}
      <div style={{ display: "flex", gap: 8, marginBottom: 20, flexWrap: "wrap" }}>
        {rows.slice(0, 8).map(c => (
          <CountryLink key={c.country_code} iso={c.country_code} name={c.country_name} showCode={false}
            style={{ display: "block", background: "#0A1520", border: "1px solid #1A2530", borderRadius: 2, padding: "8px 14px", cursor: "pointer", flex: "1 1 110px", maxWidth: 160 }}>
            <div style={{ fontFamily: "monospace", fontSize: 10, color: "#5A6878" }}>{c.country_code}</div>
            <div style={{ fontFamily: "monospace", fontSize: 13, color: "#E8E0D0", marginTop: 2 }}>{c.metric_tonnes.toFixed(0)}t</div>
            <div style={{ fontFamily: "monospace", fontSize: 11, color: "#C8A96E", marginTop: 2 }}>{c.percent_of_total.toFixed(1)}%</div>
          </CountryLink>
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
            {/* D-0091: each tick is a link to that country's card, and so is
                each bar. The tooltip stays text - it only exists on hover. */}
            <XAxis dataKey="country_code" tick={<CountryAxisTick />} axisLine={false} tickLine={false} angle={-45} textAnchor="end" />
            <YAxis tick={{ fill: "#3A4D5C", fontFamily: "monospace", fontSize: 10 }} axisLine={false} tickLine={false} width={52} tickFormatter={v => `${v.toLocaleString()}t`} />
            <Tooltip formatter={v => [`${v.toLocaleString()}t`, "Gold"]} contentStyle={{ background: "#0A1520", border: "1px solid #1E2D3D", borderRadius: 2, fontFamily: "monospace", fontSize: 11 }} labelStyle={{ color: "#5A6878" }} />
            <Bar dataKey="metric_tonnes" radius={[2, 2, 0, 0]} fill="#C8A96E" fillOpacity={0.8}
              onClick={(d) => navigateToCountry(d?.country_code ?? d?.payload?.country_code)} cursor="pointer" />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Full table */}
      <div style={{ background: "#0A1520", border: "1px solid #1A2530", borderRadius: 2, padding: "20px 0" }}>
        <div style={{ padding: "0 20px 16px", fontFamily: "monospace", fontSize: 12, color: "#8A9BAC", letterSpacing: "0.1em" }}>
          COMPLETE HOLDINGS TABLE
          <span style={{ marginLeft: 10, fontSize: 10, color: "#3A4D5C" }}>click country for its card · click row for history</span>
        </div>
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr>
                <ColHeader label="#" tip="Rank by gold holdings, largest to smallest." align="right" />
                <ColHeader label="Country" tip="Sovereign nation or monetary authority reporting central bank gold to the IMF. Read from the IMF IRFCL return directly rather than from the World Gold Council compilation of it (D-0076)." align="left" />
                <ColHeader label="As Of" tip="Month of the most recent reading for this country. D-0076 moved the source from a quarterly World Gold Council download to the IMF's MONTHLY IRFCL return, so this is now a month rather than a quarter. Countries file at different times, so dates vary; the World Gold Council series is retained as backfill for the ~28 countries that do not file the monthly template." align="right" />
                <ColHeader label="Tonnes" tip="Gold holdings in metric tonnes. 1 metric tonne = 32,150 troy ounces. The US holds ~8,133t — the largest national gold reserve in the world. Russia and China have been the most consistent accumulators since 2014." align="right" />
                <ColHeader label="% of Total" tip="This country's share of all reported central bank gold holdings worldwide. A rising share indicates active accumulation relative to peers." align="right" />
                <ColHeader label="Movement" tip="Change in tonnage since the previous reading, and what kind of movement it is. Gold is held in TONNES — a pure quantity — so unlike Treasuries there is no price component to separate out: a change here is always a decision. The kind is therefore direction and persistence, which is what dimension 2 scores at 4 points per consecutive declining quarter (D-0087)." align="right" />
                <ColHeader label="3mo" tip="Change in tonnage over three readings, with the percentage. Dimension 2 scores the quarter-on-quarter decline plus how many quarters it has persisted; the series is resampled to one reading per calendar quarter because D-0076 made the source monthly (F-0094)." align="right" />
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
                      {/* D-0091: name -> card; row -> inline panel (F-0064). */}
                      <CountryLink iso={c.country_code} name={c.country_name} />
                    </td>
                    <td style={{ padding: "8px 16px", fontFamily: "monospace", fontSize: 11, color: "#3A4D5C", textAlign: "right" }}>{c.as_of_date ?? "—"}</td>
                    <td style={{ padding: "8px 16px", fontFamily: "monospace", fontSize: 13, color: "#C8A96E", textAlign: "right" }}>{c.metric_tonnes.toLocaleString(undefined, { maximumFractionDigits: 1 })}</td>
                    <td style={{ padding: "8px 16px", fontFamily: "monospace", fontSize: 12, color: "#8A9BAC", textAlign: "right" }}>{c.percent_of_total.toFixed(1)}%</td>
                    {/* D-0087. Tonnes are a pure quantity, so the movement IS
                        the decision — there is no price component to strip out
                        as there is for Treasuries. */}
                    <td style={{ padding: "8px 16px", textAlign: "right" }}>
                      <MovementCell
                        change={c.change_1m_tonnes}
                        unit="t"
                        movement={c.movement}
                        note={c.movement_note}
                      />
                    </td>
                    <td style={{ padding: "8px 16px", textAlign: "right" }}>
                      <MovementCell
                        change={c.change_3m_tonnes}
                        unit="t"
                        pct={c.change_3m_pct}
                        movement={c.movement}
                        note={c.consecutive_declines ? `${c.consecutive_declines} consecutive declining readings.` : undefined}
                      />
                    </td>
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
      <div style={{ marginTop: 12, fontFamily: "monospace", fontSize: 11, color: "#1E2D3D" }}>Source: IMF IRFCL (line 56) · Monthly · Reporting lag ~2 months · World Gold Council retained as backfill for non-filers</div>
    </div>
  );
}

// ── Main App ──────────────────────────────────────────────────────────────────
