import { useState, useEffect } from "react";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, ReferenceLine } from "recharts";
import { apiFetch } from "../lib/api";
import { buildYieldSeries } from "../lib/yieldSeries";
import { formatDate } from "../lib/format";
import { ColHeader } from "../components/ColHeader";

export function USADashboard() {
  const [data, setData] = useState({});
  const [range, setRange] = useState(365 * 5);
  const [scenario, setScenario] = useState(null);
  const [customRate, setCustomRate] = useState(null);

  useEffect(() => {
    const end = new Date();
    const start = new Date();
    start.setDate(start.getDate() - range);
    const codes = "DGS30,DGS10,DGS2,DGS5,FEDFUNDS,DFII10,DTWEXBGS,CPIAUCSL,M2SL,GOLD_SPOT_USD";
    apiFetch(`/timeseries?metric_codes=${codes}&start_date=${start.toISOString()}&end_date=${end.toISOString()}`)
      .then(r => r.json())
      .then(raw => {
        const byMetric = {};
        raw.forEach(({ date, value, metric_code }) => {
          if (!byMetric[metric_code]) byMetric[metric_code] = [];
          byMetric[metric_code].push({ date: date.split("T")[0], value: parseFloat(value) });
        });
        setData(byMetric);
      }).catch(() => {});
  }, [range]);

  const latest = (code) => {
    const s = data[code]; if (!s?.length) return null;
    return s[s.length - 1].value;
  };

  const yoy = (code) => {
    const s = data[code]; if (!s?.length) return null;
    const last = s[s.length - 1].value;
    const ago = s.find(d => { const diff = (new Date(s[s.length-1].date) - new Date(d.date))/(86400000); return diff>=340&&diff<=400; });
    if (!ago) return null;
    return ((last - ago.value) / Math.abs(ago.value)) * 100;
  };

  const dgs10 = latest("DGS10");
  const dgs2 = latest("DGS2");
  const fedfunds = latest("FEDFUNDS");
  const realYield = latest("DFII10");
  const spread = dgs10!=null&&dgs2!=null ? dgs10-dgs2 : null;
  const m2Yoy = yoy("M2SL");
  const m2Latest = latest("M2SL");
  const cpiYoy = yoy("CPIAUCSL");
  const dxyLatest = latest("DTWEXBGS");

  // ── Fiscal breaking point calculator ────────────────────────────────────────
  // Constants (FY2024 actuals / CBO estimates)
  const ANNUAL_REVENUE_T = 4.9;       // $T federal revenue
  const ANNUAL_ROLLOVER_T = 6.0;      // $T debt rolling over annually (~avg 6Y maturity)
  const LOCKED_IN_INTEREST_T = 0.55;  // $T already locked in at existing rates
  const SPR_CURRENT_MB = 370;         // Million barrels current
  const SPR_CAPACITY_MB = 714;        // Million barrels capacity
  const US_GOLD_TONNES = 8133;        // Tonnes (unchanged since 1971)
  const US_GOLD_TROY_OZ = 261.5e6;    // Troy ounces
  // F-0057: was a hardcoded 4587. GOLD_SPOT_USD is a live daily series
  // (D-0041) and the page already queries this API, so a frozen constant
  // here was stating US gold holdings against a months-old price. No
  // fallback constant: if the series is missing the tile shows nothing
  // rather than a plausible wrong number.
  const spotGold = latest("GOLD_SPOT_USD");

  const calcInterestCost = (yieldRate) => {
    // New debt issued this year at new yield, rest at existing average rate
    const newDebtCost = ANNUAL_ROLLOVER_T * (yieldRate / 100);
    return LOCKED_IN_INTEREST_T + newDebtCost;
  };

  const breakingPointRate = () => {
    // When does interest / revenue hit 25% (emerging market danger zone)?
    // LOCKED_IN + ROLLOVER * rate = 0.25 * REVENUE
    // rate = (0.25 * REVENUE - LOCKED_IN) / ROLLOVER
    return ((0.25 * ANNUAL_REVENUE_T - LOCKED_IN_INTEREST_T) / ANNUAL_ROLLOVER_T) * 100;
  };

  const crisisRate = () => {
    // When does interest hit 35% of revenue? (Japan-level crisis)
    return ((0.35 * ANNUAL_REVENUE_T - LOCKED_IN_INTEREST_T) / ANNUAL_ROLLOVER_T) * 100;
  };

  const BREAK = breakingPointRate(); // ~5.5%
  const CRISIS = crisisRate();       // ~8.5%

  const activeYield = customRate ?? dgs10 ?? 4.3;
  const activeInterest = calcInterestCost(activeYield);
  const activeInterestPct = (activeInterest / ANNUAL_REVENUE_T) * 100;

  const dangerColor = activeYield >= CRISIS ? "#FF4444" : activeYield >= BREAK ? "#E07B5A" : activeYield >= BREAK - 1 ? "#E8C547" : "#5DB87A";

  const SCENARIOS = [
    { label: "Hold (4%)", ff: 4.0, color: "#5A6878", desc: "Status quo. Yield curve flat. Deficit serviceable but growing. Foreign holders reducing slowly." },
    { label: "Cut to 2%", ff: 2.0, color: "#E8C547", desc: "Moderate easing. Long end likely rises 50-100bps — bear steepener. Dollar weakens. Foreign selling continues." },
    { label: "Cut to 1%", ff: 1.0, color: "#E07B5A", desc: "Aggressive signal. Long end rises 100-200bps. Dollar weakens sharply. Foreign holders accelerate selling. Deficit widens as long-term borrowing costs stay high." },
    { label: "Cut to 0% (ZIRP)", ff: 0.0, color: "#FF4444", desc: "2020-2022 playbook: M2 surged 27%, CPI hit 9%, 10Y rose from 0.5% to 3.5%. The bond market doesn't care what the Fed says." },
  ];

  // Build chart data. The date join lives in lib/yieldSeries.js so it can be
  // tested (F-0007, F-0053); it used to be an inline index zip here.
  const yieldData = buildYieldSeries(data);

  const m2Data = (data["M2SL"]||[]).map(d => ({ date: d.date, value: d.value }));
  const m2YoyData = m2Data.map((d, i) => {
    if (i < 12) return { date: d.date, growth: null };
    const ago = m2Data[i-12];
    return { date: d.date, growth: ago ? ((d.value - ago.value)/ago.value*100) : null };
  }).filter(d => d.growth != null);

  // Interest cost table
  const RATE_TABLE = [3.5, 4.0, 4.5, 5.0, 5.5, 6.0, 7.0, 8.0].map(r => ({
    rate: r,
    cost: calcInterestCost(r),
    pct: (calcInterestCost(r) / ANNUAL_REVENUE_T * 100),
  }));

  return (
    <div>
      {/* Header */}
      <div style={{ marginBottom: 20 }}>
        <div style={{ fontFamily: "monospace", fontSize: 20, color: "#E8E0D0", fontWeight: 700, marginBottom: 4 }}>
          United States of America
          <span style={{ marginLeft: 12, fontSize: 11, color: "#3A4D5C" }}>USA · Treasury Issuer · Reserve Currency</span>
        </div>
        <div style={{ fontFamily: "monospace", fontSize: 11, color: "#5A6878", lineHeight: 1.7, maxWidth: 860 }}>
          The US is the <span style={{ color: "#C8A96E" }}>issuer</span> of the reserve asset being monitored globally.
          US stress is not forced selling — it's the Fed's ability to manage <span style={{ color: "#C8A96E" }}>$36T in debt</span> as
          foreign demand weakens, the dollar debasement math, and whether the bond market will accept the terms the Fed is offering.
        </div>
      </div>

      {/* Range */}
      <div style={{ display: "flex", gap: 6, marginBottom: 20 }}>
        {[[365,"1Y"],[730,"2Y"],[1825,"5Y"],[3650,"10Y"]].map(([d,l]) => (
          <button key={l} onClick={() => setRange(d)} style={{ background: range===d?"#1A2530":"transparent", border:`1px solid ${range===d?"#5A6878":"#1E2D3D"}`, color:range===d?"#C8A96E":"#3A4D5C", borderRadius:2, padding:"4px 12px", cursor:"pointer", fontFamily:"monospace", fontSize:11 }}>{l}</button>
        ))}
      </div>

      {/* Key metrics row */}
      <div style={{ display: "flex", gap: 10, marginBottom: 20, flexWrap: "wrap" }}>
        {[
          { label: "10Y Yield", val: dgs10!=null?`${dgs10.toFixed(2)}%`:"—", color: "#C8A96E", sub: spread!=null?`Spread vs 2Y: ${spread>0?"+":""}${spread.toFixed(2)}pp`:"" },
          { label: "Fed Funds", val: fedfunds!=null?`${fedfunds.toFixed(2)}%`:"—", color: "#5DB87A", sub: "" },
          { label: "Real Yield", val: realYield!=null?`${realYield.toFixed(2)}%`:"—", color: realYield!=null&&realYield<0?"#E07B5A":"#7EB8C9", sub: realYield!=null&&realYield<0?"⚠ Financial repression":"Positive" },
          { label: "M2 Growth YoY", val: m2Yoy!=null?`${m2Yoy.toFixed(1)}%`:"—", color: m2Yoy!=null&&m2Yoy>10?"#E07B5A":m2Yoy!=null&&m2Yoy>5?"#E8C547":"#5DB87A", sub: m2Yoy!=null?`$${(m2Latest/1000).toFixed(1)}T total`:"" },
          { label: "CPI YoY", val: cpiYoy!=null?`${cpiYoy.toFixed(1)}%`:"—", color: cpiYoy!=null&&cpiYoy>4?"#E07B5A":cpiYoy!=null&&cpiYoy>2?"#E8C547":"#5DB87A", sub: cpiYoy!=null&&cpiYoy>2?"Above 2% target":"" },
          { label: "Dollar Index", val: dxyLatest!=null?dxyLatest.toFixed(1):"—", color: "#7EC4A0", sub: "" },
          { label: "US Gold", val: `${US_GOLD_TONNES.toLocaleString()}t`, color: "#C8A96E", sub: spotGold != null ? `$${((US_GOLD_TROY_OZ * spotGold)/1e12).toFixed(2)}T at $${spotGold.toFixed(0)}/oz` : "spot price unavailable" },
          { label: "SPR Level", val: `${SPR_CURRENT_MB}M bbl`, color: SPR_CURRENT_MB < 400 ? "#E07B5A" : "#5DB87A", sub: `${((SPR_CURRENT_MB/SPR_CAPACITY_MB)*100).toFixed(0)}% of capacity (${SPR_CAPACITY_MB}M)` },
        ].map(s => (
          <div key={s.label} style={{ background:"#0F1923", border:"1px solid #1A2530", borderTop:`2px solid ${s.color}`, borderRadius:2, padding:"12px 16px", flex:"1 1 130px" }}>
            <div style={{ fontFamily:"monospace", fontSize:10, color:"#5A6878", textTransform:"uppercase", letterSpacing:"0.1em", marginBottom:4 }}>{s.label}</div>
            <div style={{ fontFamily:"monospace", fontSize:18, fontWeight:700, color:s.color }}>{s.val}</div>
            {s.sub && <div style={{ fontFamily:"monospace", fontSize:10, color:"#5A6878", marginTop:3 }}>{s.sub}</div>}
          </div>
        ))}
      </div>

      {/* ── BREAKING POINT CALCULATOR ── */}
      <div style={{ background:"#0A1520", border:`1px solid ${dangerColor}44`, borderLeft:`3px solid ${dangerColor}`, borderRadius:2, padding:"20px 24px", marginBottom:20 }}>
        <div style={{ display:"flex", alignItems:"center", justifyContent:"space-between", marginBottom:16, flexWrap:"wrap", gap:12 }}>
          <div>
            <div style={{ fontFamily:"monospace", fontSize:12, color:"#8A9BAC", letterSpacing:"0.1em", marginBottom:4 }}>FISCAL BREAKING POINT CALCULATOR</div>
            <div style={{ fontFamily:"monospace", fontSize:11, color:"#5A6878" }}>
              At $36.2T debt · $6T rolling over annually · $4.9T revenue · Every 100bps = <span style={{ color:"#C8A96E" }}>+$60B/yr in new interest</span>
            </div>
          </div>
          <div style={{ display:"flex", alignItems:"center", gap:12 }}>
            <span style={{ fontFamily:"monospace", fontSize:11, color:"#5A6878" }}>Model 10Y at:</span>
            <input type="range" min="1" max="12" step="0.25" value={customRate ?? activeYield}
              onChange={e => setCustomRate(parseFloat(e.target.value))}
              style={{ width:140, accentColor:"#C8A96E" }} />
            <span style={{ fontFamily:"monospace", fontSize:14, color:"#C8A96E", minWidth:40 }}>{(customRate??activeYield).toFixed(2)}%</span>
            {customRate && <button onClick={() => setCustomRate(null)} style={{ background:"transparent", border:"1px solid #1E2D3D", color:"#3A4D5C", borderRadius:2, padding:"3px 8px", cursor:"pointer", fontFamily:"monospace", fontSize:10 }}>reset</button>}
          </div>
        </div>

        {/* Live readout */}
        <div style={{ display:"flex", gap:16, marginBottom:20, flexWrap:"wrap" }}>
          {[
            { label:"Annual Interest Cost", val:`$${activeInterest.toFixed(2)}T`, color:dangerColor },
            { label:"% of Federal Revenue", val:`${activeInterestPct.toFixed(1)}%`, color:dangerColor },
            { label:"Warning zone (25%)", val:`${BREAK.toFixed(1)}% yield`, color:"#E07B5A" },
            { label:"Crisis zone (35%)", val:`${CRISIS.toFixed(1)}% yield`, color:"#FF4444" },
            { label:"Distance to warning", val: dgs10!=null?(BREAK-(customRate??dgs10)>0?`+${(BREAK-(customRate??dgs10)).toFixed(2)}pp headroom`:`${(BREAK-(customRate??dgs10)).toFixed(2)}pp BREACHED`):"—", color: dgs10!=null&&(customRate??dgs10)>=BREAK?"#FF4444":"#5DB87A" },
          ].map(s => (
            <div key={s.label} style={{ background:"#0F1923", borderRadius:2, padding:"10px 16px", flex:"1 1 140px" }}>
              <div style={{ fontFamily:"monospace", fontSize:10, color:"#5A6878", marginBottom:4 }}>{s.label}</div>
              <div style={{ fontFamily:"monospace", fontSize:16, fontWeight:700, color:s.color }}>{s.val}</div>
            </div>
          ))}
        </div>

        {/* Rate table */}
        <table style={{ width:"100%", borderCollapse:"collapse", marginBottom:12 }}>
          <thead>
            <tr>
              <ColHeader label="10Y Yield" tip="Hypothetical 10-year Treasury yield scenario. The current live value is highlighted. Each row shows what happens to US debt service costs if the 10Y yield settles at this level." align="right" style={{ padding: "6px 12px" }} />
              <ColHeader label="Annual Interest" tip="Projected annual interest expense in trillions, calculated as: locked-in cost ($0.55T) + new rollover debt ($6T/yr) × this yield rate. Based on FY2024 actuals and CBO debt maturity estimates." align="right" style={{ padding: "6px 12px" }} />
              <ColHeader label="% of Revenue" tip="Interest expense as a percentage of projected federal revenue (~$4.9T/yr). The 25% threshold is considered the emerging-market danger zone. Above 35% is Japan-level fiscal stress." align="right" style={{ padding: "6px 12px" }} />
              <ColHeader label="Status" tip="Risk classification: OK = interest <20% of revenue (manageable); WATCH = 20–25% (monitor closely); DANGER = 25–35% (emerging market threshold crossed); CRISIS = >35% (debt spiral risk, Japan 2024 analog)." align="right" style={{ padding: "6px 12px" }} />
            </tr>
          </thead>
          <tbody>
            {RATE_TABLE.map(row => {
              const isCurrent = Math.abs(row.rate - (customRate??dgs10??4.3)) < 0.3;
              const isBreak = row.rate >= BREAK && row.rate < BREAK + 0.6;
              const isCrisis = row.rate >= CRISIS && row.rate < CRISIS + 0.6;
              const statusColor = row.pct >= 35 ? "#FF4444" : row.pct >= 25 ? "#E07B5A" : row.pct >= 20 ? "#E8C547" : "#5DB87A";
              const status = row.pct >= 35 ? "⚡ CRISIS" : row.pct >= 25 ? "⚠ DANGER" : row.pct >= 20 ? "WATCH" : "OK";
              return (
                <tr key={row.rate} style={{ background: isCurrent ? "#C8A96E0D" : "transparent", borderBottom:"1px solid #0F1923" }}>
                  <td style={{ padding:"7px 12px", fontFamily:"monospace", fontSize:12, color:isCurrent?"#C8A96E":"#E8E0D0", textAlign:"right", fontWeight:isCurrent?700:400 }}>
                    {row.rate.toFixed(1)}% {isCurrent?"← current":""} {isBreak?"← warning threshold":""} {isCrisis?"← crisis threshold":""}
                  </td>
                  <td style={{ padding:"7px 12px", fontFamily:"monospace", fontSize:12, color:"#8A9BAC", textAlign:"right" }}>${row.cost.toFixed(2)}T/yr</td>
                  <td style={{ padding:"7px 12px", fontFamily:"monospace", fontSize:12, color:statusColor, textAlign:"right" }}>{row.pct.toFixed(1)}%</td>
                  <td style={{ padding:"7px 12px", textAlign:"right" }}>
                    <span style={{ fontFamily:"monospace", fontSize:10, color:statusColor, background:`${statusColor}18`, border:`1px solid ${statusColor}44`, borderRadius:2, padding:"1px 6px" }}>{status}</span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        <div style={{ fontFamily:"monospace", fontSize:10, color:"#2A3540" }}>
          Assumptions: $36.2T total debt · $6T annual rollover · $4.9T revenue · $0.55T existing locked-in interest · Danger = 25% interest/revenue (EM threshold) · Crisis = 35% (Japan-level)
        </div>
      </div>

      {/* Yield curve chart */}
      {yieldData.length > 0 && (
        <div style={{ background:"#0A1520", border:"1px solid #1A2530", borderRadius:2, padding:"20px 24px", marginBottom:20 }}>
          <div style={{ fontFamily:"monospace", fontSize:10, color:"#3A4D5C", letterSpacing:"0.1em", marginBottom:16 }}>YIELD CURVE & RATE STRUCTURE</div>
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={yieldData} margin={{ top:4, right:8, bottom:4, left:8 }}>
              <CartesianGrid strokeDasharray="2 6" stroke="#0F1923" vertical={false} />
              <XAxis dataKey="date" tickFormatter={formatDate} tick={{ fill:"#3A4D5C", fontFamily:"monospace", fontSize:10 }} axisLine={false} tickLine={false} minTickGap={60} interval="preserveStartEnd" />
              <YAxis tick={{ fill:"#3A4D5C", fontFamily:"monospace", fontSize:10 }} axisLine={false} tickLine={false} width={40} tickFormatter={v=>`${v}%`} />
              <ReferenceLine y={BREAK} stroke="#E07B5A" strokeDasharray="4 4" strokeOpacity={0.5} label={{ value:`${BREAK.toFixed(1)}% warning`, fill:"#E07B5A66", fontFamily:"monospace", fontSize:9, position:"right" }} />
              <ReferenceLine y={0} stroke="#2A3540" strokeDasharray="3 3" />
              <Tooltip contentStyle={{ background:"#0A1520", border:"1px solid #1E2D3D", borderRadius:2, fontFamily:"monospace", fontSize:11 }} labelStyle={{ color:"#5A6878" }} labelFormatter={formatDate} formatter={(v,n)=>[`${v?.toFixed(2)}%`,n]} />
              <Legend wrapperStyle={{ fontFamily:"monospace", fontSize:10, color:"#5A6878", paddingTop:12 }} />
              <Line type="monotone" dataKey="30Y" stroke="#D4B06A" strokeWidth={1.5} dot={false} connectNulls />
              <Line type="monotone" dataKey="10Y" stroke="#C8A96E" strokeWidth={1.5} dot={false} connectNulls />
              <Line type="monotone" dataKey="2Y" stroke="#9B8EC4" strokeWidth={1.5} dot={false} connectNulls />
              <Line type="monotone" dataKey="Fed Funds" stroke="#5DB87A" strokeWidth={1.5} dot={false} connectNulls />
              <Line type="monotone" dataKey="Real Yield" stroke="#E8C547" strokeWidth={1} dot={false} connectNulls strokeDasharray="3 3" />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* M2 Growth chart */}
      {m2YoyData.length > 0 && (
        <div style={{ background:"#0A1520", border:"1px solid #1A2530", borderRadius:2, padding:"20px 24px", marginBottom:20 }}>
          <div style={{ display:"flex", alignItems:"center", gap:12, marginBottom:16 }}>
            <div style={{ fontFamily:"monospace", fontSize:10, color:"#3A4D5C", letterSpacing:"0.1em" }}>US M2 BROAD MONEY GROWTH (YoY %)</div>
            {m2Yoy!=null && <span style={{ fontFamily:"monospace", fontSize:10, color: m2Yoy>10?"#E07B5A":m2Yoy>5?"#E8C547":"#5DB87A", background:`${m2Yoy>10?"#E07B5A":m2Yoy>5?"#E8C547":"#5DB87A"}18`, border:`1px solid ${m2Yoy>10?"#E07B5A":m2Yoy>5?"#E8C547":"#5DB87A"}44`, borderRadius:2, padding:"1px 6px" }}>{m2Yoy.toFixed(1)}% current</span>}
          </div>
          <ResponsiveContainer width="100%" height={160}>
            <LineChart data={m2YoyData} margin={{ top:4, right:8, bottom:4, left:8 }}>
              <CartesianGrid strokeDasharray="2 6" stroke="#0F1923" vertical={false} />
              <XAxis dataKey="date" tickFormatter={formatDate} tick={{ fill:"#3A4D5C", fontFamily:"monospace", fontSize:10 }} axisLine={false} tickLine={false} minTickGap={60} interval="preserveStartEnd" />
              <YAxis tick={{ fill:"#3A4D5C", fontFamily:"monospace", fontSize:10 }} axisLine={false} tickLine={false} width={44} tickFormatter={v=>`${v.toFixed(0)}%`} />
              <ReferenceLine y={10} stroke="#E07B5A" strokeDasharray="4 4" strokeOpacity={0.5} label={{ value:"10%", fill:"#E07B5A66", fontFamily:"monospace", fontSize:9, position:"right" }} />
              <ReferenceLine y={0} stroke="#2A3540" strokeDasharray="3 3" />
              <Tooltip formatter={(v)=>[`${v?.toFixed(1)}%`,"M2 YoY"]} contentStyle={{ background:"#0A1520", border:"1px solid #1E2D3D", borderRadius:2, fontFamily:"monospace", fontSize:11 }} labelStyle={{ color:"#5A6878" }} labelFormatter={formatDate} />
              <Line type="monotone" dataKey="growth" stroke="#6A8FC4" strokeWidth={1.5} dot={false} connectNulls />
            </LineChart>
          </ResponsiveContainer>
          <div style={{ fontFamily:"monospace", fontSize:10, color:"#2A3540", marginTop:6 }}>The 2020-2022 surge (peak +27%) drove CPI to 9.1%. Current trajectory matters for foreign holders deciding whether dollar reserves are worth holding.</div>
        </div>
      )}

      {/* Rate scenario modeler */}
      <div style={{ background:"#0A1520", border:"1px solid #1A2530", borderRadius:2, padding:"20px 24px", marginBottom:20 }}>
        <div style={{ fontFamily:"monospace", fontSize:10, color:"#3A4D5C", letterSpacing:"0.1em", marginBottom:4 }}>RATE CUT SCENARIO ANALYSIS</div>
        <div style={{ fontFamily:"monospace", fontSize:11, color:"#5A6878", marginBottom:16 }}>The Fed controls the short end. The bond market controls the long end. These are not the same thing.</div>
        <div style={{ display:"flex", gap:8, marginBottom:16, flexWrap:"wrap" }}>
          {SCENARIOS.map(s => (
            <button key={s.label} onClick={() => setScenario(scenario?.label===s.label?null:s)}
              style={{ background:scenario?.label===s.label?`${s.color}18`:"transparent", border:`1px solid ${scenario?.label===s.label?s.color:"#1E2D3D"}`, color:scenario?.label===s.label?s.color:"#5A6878", borderRadius:2, padding:"6px 14px", cursor:"pointer", fontFamily:"monospace", fontSize:11 }}>
              {s.label}
            </button>
          ))}
        </div>
        {scenario ? (
          <div style={{ background:`${scenario.color}0D`, border:`1px solid ${scenario.color}33`, borderLeft:`3px solid ${scenario.color}`, borderRadius:2, padding:"16px 20px" }}>
            <div style={{ fontFamily:"monospace", fontSize:12, color:scenario.color, fontWeight:700, marginBottom:8 }}>{scenario.label}</div>
            <div style={{ fontFamily:"monospace", fontSize:12, color:"#8A9BAC", lineHeight:1.8, marginBottom:12 }}>{scenario.desc}</div>
            <div style={{ display:"flex", gap:20, flexWrap:"wrap" }}>
              {[
                { label:"Fed Funds Target", val:`${scenario.ff.toFixed(1)}%`, color:"#5DB87A" },
                { label:"Likely 10Y Response", val:scenario.ff<=0?"Rises 150-250bps":scenario.ff<=1?"Rises 100-200bps":scenario.ff<=2?"Rises 50-100bps":"Holds ±25bps", color:scenario.ff<=1?"#E07B5A":"#E8C547" },
                { label:"Yield Curve Shape", val:scenario.ff<=1?"Bear Steepener ⚠":scenario.ff<=2?"Steepens":"Flat", color:scenario.ff<=1?"#E07B5A":"#E8C547" },
                { label:"Dollar Effect", val:scenario.ff<=1?"Weakens sharply":scenario.ff<=2?"Weakens":"Stable", color:scenario.ff<=1?"#E07B5A":"#E8C547" },
                { label:"Foreign Selling", val:scenario.ff<=1?"Accelerates":"Continues", color:scenario.ff<=1?"#E07B5A":"#E8C547" },
                { label:"Breaking Point Risk", val:scenario.ff<=0?"CRISIS":scenario.ff<=1?"HIGH":"MODERATE", color:scenario.ff<=0?"#FF4444":scenario.ff<=1?"#E07B5A":"#E8C547" },
              ].map(s => (
                <div key={s.label}>
                  <div style={{ fontFamily:"monospace", fontSize:10, color:"#3A4D5C", marginBottom:2 }}>{s.label}</div>
                  <div style={{ fontFamily:"monospace", fontSize:12, color:s.color, fontWeight:600 }}>{s.val}</div>
                </div>
              ))}
            </div>
          </div>
        ) : (
          <div style={{ fontFamily:"monospace", fontSize:11, color:"#2A3540", padding:"8px 0" }}>Select a scenario to see bond market implications.</div>
        )}
      </div>

      {/* Doom loop */}
      <div style={{ background:"#0A1520", border:"1px solid #1A2530", borderRadius:2, padding:"20px 24px" }}>
        <div style={{ fontFamily:"monospace", fontSize:10, color:"#3A4D5C", letterSpacing:"0.1em", marginBottom:12 }}>THE FEEDBACK LOOP — HOW FOREIGN STRESS REACHES THE US</div>
        <div style={{ display:"flex", gap:6, flexWrap:"wrap", alignItems:"center", marginBottom:12 }}>
          {[
            { n:"1", t:"Foreign stress builds", d:"Countries need USD liquidity — sell Treasuries" },
            "→",
            { n:"2", t:"Treasury prices fall", d:"Yields rise as supply exceeds demand" },
            "→",
            { n:"3", t:"US borrowing costs rise", d:"$36T debt × higher yield = ballooning deficit" },
            "→",
            { n:"4", t:"More Treasuries issued", d:"To fund the expanding deficit" },
            "→",
            { n:"5", t:"Feedback tightens", d:"More supply → more yield pressure → back to step 2" },
          ].map((item, i) =>
            item === "→"
              ? <div key={i} style={{ fontFamily:"monospace", fontSize:16, color:"#1E2D3D" }}>→</div>
              : <div key={i} style={{ background:"#0F1923", border:"1px solid #1A2530", borderRadius:2, padding:"10px 12px", flex:"1 1 120px", marginBottom:6 }}>
                  <div style={{ fontFamily:"monospace", fontSize:10, color:"#C8A96E", marginBottom:3 }}>STEP {item.n}</div>
                  <div style={{ fontFamily:"monospace", fontSize:11, color:"#E8E0D0", fontWeight:600, marginBottom:2 }}>{item.t}</div>
                  <div style={{ fontFamily:"monospace", fontSize:10, color:"#5A6878" }}>{item.d}</div>
                </div>
          )}
        </div>
        <div style={{ fontFamily:"monospace", fontSize:11, color:"#3A4D5C", borderTop:"1px solid #1A2530", paddingTop:12 }}>
          Sentinel's stress signals across 34 countries are <span style={{ color:"#C8A96E" }}>Step 1</span> early indicators.
          The MARKETS tab yield data is <span style={{ color:"#C8A96E" }}>Step 2</span>.
          The breaking point calculator above shows where <span style={{ color:"#C8A96E" }}>Step 3</span> becomes irreversible.
          At {BREAK.toFixed(1)}% on the 10Y, the US crosses the emerging market danger threshold. At {CRISIS.toFixed(1)}%, it's Japan 2024.
        </div>
      </div>
    </div>
  );
}
