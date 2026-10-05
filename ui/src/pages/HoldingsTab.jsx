import { useState } from "react";
import { useApiResource } from "../hooks/useApiResource";
import { ColHeader } from "../components/ColHeader";
import { CountryDetail } from "../components/CountryDetail";
import { CountryLink } from "../components/CountryLink";
import { DataAsOf } from "../components/DataAsOf";
import { DataConfidence } from "../components/DataConfidence";
import { LoadFailure } from "../components/LoadFailure";
import { freshness } from "../lib/freshness";
import { MovementCell } from "../components/MovementCell";
import { trillions } from "../lib/format";

export function HoldingsTab({ latestAll = {} }) {
  const { data: holdings, error, loading } = useApiResource(`/holdings`);
  const [selected, setSelected] = useState(null);
  const [sort, setSort] = useState("holdings");

  if (loading) return <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: 300, fontFamily: "monospace", fontSize: 13, color: "#3A4D5C" }}>loading...</div>;
  if (error || !holdings) {
    return <LoadFailure what="TIC holdings" error={error}
      detail="If the table is genuinely empty, run POST /api/fetch/treasury-holdings." />;
  }

  const rows = [...(holdings.holdings || [])].sort((a, b) => {
    if (sort === "holdings") return b.holdings_billions_usd - a.holdings_billions_usd;
    if (sort === "pct") return b.percent_of_total - a.percent_of_total;
    if (sort === "country") return a.country_name.localeCompare(b.country_name);
    return 0;
  });

  // D-0085. `total_billions_usd` is the sum of the countries listed. The
  // published figure for ALL foreign holdings is the Grand Total row of SLT
  // Table 5 (D-0079), which is larger: Table 3 carries 76 countries, about 94%
  // of it. Labelling the sum "Total Foreign Holdings" understated the real
  // figure by $537.8bn once Table 3 widened the list from 20 countries to 60.
  const listedTotal = holdings.total_billions_usd;
  const grandTotal = holdings.grand_total_billions_usd ?? listedTotal;
  const coverage = holdings.coverage_pct;
  const ltOnlyCount = holdings.long_term_only_count ?? 0;
  const asOf = holdings.date ? new Date(holdings.date).toLocaleDateString("en-US", { month: "short", year: "numeric" }) : "—";
  const ticAge = freshness(holdings.date);
  // Concentration among countries with a comparable figure. A long-term-only
  // country is a different measure and cannot be summed with totals.
  const comparable = rows.filter((r) => !r.long_term_only);
  const top3pct = comparable.slice(0, 3).reduce((s, r) => s + r.percent_of_total, 0);

  const col = (label, key, tip) => (
    <ColHeader label={label} tip={tip} sortKey={key} activeSort={sort} onSort={setSort} align="right" />
  );

  return (
    <div>
      {/* Summary cards */}
      <DataConfidence sourceKeys={["tic"]} />

      <div style={{ display: "flex", gap: 12, marginBottom: 20, flexWrap: "wrap" }}>
        {[
          {
            label: "Total Foreign Holdings",
            val: `$${trillions(grandTotal)}T`,
            // The published total, with how much of it the list below accounts
            // for. D-0085: the tile used to show the sum of the rows.
            sub: coverage != null ? `${coverage.toFixed(1)}% shown below` : null,
          },
          {
            label: "Countries Listed",
            val: comparable.length,
            sub: ltOnlyCount > 0 ? `+${ltOnlyCount} long-term only` : null,
          },
          // D-0091: the tile opens the top holder's card. An empty tile stays
          // a plain dash - no link and no marker, there is no country to name.
          { label: "Top Holder", val: comparable[0]
            ? <CountryLink iso={comparable[0].country_code} name={comparable[0].country_code} showCode={false} />
            : "—" },
          { label: "Top 3 Concentration", val: `${top3pct.toFixed(1)}%`, alert: top3pct > 40 },
          {
            label: "Data As Of",
            val: asOf,
            // F-0083: the tile said "Dec 2025" and nothing else while the
            // source had been frozen for 302 days.
            sub: ticAge.age != null ? ticAge.text : null,
            subColor: ticAge.color,
          },
        ].map(s => (
          <div key={s.label} style={{ background: "#0F1923", border: `1px solid ${s.alert ? "#E07B5A33" : "#1A2530"}`, borderTop: `2px solid ${s.alert ? "#E07B5A" : "#1A2530"}`, borderRadius: 2, padding: "14px 20px", flex: "1 1 140px" }}>
            <div style={{ fontFamily: "monospace", fontSize: 10, color: "#5A6878", textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 6 }}>{s.label}</div>
            <div style={{ fontFamily: "monospace", fontSize: 20, fontWeight: 700, color: s.alert ? "#E07B5A" : "#E8E0D0" }}>{s.val}</div>
            {s.sub && (
              <div style={{ fontFamily: "monospace", fontSize: 10, color: s.subColor ?? "#5A6878", marginTop: 3 }}>{s.sub}</div>
            )}
          </div>
        ))}
      </div>

      {/* Top 8 quick cards */}
      <div style={{ display: "flex", gap: 8, marginBottom: 20, flexWrap: "wrap" }}>
        {rows.slice(0, 8).map(c => (
          <CountryLink key={c.country_code} iso={c.country_code} name={c.country_name} showCode={false}
            style={{ display: "block", background: "#0A1520", border: "1px solid #1A2530", borderRadius: 2, padding: "8px 14px", cursor: "pointer", flex: "1 1 110px", maxWidth: 160 }}>
            <div style={{ fontFamily: "monospace", fontSize: 10, color: "#5A6878" }}>{c.country_code}</div>
            <div style={{ fontFamily: "monospace", fontSize: 13, color: "#E8E0D0", marginTop: 2 }}>${c.holdings_billions_usd.toFixed(0)}B</div>
            <div style={{ fontFamily: "monospace", fontSize: 11, color: "#C8A96E", marginTop: 2 }}>{c.percent_of_total.toFixed(1)}%</div>
          </CountryLink>
        ))}
      </div>

      {/* Inline country detail */}
      {selected && (
        <CountryDetail iso={selected.country_code} onClose={() => setSelected(null)} latestAll={latestAll} />
      )}

      {/* Exited countries note */}
      <div style={{ background: "#FF444410", border: "1px solid #FF444433", borderLeft: "3px solid #FF4444", borderRadius: 2, padding: "12px 18px", marginBottom: 16 }}>
        <div style={{ fontFamily: "monospace", fontSize: 11, color: "#FF4444", fontWeight: 700, marginBottom: 4 }}>
          🚨 COUNTRIES WITH COMPLETED TREASURY LIQUIDATION (not in table below)
        </div>
        <div style={{ fontFamily: "monospace", fontSize: 11, color: "#8A9BAC", lineHeight: 1.8 }}>
          The following hold <strong style={{ color: "#FF4444" }}>zero US Treasuries</strong> — they exited before the TIC reporting window. See CROSS-ASSET tab for stress analysis.
        </div>
        <div style={{ display: "flex", gap: 10, marginTop: 8, flexWrap: "wrap" }}>
          {[
            { iso: "RUS", name: "Russia", gold: "2,304t" },
            { iso: "TUR", name: "Turkey", gold: "535t" },
            { iso: "QAT", name: "Qatar", gold: "115t" },
            { iso: "UZB", name: "Uzbekistan", gold: "416t" },
          ].map(c => (
            <div key={c.iso} style={{ background: "#0F1923", border: "1px solid #FF444433", borderRadius: 2, padding: "6px 12px" }}>
              <CountryLink iso={c.iso} name={c.name} showCode={false}>
                <span style={{ fontFamily: "monospace", fontSize: 11, color: "#FF4444" }}>{c.iso}</span>
                <span style={{ fontFamily: "monospace", fontSize: 11, color: "#8A9BAC", marginLeft: 6 }}>{c.name}</span>
              </CountryLink>
              <span style={{ fontFamily: "monospace", fontSize: 10, color: "#E8C547", marginLeft: 8 }}>⬛ $0B · 🥇 {c.gold}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Full holdings table */}
      <div style={{ background: "#0A1520", border: "1px solid #1A2530", borderRadius: 2, padding: "20px 0" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "0 20px 16px" }}>
          <div style={{ fontFamily: "monospace", fontSize: 12, color: "#8A9BAC", letterSpacing: "0.1em" }}>
            FOREIGN TREASURY HOLDINGS
            <span style={{ marginLeft: 10, fontSize: 10, color: "#3A4D5C" }}>click country for its card · click row for history</span>
          </div>
        </div>
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr>
                <ColHeader label="Country" tip="Foreign sovereign entity holding US Treasuries, per the monthly TIC (Treasury International Capital) report published by the US Treasury." align="left" />
                {col("Holdings ($B)", "holdings", "Total US Treasury securities held, in billions of USD. Includes T-bills, notes, and bonds. Source: latest TIC monthly snapshot.")}
                {col("% of Total", "pct", "This country's share of all foreign-held US Treasuries. High concentration in a single holder (e.g. >15%) represents systemic risk — a large sell-off by one country can move the market.")}
                <ColHeader label="Movement" tip="Change in the country's reported position since the previous month, and WHAT KIND of movement it was. 'sold' and 'bought' are net transactions; 'repriced' means the position moved mainly on bond prices rather than on any decision — Japan's July position fell $12.7bn while it BOUGHT $0.9bn, and dimension 1 does not score that as selling (A-0021, D-0087). The label comes from the same rule the scorer applies, so the word here and the score agree." align="right" />
                <ColHeader label="Tx 3mo" tip="Net transactions over three months, in billions, with price stripped out — what the country actually bought or sold. Japan's was −$88.6bn over the quarter to July 2026, almost all of it Treasury bills, which a monthly percentage cannot show (F-0099)." align="right" />
                <ColHeader label="Share" tip="Visual bar showing this country's proportional share of total foreign holdings. Top 3 holders highlighted in gold." align="right" />
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
                      {/* D-0091: the name opens the card; the row still opens
                          the inline history panel (F-0064). The link stops
                          propagation, so the two never both fire. */}
                      <CountryLink iso={c.country_code} name={c.country_name} />
                      {c.long_term_only && (
                        <span
                          title="Long-term holdings only. This reporter publishes 'n.a.' for its total position, so bills are not included and this figure is NOT comparable with the totals above it (D-0085)."
                          style={{ marginLeft: 6, fontSize: 9, color: "#5A6878", cursor: "help" }}>
                          LT only
                        </span>
                      )}
                    </td>
                    <td style={{ padding: "10px 16px", fontFamily: "monospace", fontSize: 13, color: "#8A9BAC", textAlign: "right" }}>${c.holdings_billions_usd.toFixed(1)}B</td>
                    <td style={{ padding: "10px 16px", fontFamily: "monospace", fontSize: 13, color: "#C8A96E", textAlign: "right" }}>{c.percent_of_total.toFixed(1)}%</td>
                    {/* D-0087. The movement and what kind it was. Japan's
                        position fell $12.7bn last month while it BOUGHT
                        $0.9bn; a change column alone says the opposite of
                        what happened. */}
                    <td style={{ padding: "10px 16px", textAlign: "right" }}>
                      <MovementCell
                        change={c.change_1m_bn}
                        pct={c.change_1m_pct}
                        movement={c.movement}
                        note={c.movement_note}
                      />
                    </td>
                    <td style={{ padding: "10px 16px", fontFamily: "monospace", fontSize: 12, textAlign: "right", color: (c.net_3m_bn ?? 0) < 0 ? "#E07B5A" : (c.net_3m_bn ?? 0) > 0 ? "#5DB87A" : "#5A6878" }}
                        title="Net transactions over three months — what the country actually bought or sold, with price stripped out.">
                      {c.net_3m_bn == null ? "—" : `${c.net_3m_bn > 0 ? "+" : c.net_3m_bn < 0 ? "−" : ""}$${Math.abs(c.net_3m_bn).toFixed(1)}B`}
                    </td>
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
      <DataAsOf
        asOf={holdings.date}
        source="US Treasury TIC"
      />
    </div>
  );
}

// ── Country Search Tab ────────────────────────────────────────────────────────
