import { useState } from "react";
import { useApiResource } from "../hooks/useApiResource";
import { MAX_RAW_SCORE, STRESS_DIMENSIONS, STRESS_MULTIPLIERS, cdsBandText } from "../lib/dimensions";
import { AlertBanner } from "../components/AlertBanner";
import { ColHeader } from "../components/ColHeader";
import { LoadFailure } from "../components/LoadFailure";

export function CompositeTab({ onCountrySelect }) {
  const { data, error, loading } = useApiResource(`/stress/composite`);
  const [view, setView] = useState("all");

  if (loading) return <div style={{ display:"flex", alignItems:"center", justifyContent:"center", height:300, fontFamily:"monospace", fontSize:13, color:"#3A4D5C" }}>computing composite stress...</div>;
  if (error || !data || data.error) {
    return <LoadFailure what="composite stress" error={error} detail={data?.error} />;
  }

  const { summary } = data;
  const allResults = [...(data.crisis||[]), ...(data.stressed||[]), ...(data.elevated||[]), ...(data.watch||[])];
  const displayData = view==="crisis" ? data.crisis
    : view==="stressed" ? [...(data.crisis||[]),...(data.stressed||[])]
    : view==="elevated" ? [...(data.crisis||[]),...(data.stressed||[]),...(data.elevated||[])]
    : allResults;

  const TIER_COLORS = { CRISIS:"#FF4444", STRESSED:"#E07B5A", ELEVATED:"#E8C547", WATCH:"#5A6878" };
  const compactHead = { padding: "8px 7px", whiteSpace: "normal", lineHeight: 1.25 };
  const activitySticky = {
    position: "sticky",
    right: 0,
    background: "#0A1520",
    zIndex: 2,
    boxShadow: "-8px 0 10px -8px rgba(0,0,0,0.75)",
  };

  return (
    <div>
      {summary?.crisis === 0 && summary?.stressed === 0 && (
        <div style={{ background:"#5DB87A15", border:"1px solid #5DB87A44", borderLeft:"3px solid #5DB87A", borderRadius:2, padding:"10px 16px", marginBottom:20, fontFamily:"monospace", fontSize:12, color:"#5DB87A" }}>
          ✓ No CRISIS or STRESSED signals active as of {data.as_of} — system monitoring {allResults.length} countries.
        </div>
      )}
      {(summary?.crisis??0) > 0 && (
        <AlertBanner message={`⚡ ${summary.crisis} CRISIS-tier countr${summary.crisis===1?"y":"ies"} — all stress dimensions firing.`} color="#FF4444" />
      )}

      {/* Score methodology */}
      <div style={{ background:"#0A1520", border:"1px solid #1A2530", borderRadius:2, padding:"14px 20px", marginBottom:20, display:"flex", gap:28, flexWrap:"wrap" }}>
        <div style={{ fontFamily:"monospace", fontSize:10, color:"#3A4D5C", letterSpacing:"0.1em", alignSelf:"center" }}>SCORE =</div>
        {STRESS_DIMENSIONS.map(s => (
          <div key={s.label} style={{ display:"flex", alignItems:"center", gap:8 }}>
            <div style={{ width:8, height:8, borderRadius:"50%", background:s.color, flexShrink:0 }} />
            <div>
              <div style={{ fontFamily:"monospace", fontSize:11, color:"#E8E0D0" }}>{s.label} <span style={{ color:"#3A4D5C" }}>0–{s.max} pts</span></div>
              <div style={{ fontFamily:"monospace", fontSize:10, color:"#5A6878" }}>{s.desc}</div>
            </div>
          </div>
        ))}
        <div style={{ display:"flex", alignItems:"center", gap:8, borderLeft:"1px solid #1A2530", paddingLeft:20 }}>
          <div>
            {STRESS_MULTIPLIERS.map(m => (
              <div key={m.label} style={{ fontFamily:"monospace", fontSize:11, color:m.color }}>
                {m.label} <span style={{ color:"#5A6878" }}>({m.desc})</span>
              </div>
            ))}
            <div style={{ fontFamily:"monospace", fontSize:10, color:"#3A4D5C", marginTop:4 }}>
              max {MAX_RAW_SCORE} raw · capped at 150
            </div>
          </div>
        </div>
      </div>

      {/* Summary cards */}
      <div style={{ display:"flex", gap:12, marginBottom:20, flexWrap:"wrap" }}>
        {[
          { label:"CRISIS", val:summary?.crisis??0, color:"#FF4444", desc:"All signals + multiplier" },
          { label:"STRESSED", val:summary?.stressed??0, color:"#E07B5A", desc:"Score 50–75" },
          { label:"ELEVATED", val:summary?.elevated??0, color:"#E8C547", desc:"Score 25–50" },
          { label:"WATCH", val:summary?.watch??0, color:"#5A6878", desc:"Score < 25" },
          { label:"Top Risk", val:summary?.highest_risk?.country_name??"—", color:"#C8A96E", desc:`Score: ${summary?.highest_risk?.composite_score?.toFixed(0)??"—"}` },
        ].map(s => (
          <div key={s.label} style={{ background:"#0F1923", border:`1px solid ${(s.val>0&&s.label!=="Top Risk")?`${s.color}33`:"#1A2530"}`, borderTop:`2px solid ${(s.val>0||s.label==="Top Risk")?s.color:"#1A2530"}`, borderRadius:2, padding:"14px 20px", flex:"1 1 140px" }}>
            <div style={{ fontFamily:"monospace", fontSize:10, color:"#5A6878", textTransform:"uppercase", letterSpacing:"0.1em", marginBottom:4 }}>{s.label}</div>
            <div style={{ fontFamily:"monospace", fontSize:20, fontWeight:700, color:(s.val>0||s.label==="Top Risk")?s.color:"#3A4D5C" }}>{s.val}</div>
            <div style={{ fontFamily:"monospace", fontSize:10, color:"#3A4D5C", marginTop:3 }}>{s.desc}</div>
          </div>
        ))}
      </div>

      {/* Leaderboard */}
      <div style={{ background:"#0A1520", border:"1px solid #1A2530", borderRadius:2, padding:"20px 0" }}>
        <div style={{ display:"flex", alignItems:"center", justifyContent:"space-between", padding:"0 20px 16px" }}>
          <div style={{ fontFamily:"monospace", fontSize:12, color:"#8A9BAC", letterSpacing:"0.1em" }}>
            COMPOSITE SOVEREIGN STRESS LEADERBOARD
            <span style={{ marginLeft:10, fontSize:10, color:"#3A4D5C" }}>click country to open full detail view</span>
          </div>
          <div style={{ display:"flex", gap:6 }}>
            {[["all","ALL"],["elevated","ELEVATED+"],["stressed","STRESSED+"],["crisis","CRISIS"]].map(([v,l]) => (
              <button key={v} onClick={() => setView(v)} style={{ background:view===v?"#1A2530":"transparent", border:`1px solid ${view===v?"#5A6878":"#1E2D3D"}`, color:view===v?"#C8A96E":"#3A4D5C", borderRadius:2, padding:"4px 10px", cursor:"pointer", fontFamily:"monospace", fontSize:11 }}>{l}</button>
            ))}
          </div>
        </div>
        {displayData.length === 0
          ? <div style={{ padding:"40px 20px", fontFamily:"monospace", fontSize:13, color:"#3A4D5C", textAlign:"center" }}>no countries in this tier</div>
          : (
            <div style={{ overflowX:"auto" }}>
              <table style={{ width:"100%", borderCollapse:"collapse", tableLayout:"fixed" }}>
                <colgroup>
                  <col style={{ width: 108 }} />
                  <col style={{ width: 78 }} />
                  <col style={{ width: 70 }} />
                  <col style={{ width: 50 }} />
                  <col style={{ width: 54 }} />
                  <col style={{ width: 36 }} />
                  <col style={{ width: 36 }} />
                  <col style={{ width: 54 }} />
                  <col style={{ width: 36 }} />
                  <col style={{ width: 54 }} />
                  <col style={{ width: 62 }} />
                  <col style={{ width: 42 }} />
                  <col style={{ width: 62 }} />
                  <col style={{ width: 86 }} />
                  <col />
                </colgroup>
                <thead>
                  <tr>
                    <ColHeader label="Country" tip="Sovereign entity scored across five stress dimensions. A ◦ marker beside the score means no usable CDS quote for that country, so the score reflects four. Click any row to open the full country detail view." align="left" style={compactHead} />
                    <ColHeader label="Tier" tip="Risk classification based on composite score: WATCH (<25), ELEVATED (25–50), STRESSED (50–75), CRISIS (≥75). CRISIS requires all major signals firing plus a multiplier." align="left" style={compactHead} />
                    <ColHeader label="T-Bill MoM" tip="Month-over-month % change in US Treasury holdings. 'ZERO ⚠' means the country has fully exited — holds no US Treasuries. This is the primary Treasury stress input (Dimension 1)." align="right" style={compactHead} />
                    <ColHeader label="Consec" tip="Consecutive months of declining Treasury holdings. Each additional month adds 4 pts to the Treasury score, capped at 5 months (20 pts). Persistence distinguishes strategic selling from noise." align="right" style={compactHead} />
                    <ColHeader label="Gold t" tip="Central bank gold reserves in metric tonnes (latest quarterly report). Context for the gold score: large reserves + selling = higher stress than small reserves + selling." align="right" style={compactHead} />
                    <ColHeader label="T" tip="Treasury dimension score (0–50 pts). Calculated from: MoM decline magnitude (0–30 pts, scaled) + consecutive declining months (0–20 pts). This is the highest-weight stress dimension." align="right" style={compactHead} />
                    <ColHeader label="G" tip="Gold reserves dimension score (0–40 pts). Calculated from: QoQ decline magnitude (0–20 pts) + consecutive declining quarters (0–20 pts). Selling gold alongside Treasuries activates the cross-asset multiplier." align="right" style={compactHead} />
                    <ColHeader label="Spread" tip="Sovereign bond yield spread vs the US 10Y, in basis points. MEASURED ONLY \u2014 D-0066 retired this dimension from scoring: it awarded points for trading more than 50bps ABOVE the US 10Y, and held yields for only fourteen developed markets, every one of which trades BELOW it. It scored 0 points for 0 countries. The number is still worth seeing; it no longer earns any." align="right" style={compactHead} />
                    <ColHeader label="P" tip="Petrodollar dimension score (0–20 pts). Only fires for oil-dependent nations (Gulf, Russia/CIS, Nigeria, etc.). Brent down >10% over 3M = 5 pts; >20% = 10 pts; >30% = 20 pts. +5 pts if oil falling AND country is selling Treasuries simultaneously." align="right" style={compactHead} />
                    <ColHeader label="CDS 5Y" tip={`Latest 5-year sovereign CDS spread in basis points \u2014 the market price of default protection (dimension 7). ${cdsBandText()}; +5 pts if widening >20% over 3M. A dash means no usable quote: either the sovereign is not on the board, or the quote was refused as stale or as not a running spread. The dimension then contributes 0 and is NOT counted as calm.`} align="right" style={compactHead} />
                    <ColHeader label="Mult" tip="Score multiplier applied to the raw total. 1.5× activates when a country sells both Treasuries and gold (cross-asset stress). 2.0× activates when selling gold into a rising spot price (divergence = forced seller signal)." align="right" style={compactHead} />
                    <ColHeader label="Non-$" tip="Non-dollar reserve trend (TRESEG series). STA = stable; REB = rebuilding (>5% YoY growth, de-dollarization into alternative system); DEP = depleting (>5% YoY decline, possible distress). Only analytically significant for EXITED countries." align="right" style={compactHead} />
                    <ColHeader label="Score" tip="Final composite score after multipliers. WATCH <25 · ELEVATED 25–50 · STRESSED 50–75 · CRISIS ≥75. Raw maximum is 165 across five dimensions; multipliers can take the result to the 150 cap." align="right" style={compactHead} />
                    <ColHeader label="Activity" tip="Human-readable summary of the specific signals contributing to this country's score. Each dot-separated entry corresponds to a threshold being crossed in one of the seven scoring dimensions." align="left" style={{ ...compactHead, ...activitySticky, zIndex: 3 }} />
                  </tr>
                </thead>
                <tbody>
                  {displayData.map(c => {
                    const tc = TIER_COLORS[c.tier] || "#5A6878";
                    return (
                      <tr key={c.country_iso}
                        onClick={() => onCountrySelect(c.country_iso)}
                        style={{ borderBottom:"1px solid #0F1923", cursor:"pointer" }}
                        onMouseEnter={e => {
                          e.currentTarget.style.background="#0D1820";
                          const activityCell = e.currentTarget.lastElementChild;
                          if (activityCell) activityCell.style.background="#0D1820";
                        }}
                        onMouseLeave={e => {
                          e.currentTarget.style.background="transparent";
                          const activityCell = e.currentTarget.lastElementChild;
                          if (activityCell) activityCell.style.background="#0A1520";
                        }}>
                        <td style={{ padding:"7px 8px", fontFamily:"monospace", fontSize:12, color:"#E8E0D0", textAlign:"left", whiteSpace:"normal", overflowWrap:"break-word" }}>
                          <div style={{ lineHeight:1.25 }}>{c.country_name}</div>
                          <div style={{ fontSize:10, color:"#3A4D5C", marginTop:1 }}>{c.country_iso}</div>
                        </td>
                        <td style={{ padding:"7px 8px" }}>
                          <span style={{ fontFamily:"monospace", fontSize:10, color:tc, background:`${tc}18`, border:`1px solid ${tc}44`, borderRadius:2, padding:"1px 5px" }}>{c.tier}</span>
                        </td>
                        <td style={{ padding:"7px 8px", fontFamily:"monospace", fontSize:11, textAlign:"right", color:(c.tic_mom_pct??0)<0?"#E07B5A":"#5DB87A" }}>
                          {c.no_tic_holdings
                            ? <span style={{ color:"#FF4444", fontSize:10 }}>ZERO ⚠</span>
                            : c.tic_mom_pct!=null?`${c.tic_mom_pct>0?"+":""}${c.tic_mom_pct.toFixed(1)}%`:"—"}
                        </td>
                        <td style={{ padding:"7px 8px", fontFamily:"monospace", fontSize:11, textAlign:"right", color:(c.tic_consecutive_months??0)>=3?"#E07B5A":"#8A9BAC" }}>
                          {(c.tic_consecutive_months??0)>0?`${c.tic_consecutive_months}mo`:"—"}
                        </td>
                        <td style={{ padding:"7px 8px", fontFamily:"monospace", fontSize:11, textAlign:"right", color:c.selling_gold?"#E07B5A":"#5A6878" }}>
                          {c.gold_tonnes!=null?`${c.gold_tonnes.toLocaleString()}`:"—"}
                        </td>
                        <td style={{ padding:"7px 8px", fontFamily:"monospace", fontSize:11, textAlign:"right", color:"#C8A96E" }}>{c.tic_score?.toFixed(0)??0}</td>
                        <td style={{ padding:"7px 8px", fontFamily:"monospace", fontSize:11, textAlign:"right", color:"#E8C547" }}>{c.gold_score?.toFixed(0)??0}</td>
                        <td style={{ padding:"7px 8px", fontFamily:"monospace", fontSize:11, textAlign:"right", color:(c.spread_bps??0)>50?"#7EB8C9":"#3A4D5C" }}>
                          {c.spread_bps!=null?`${c.spread_bps>0?"+":""}${c.spread_bps.toFixed(0)}`:"—"}
                        </td>
                        <td style={{ padding:"7px 8px", fontFamily:"monospace", fontSize:11, textAlign:"right", color:(c.petro_score??0)>0?"#E07B5A":"#3A4D5C" }}>
                          {c.oil_dependent?(c.petro_score>0?c.petro_score:"🛢"):"—"}
                        </td>
                        <td style={{ padding:"7px 8px", fontFamily:"monospace", fontSize:11, textAlign:"right", color:c.cds_5y!=null?(c.cds_5y>250?"#E07B5A":c.cds_5y>100?"#C8A96E":"#7EB8C9"):"#3A4D5C" }}>
                          {c.cds_5y!=null?`${c.cds_5y.toFixed(0)}`:<span style={{ color:"#3A4D5C" }} title="No CDS coverage — dimension scores 0">—</span>}
                        </td>
                        <td style={{ padding:"7px 8px", fontFamily:"monospace", fontSize:11, textAlign:"right", color:(c.multiplier??1)>1?"#FF4444":"#3A4D5C" }}>
                          {(c.multiplier??1)>1?`${c.multiplier}×`:"—"}
                        </td>
                        <td style={{ padding:"7px 8px", fontFamily:"monospace", fontSize:10, textAlign:"right", color:c.treseg_signal==="REBUILDING"?"#FF4444":c.treseg_signal==="DEPLETING"?"#E07B5A":"#3A4D5C", whiteSpace:"nowrap" }}>
                          {c.treseg_signal&&c.treseg_signal!=="NO_DATA" ? `${c.treseg_signal.slice(0,3)} ${c.treseg_trend_pct!=null?(c.treseg_trend_pct>0?"+":"")+c.treseg_trend_pct+"%":""}` : "—"}
                        </td>
                        <td style={{ padding:"7px 8px" }}>
                          <div style={{ display:"flex", alignItems:"center", gap:6 }}>
                            <div style={{ flex:1, minWidth:0, background:"#0F1923", borderRadius:2, height:5, overflow:"hidden" }}>
                              <div style={{ width:`${Math.min(100,c.composite_score)}%`, background:tc, height:"100%", borderRadius:2 }} />
                            </div>
                            <span style={{ fontFamily:"monospace", fontSize:11, color:tc, minWidth:28, textAlign:"right", fontWeight:700 }}>{c.composite_score?.toFixed(0)??0}</span>
                            {c.cds_5y==null && (
                              <span title="Score computed without CDS input — no sovereign CDS coverage for this country"
                                style={{ fontSize:9, color:"#5A6878", cursor:"help", marginLeft:1 }}>◦</span>
                            )}
                          </div>
                        </td>
                        <td style={{ padding:"7px 10px", fontFamily:"monospace", fontSize:11, color:"#5A6878", textAlign:"left", whiteSpace:"normal", overflowWrap:"break-word", wordBreak:"break-word", lineHeight:1.45, minWidth:170, maxWidth:240, ...activitySticky }}
                          title={(c.active_signals||[]).join(" · ") || undefined}>
                          {(c.active_signals||[]).join(" · ") || "—"}
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
      <div style={{ marginTop:12, fontFamily:"monospace", fontSize:11, color:"#1E2D3D" }}>
        Data as of {data.as_of} · Sources: US Treasury TIC · World Gold Council · FRED
      </div>
    </div>
  );
}


// ── Gold Reserves Tab ────────────────────────────────────────────────────────
