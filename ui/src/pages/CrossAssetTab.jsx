import { useState } from "react";
import { useApiResource } from "../hooks/useApiResource";
import { tierColor, tierLabel } from "../lib/format";
import { AlertBanner } from "../components/AlertBanner";
import { ColHeader } from "../components/ColHeader";
import { DataAsOf } from "../components/DataAsOf";
import { describeCrossAsset } from "../lib/crossAssetNarrative";
import { LoadFailure } from "../components/LoadFailure";

export function CrossAssetTab() {
  const { data, error, loading } = useApiResource(`/holdings/cross-asset-stress`);
  const [view, setView] = useState("all");

  if (loading) return <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: 300, fontFamily: "monospace", fontSize: 13, color: "#3A4D5C" }}>loading cross-asset signals...</div>;
  if (error || !data || data.detail) {
    return <LoadFailure what="cross-asset signals" error={error}
      detail="Ensure TIC holdings and gold reserves are both loaded." />;
  }

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
                    <ColHeader label="Country" tip="Sovereign entity being analyzed for cross-asset stress. Countries appear here only when they show simultaneous selling pressure across multiple asset classes." align="left" />
                    <ColHeader label="Signal" tip="Stress classification: DIVERGENCE (2×) = selling gold while spot price rises — forced seller; CROSS-ASSET (1.5×) = selling both T-bills and gold; EXITED = zero US Treasuries held; T-ONLY = reducing Treasury holdings only; Au ONLY = reducing gold reserves only." align="left" />
                    <ColHeader label="T-Bills MoM" tip="Month-over-month % change in US Treasury holdings. Negative = selling. 'EXITED' means zero holdings — position fully liquidated before TIC reporting window." align="right" />
                    <ColHeader label="Consec ↓" tip="Consecutive months of declining Treasury holdings. Persistence distinguishes structural de-dollarization from tactical rebalancing. 3+ months = significant signal." align="right" />
                    <ColHeader label="Gold t" tip="Central bank gold reserves in metric tonnes, from the most recent World Gold Council / IMF IFS quarterly report. Large holdings alongside zero Treasuries indicate deliberate reserve restructuring." align="right" />
                    <ColHeader label="Gold MoM" tip="Quarter-over-quarter % change in gold reserves. Negative = selling gold. When a country sells gold AND Treasuries simultaneously, cross-asset multiplier (1.5×) activates." align="right" />
                    <ColHeader label="Non-$ Reserves" tip="Total reserves excluding gold (TRESEG series, FRED). REBUILDING = non-dollar reserves growing >5% YoY — country is building an alternative reserve base. DEPLETING = shrinking >5% YoY — possible forced selling under distress." align="right" />
                    <ColHeader label="Score" tip="Composite stress score (0-150). Base score from the T-bill and gold signals, multiplied by 1.5x for cross-asset or 2.0x for divergence. Shown as a number rather than a gauge: a bar answers \u0022how full\u0022 when the question is \u0022how much, and driven by what\u0022." align="right" />
                    <ColHeader label="Analysis" tip="Why this country is on this table, composed from the figures in the row. Not an LLM call - it is a description of data already present, so it is identical for identical rows and works when the brief endpoint is down." align="left" />
                  </tr>
                </thead>
                <tbody>
                  {displayData.map(c => {
                    const tier = c.signal_tier || (c.divergence_signal ? "DIVERGENCE" : c.cross_asset_stress ? "CROSS_ASSET" : c.no_tic_holdings ? "EXITED" : c.selling_treasuries ? "TREASURY_ONLY" : "GOLD_ONLY");
                    const tc = tierColor(tier);
                    const label = tierLabel(tier);
                    return (
                      <tr key={c.country_iso} style={{ borderBottom:"1px solid #0F1923" }}
                        onMouseEnter={e => e.currentTarget.style.background="#0D1820"}
                        onMouseLeave={e => e.currentTarget.style.background="transparent"}>
                        <td style={{ padding:"8px 9px", fontFamily:"monospace", fontSize:13, color:"#E8E0D0" }}>
                          {c.country_name}<span style={{ marginLeft:6, fontSize:10, color:"#3A4D5C" }}>{c.country_iso}</span>
                        </td>
                        <td style={{ padding:"8px 9px" }}>
                          <span style={{ fontFamily:"monospace", fontSize:10, color:tc, background:`${tc}18`, border:`1px solid ${tc}44`, borderRadius:2, padding:"2px 6px", whiteSpace:"nowrap" }}>{label}</span>
                        </td>
                        <td style={{ padding:"8px 9px", fontFamily:"monospace", fontSize:12, textAlign:"right", color:(c.tic_mom_pct??0)<0?"#E07B5A":"#5DB87A" }}>
                          {c.no_tic_holdings
                            ? <span style={{ color:"#FF8C00", fontSize:10 }}>EXITED ⚠</span>
                            : c.tic_mom_pct!=null?`${c.tic_mom_pct>0?"+":""}${c.tic_mom_pct.toFixed(2)}%`:"—"}
                        </td>
                        <td style={{ padding:"8px 9px", fontFamily:"monospace", fontSize:12, textAlign:"right", color:(c.tic_consecutive_months??0)>=3?"#E07B5A":"#8A9BAC" }}>{(c.tic_consecutive_months??0)>0?`${c.tic_consecutive_months}mo`:"—"}</td>
                        <td style={{ padding:"8px 9px", fontFamily:"monospace", fontSize:12, textAlign:"right", color:"#8A9BAC" }}>{c.gold_tonnes!=null?`${c.gold_tonnes.toLocaleString()}t`:"—"}</td>
                        <td style={{ padding:"8px 9px", fontFamily:"monospace", fontSize:12, textAlign:"right", color:c.gold_mom_pct==null?"#3A4D5C":c.gold_mom_pct<0?"#E07B5A":"#5DB87A" }}>
                          {c.gold_mom_pct!=null?`${c.gold_mom_pct>0?"+":""}${c.gold_mom_pct.toFixed(2)}%`:"—"}
                        </td>
                        <td style={{ padding:"8px 9px", fontFamily:"monospace", fontSize:11, textAlign:"right", color:c.treseg_signal==="REBUILDING"?"#FF4444":c.treseg_signal==="DEPLETING"?"#E07B5A":"#3A4D5C" }}>
                          {c.treseg_signal==="NO_DATA"||!c.treseg_signal ? "—" : `${c.treseg_signal} ${c.treseg_trend_pct!=null?(c.treseg_trend_pct>0?"+":"")+c.treseg_trend_pct+"%":""}`}
                        </td>
                        <td style={{ padding:"8px 10px", fontFamily:"monospace", textAlign:"right", whiteSpace:"nowrap" }}>
                          <span style={{ fontSize:15, fontWeight:700, color:tc }}>{(c.stress_score??0).toFixed(0)}</span>
                          {c.multiplier > 1 && (
                            <span style={{ fontSize:10, color:"#E07B5A", marginLeft:4 }}>{c.multiplier}\u00d7</span>
                          )}
                        </td>
                        <td style={{ padding:"8px 10px", fontFamily:"monospace", fontSize:11, color:"#8A9BAC", lineHeight:1.45, minWidth:230 }}>
                          {(() => {
                            const a = describeCrossAsset(c);
                            return (
                              <>
                                <div style={{ color:"#C8D4DF" }}>{a.headline}</div>
                                {a.detail && <div style={{ color:"#5A6878", fontSize:10, marginTop:2 }}>{a.detail}</div>}
                              </>
                            );
                          })()}
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
      <DataAsOf
        asOf={data.as_of}
        source="US Treasury TIC · World Gold Council"
        note="the TIC source has not published since then; the Treasury side of every signal here is that old"
      />
    </div>
  );
}


// ── Composite Tab ─────────────────────────────────────────────────────────────
