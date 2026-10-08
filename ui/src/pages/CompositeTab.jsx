import { useState } from "react";
import { coverageBadge } from "../lib/coverage";
import { AllOtherStrip } from "../components/AllOtherStrip";
import { ForeignOfficialStrip } from "../components/ForeignOfficialStrip";
import { useApiResource } from "../hooks/useApiResource";
import { MAX_RAW_SCORE, STRESS_DIMENSIONS, STRESS_MULTIPLIERS, cdsBandText } from "../lib/dimensions";
import { DataAsOf } from "../components/DataAsOf";
import { DataConfidence } from "../components/DataConfidence";
import { AlertBanner } from "../components/AlertBanner";
import { ColHeader } from "../components/ColHeader";
import { InfoTip } from "../components/InfoTip";
import { LoadFailure } from "../components/LoadFailure";
import { CountryLink } from "../components/CountryLink";
import { navigateToCountry } from "../lib/countryRoute";

export function CompositeTab() {
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

      {/* D-0074: the composite is the sum of five dimensions drawn from
          six sources of very different vintage. A single "as of" at the
          foot of the table cannot say that. */}
      <DataConfidence
        sourceKeys={["tic", "gold_reserves", "money_supply", "oil", "cds", "sovereign_yields"]}
        label="Score inputs"
      />

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

      {/* D-0079 / A-0019 option 2. Once, above the table, never on a row:
          All Other covers ~100 holders and a move says someone reduced, not
          who. Beside a country it would invite the reading that cost 1,050
          points across 32 countries (F-0097). */}
      <ForeignOfficialStrip signal={summary?.foreign_official} />
      <AllOtherStrip signal={summary?.all_other} />

      {/* Summary cards */}
      <div style={{ display:"flex", gap:12, marginBottom:20, flexWrap:"wrap" }}>
        {[
          { label:"CRISIS", val:summary?.crisis??0, color:"#FF4444", desc:"Score ≥ 75",
            tip:"Countries with a composite score of 75 or more. The composite is the raw score across the scored dimensions (out of 165), times a multiplier: ×1.5 when Treasuries and gold are both being sold, ×2.0 when gold is sold into a rising gold price. A country that has exited Treasuries while rebuilding its non-gold reserves gets a further ×1.2, capped at 150." },
          { label:"STRESSED", val:summary?.stressed??0, color:"#E07B5A", desc:"Score 50–75",
            tip:"Countries with a composite score of at least 50 and below 75: the raw score across the scored dimensions, times any multiplier, as for CRISIS." },
          { label:"ELEVATED", val:summary?.elevated??0, color:"#E8C547", desc:"Score 25–50",
            tip:"Countries with a composite score of at least 25 and below 50." },
          { label:"WATCH", val:summary?.watch??0, color:"#5A6878", desc:"Score < 25",
            tip:"Countries scoring above zero but below 25. A country scoring exactly zero is left off the board, unless it has exited Treasuries, in which case it is always listed." },
          // D-0091: the tile opens the highest-risk country's card.
          { label:"Top Risk", val:summary?.highest_risk
              ? <CountryLink iso={summary.highest_risk.country_iso} name={summary.highest_risk.country_name} showCode={false} />
              : "—", color:"#C8A96E", desc:`Score: ${summary?.highest_risk?.composite_score?.toFixed(0)??"—"}`,
            tip:"The country with the highest composite score in the stored snapshot. The snapshot is recomputed nightly at 04:45 UTC, or on POST /api/snapshot/composite (D-0042). Click to open its card (D-0091)." },
        ].map(s => (
          <div key={s.label} style={{ background:"#0F1923", border:`1px solid ${(s.val>0&&s.label!=="Top Risk")?`${s.color}33`:"#1A2530"}`, borderTop:`2px solid ${(s.val>0||s.label==="Top Risk")?s.color:"#1A2530"}`, borderRadius:2, padding:"14px 20px", flex:"1 1 140px" }}>
            <InfoTip title={s.label} tip={s.tip} placement="below" as="div" style={{ fontFamily:"monospace", fontSize:10, color:"#5A6878", textTransform:"uppercase", letterSpacing:"0.1em", marginBottom:4 }}>
              <span style={{ borderBottom:"1px dashed #2A3D50", paddingBottom:1 }}>{s.label}</span>
            </InfoTip>
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
                {/* F-0086: exactly one <col> per column.
                    There were fifteen for fourteen columns after D-0062
                    removed CDS Term. The browser maps the first fourteen and
                    drops the last - so Activity inherited Score's 86px slot,
                    the intended auto-width column was discarded, and because
                    the specified widths summed to 828px against a full-width
                    table the browser inflated every column proportionally to
                    make up the difference. That inflation is the empty space.

                    Sized to content now, with the prose column unsized so it
                    takes the slack rather than every column taking a share of
                    it. */}
                <colgroup>
                  <col style={{ width: 132 }} />{/* Country + ISO; "United Arab Emirates" is the longest */}
                  <col style={{ width: 84 }} />{/* Tier badge */}
                  <col style={{ width: 76 }} />{/* T-Bill MoM, or "ZERO" */}
                  <col style={{ width: 74 }} />{/* Tx 3mo - net transactions */}
                  <col style={{ width: 52 }} />{/* Consec */}
                  <col style={{ width: 62 }} />{/* Gold t */}
                  <col style={{ width: 40 }} />{/* T */}
                  <col style={{ width: 40 }} />{/* G */}
                  <col style={{ width: 58 }} />{/* Spread */}
                  <col style={{ width: 40 }} />{/* P */}
                  <col style={{ width: 58 }} />{/* CDS 5Y */}
                  <col style={{ width: 46 }} />{/* Mult */}
                  <col style={{ width: 78 }} />{/* Non-$ */}
                  <col style={{ width: 96 }} />{/* Score: bar + number + marker */}
                  <col />{/* Activity - takes the remainder */}
                </colgroup>
                <thead>
                  <tr>
                    <ColHeader label="Country" tip="Sovereign entity scored across five stress dimensions. A ◦ marker beside the score means no usable CDS quote for that country, so the score reflects four. Click any row to open the full country detail view." align="left" style={compactHead} />
                    <ColHeader label="Tier" tip="Risk classification based on composite score: WATCH (<25), ELEVATED (25–50), STRESSED (50–75), CRISIS (≥75). CRISIS requires all major signals firing plus a multiplier." align="left" style={compactHead} />
                    <ColHeader label="T-Bill MoM" tip="Month-over-month % change in US Treasury HOLDINGS. Holdings move with price as well as transactions, so this column alone cannot tell selling from repricing — the next column can. 'ZERO ⚠' means a reported position of zero; 'n/r' means not in the current release (F-0097)." align="right" style={compactHead} />
                    <ColHeader label="Tx 3mo" tip="Net transactions over three months, in billions — what the country actually bought or sold, with price stripped out. Japan's holdings moved -1.15% last month while it sold $88.6bn over the quarter, almost all of it Treasury bills; the percentage column cannot show that (F-0099, D-0084). A figure pointing the opposite way from T-Bill MoM means that month's holdings move was price, not posture." align="right" style={compactHead} />
                    <ColHeader label="Consec" tip="Consecutive months of declining Treasury HOLDINGS. Each adds 4 pts to the Treasury score, capped at 5 months (20 pts). Persistence distinguishes strategic selling from noise." align="right" style={compactHead} />
                    <ColHeader label="Gold t" tip="Central bank gold reserves in metric tonnes, from the IMF's monthly IRFCL return (D-0076). Context for the gold score: large reserves + selling = higher stress than small reserves + selling." align="right" style={compactHead} />
                    <ColHeader label="T" tip="Treasury dimension score (0–50 pts), the highest-weight dimension. Magnitude (0–30) is the WORSE of two three-month lenses: the fall in the total position (1.5 pts per %, so −20% earns the full 30) or the drawdown in the country's Treasury BILL book from its 3-month peak (0.6 pts per %, so a 50% liquidation earns 30). The bill book is where a sovereign raises dollars first. The result is weighted 1.0×–1.5× by the country's share of all foreign holdings, so $1bn of selling is no longer worth 337× more to a small holder than to Japan (F-0099). Persistence adds 4 pts per consecutive declining month, capped at 20. The total-position magnitude is suppressed where the fall was price rather than selling (A-0021). See D-0084." align="right" style={compactHead} />
                    <ColHeader label="G" tip="Gold reserves dimension score (0–40 pts): QoQ decline magnitude (0–20) + consecutive declining quarters (4 pts each, capped at 5 quarters = 20). The source is now the IMF's monthly IRFCL return rather than a quarterly download (D-0076), so the series is resampled to one reading per calendar quarter — otherwise three monthly dips would score as three quarters (F-0094). Selling gold alongside Treasuries activates the cross-asset multiplier." align="right" style={compactHead} />
                    <ColHeader label="Spread" tip="Sovereign bond yield spread vs the US 10Y, in basis points. MEASURED ONLY \u2014 D-0066 retired this dimension from scoring: it awarded points for trading more than 50bps ABOVE the US 10Y, and held yields for only fourteen developed markets, every one of which trades BELOW it. It scored 0 points for 0 countries. The number is still worth seeing; it no longer earns any." align="right" style={compactHead} />
                    <ColHeader label="P" tip="Petrodollar dimension score (0–20 pts). Only fires for oil-dependent nations (Gulf, Russia/CIS, Nigeria, etc.). Brent down >10% over 3M = 5 pts; >20% = 10 pts; >30% = 20 pts. +5 pts if oil falling AND country is selling Treasuries simultaneously." align="right" style={compactHead} />
                    <ColHeader label="CDS 5Y" tip={`Latest 5-year sovereign CDS spread in basis points \u2014 the market price of default protection (dimension 7). ${cdsBandText()}; +5 pts if widening >20% over 3M. A dash means no usable quote: either the sovereign is not on the board, or the quote was refused as stale or as not a running spread. The dimension then contributes 0 and is NOT counted as calm.`} align="right" style={compactHead} />
                    <ColHeader label="Mult" tip="Score multiplier applied to the raw total. 1.5× activates when a country sells both Treasuries and gold (cross-asset stress). 2.0× activates when selling gold into a rising spot price (divergence = forced seller signal)." align="right" style={compactHead} />
                    <ColHeader label="Non-$" tip="Non-dollar reserve trend (TRESEG series). STA = stable; REB = rebuilding (>5% YoY growth, de-dollarization into alternative system); DEP = depleting (>5% YoY decline, possible distress). Only analytically significant for EXITED countries." align="right" style={compactHead} />
                    <ColHeader label="Score" tip="Final composite score after multipliers. WATCH <25 · ELEVATED 25–50 · STRESSED 50–75 · CRISIS ≥75. Raw maximum is 165 across five dimensions; multipliers can take the result to the 150 cap. A marker beside the score counts the dimensions that cannot be scored for that country at all — hover it for which and why. The Treasury dimension, worth 50 of the 165, reaches only the twenty countries SLT Table 5 names (A-0019), so two countries with the same score may have been measured on different amounts of evidence." align="right" style={compactHead} />
                    <ColHeader label="Activity" tip="Human-readable summary of the specific signals contributing to this country's score. Each dot-separated entry corresponds to a threshold being crossed in one of the seven scoring dimensions." align="left" style={{ ...compactHead, ...activitySticky, zIndex: 3 }} />
                  </tr>
                </thead>
                <tbody>
                  {displayData.map(c => {
                    const tc = TIER_COLORS[c.tier] || "#5A6878";
                    return (
                      <tr key={c.country_iso}
                        onClick={() => navigateToCountry(c.country_iso)}
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
                          {/* D-0091: a real link to the same card the row opens,
                              so the name is reachable by keyboard and has a URL. */}
                          <CountryLink iso={c.country_iso} name={c.country_name}
                            style={{ display:"block", lineHeight:1.25 }}
                            codeStyle={{ display:"block", marginLeft:0, marginTop:1 }} />
                        </td>
                        <td style={{ padding:"7px 8px" }}>
                          <span style={{ fontFamily:"monospace", fontSize:10, color:tc, background:`${tc}18`, border:`1px solid ${tc}44`, borderRadius:2, padding:"1px 5px" }}>{c.tier}</span>
                        </td>
                        <td style={{ padding:"7px 8px", fontFamily:"monospace", fontSize:11, textAlign:"right", color:(c.tic_mom_pct??0)<0?"#E07B5A":"#5DB87A" }}>
                          {/* F-0097: this read ZERO for Germany at $103.1bn. Absence from
                              SLT Table 5's twenty named holders means "inside All Other",
                              not "holds nothing". */}
                          {c.no_tic_holdings
                            ? <span style={{ color:"#FF4444", fontSize:10 }}>ZERO ⚠</span>
                            : c.tic_state==="below_threshold"
                              ? <span style={{ color:"#5A6878", fontSize:10 }} title={`Below TIC reporting threshold — last reported $${c.tic_last_reported_bn}bn on ${c.tic_last_reported_date}`}>n/r</span>
                              : c.tic_state==="no_data"
                                ? <span style={{ color:"#3A4D5C", fontSize:10 }} title="Never among the reported holders">—</span>
                              : c.tic_state==="never_held"
                                ? <span style={{ color:"#3A4D5C", fontSize:10 }} title="Never held $1bn of Treasuries, so there was no position to exit (D-0106)">—</span>
                                : c.tic_mom_pct!=null?`${c.tic_mom_pct>0?"+":""}${c.tic_mom_pct.toFixed(1)}%`:"—"}
                        </td>
                        <td style={{ padding:"7px 8px", fontFamily:"monospace", fontSize:11, textAlign:"right" }}>
                          {/* D-0084. The dollars actually transacted, beside the
                              percentage the score reads. Coloured by direction,
                              and gold when it contradicts the holdings move. */}
                          {c.tic_net_3m_bn == null
                            ? <span style={{ color:"#3A4D5C" }}>—</span>
                            : (() => {
                                const v = c.tic_net_3m_bn;
                                const contra = c.tic_price_driven && (c.tic_3m_pct ?? 0) < 0;
                                return (
                                  <span
                                    title={contra
                                      ? `Holdings fell but transactions were ${v >= 0 ? "positive" : "small relative to valuation"} — the Treasury magnitude is not scored for this country (A-0021).`
                                      : `Net transactions over three months.`}
                                    style={{ color: contra ? "#C8A96E" : v < 0 ? "#E07B5A" : "#5DB87A", cursor: "help" }}>
                                    {`${v > 0 ? "+" : v < 0 ? "−" : ""}$${Math.abs(v).toFixed(1)}`}
                                  </span>
                                );
                              })()}
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
                            {/* A-0019. Was a CDS-only marker. One badge now for
                                every dimension that cannot speak about this
                                country — dimension 1 reaches only the twenty
                                countries TIC names (F-0097), and a score built
                                from two dimensions means something different
                                from the same score built from five. Muted on
                                purpose: this is a limit on what the number
                                means, not a finding about the country. */}
                            {(() => {
                              const badge = coverageBadge(c);
                              return badge && (
                                <span title={badge.title}
                                  style={{ fontSize:9, color:"#5A6878", cursor:"help", marginLeft:2 }}>{badge.text}</span>
                              );
                            })()}
                          </div>
                        </td>
                        <td style={{ padding:"7px 10px", fontFamily:"monospace", fontSize:11, color:"#5A6878", textAlign:"left", whiteSpace:"normal", overflowWrap:"break-word", wordBreak:"break-word", lineHeight:1.45, ...activitySticky }}
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
        <DataAsOf
          asOf={data.as_of}
          source="US Treasury TIC · IMF IRFCL · World Bank · FRED · World Government Bonds"
          style={{ marginTop: 0 }}
        />
      </div>
    </div>
  );
}


// ── Gold Reserves Tab ────────────────────────────────────────────────────────
