import { FUTURE, SIGNALS, SOURCES } from "../lib/dataSources";

export function AboutTab() {
  return (
    <div>
      <div style={{ fontFamily: "monospace", fontSize: 11, color: "#5A6878", marginBottom: 28, lineHeight: 1.8, maxWidth: 800 }}>
        Project Sentinel monitors sovereign stress signals in global treasury markets. The core thesis: countries that are
        <span style={{ color: "#C8A96E" }}> forced sellers</span> of US Treasuries reveal themselves through the data before it becomes news.
        The highest-conviction signal is simultaneous selling of both treasuries and gold — especially into a rising gold price.
      </div>

      {/* Retired surfaces — D-0051 */}
      <div style={{ marginBottom: 32 }}>
        <div style={{ fontFamily: "monospace", fontSize: 10, color: "#3A4D5C", letterSpacing: "0.15em", textTransform: "uppercase", marginBottom: 16, borderBottom: "1px solid #1A2530", paddingBottom: 6 }}>RETIRED</div>
        <div style={{ background: "#0A1520", border: "1px solid #1A2530", borderLeft: "3px solid #3A4D5C", borderRadius: 2, padding: "16px 20px", fontFamily: "monospace", fontSize: 11, color: "#5A6878", lineHeight: 1.8, maxWidth: 800 }}>
          <div style={{ color: "#8A9BAC", marginBottom: 6 }}>STRESS tab — retired 2026-09-29</div>
          A single US-level stress score built from the yield curve, holdings concentration
          and commodity volatility. It answered a different question from
          <span style={{ color: "#C8A96E" }}> COMPOSITE</span>, which scores sovereign stress
          per country, and having both invited the two to be read as one number disagreeing
          with itself.
          <div style={{ marginTop: 10, color: "#3A4D5C" }}>
            The scorer itself is not gone: <span style={{ color: "#5A6878" }}>stress_score_v2</span> still
            runs nightly at 04:30 UTC and <span style={{ color: "#5A6878" }}>GET /api/stress-score</span> still
            serves it. Only the tab was removed. See D-0051.
          </div>
        </div>
      </div>

      {/* Data Sources */}
      <div style={{ marginBottom: 32 }}>
        <div style={{ fontFamily: "monospace", fontSize: 10, color: "#3A4D5C", letterSpacing: "0.15em", textTransform: "uppercase", marginBottom: 16, borderBottom: "1px solid #1A2530", paddingBottom: 6 }}>DATA SOURCES</div>
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {SOURCES.map(s => (
            <div key={s.name} style={{ background: "#0A1520", border: `1px solid ${s.manual ? "#E8C54733" : "#1A2530"}`, borderLeft: `3px solid ${s.manual ? "#E8C547" : "#1A2530"}`, borderRadius: 2, padding: "16px 20px" }}>
              <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 16, flexWrap: "wrap" }}>
                <div style={{ flex: 1 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6 }}>
                    <span style={{ fontFamily: "monospace", fontSize: 13, color: "#E8E0D0", fontWeight: 600 }}>{s.name}</span>
                    <span style={{ fontFamily: "monospace", fontSize: 10, color: s.manual ? "#E8C547" : "#5DB87A", background: s.manual ? "#E8C54718" : "#5DB87A18", border: `1px solid ${s.manual ? "#E8C54744" : "#5DB87A44"}`, borderRadius: 2, padding: "1px 6px" }}>
                      {s.manual ? "⚠ MANUAL UPDATE" : "● AUTO"}
                    </span>
                  </div>
                  <div style={{ display: "flex", gap: 24, marginBottom: 8, flexWrap: "wrap" }}>
                    {[["Update", s.update], ["Lag", s.lag], ["Coverage", s.coverage]].map(([l, v]) => (
                      <div key={l}>
                        <span style={{ fontFamily: "monospace", fontSize: 10, color: "#3A4D5C" }}>{l}: </span>
                        <span style={{ fontFamily: "monospace", fontSize: 10, color: "#8A9BAC" }}>{v}</span>
                      </div>
                    ))}
                  </div>
                  <div style={{ fontFamily: "monospace", fontSize: 11, color: "#5A6878", marginBottom: 8 }}>
                    {s.metrics.map((m, i) => <div key={i}>· {m}</div>)}
                  </div>
                  <div style={{ fontFamily: "monospace", fontSize: 11, color: s.manual ? "#E8C547" : "#3A4D5C", lineHeight: 1.6 }}>{s.notes}</div>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Manual Update Checklist */}
      <div style={{ background: "#0A1520", border: "1px solid #5DB87A33", borderLeft: "3px solid #5DB87A", borderRadius: 2, padding: "16px 20px", marginBottom: 32 }}>
        <div style={{ fontFamily: "monospace", fontSize: 12, color: "#5DB87A", marginBottom: 12, letterSpacing: "0.1em" }}>✓ NOTHING REQUIRES A MANUAL DOWNLOAD</div>
        {/* F-0100. This was a MONTHLY MANUAL UPDATE CHECKLIST whose first item
            told the operator to download a WGC CSV and commit it to the repo —
            months after D-0076 automated gold from the IMF. F-0096 rewrote the
            source catalogue above and missed this block entirely, which is why
            the ABOUT tests now read the whole file rather than one export. */}
        {[
          { task: "Every source is fetched on a schedule", url: null, action: "Eleven jobs, listed with their cron on the ADMIN tab. Nothing is hand-fed." },
          { task: "Check the confidence strip on any tab", url: null, action: "It reports the watchdog's per-source verdict against each source's own release cadence (D-0074)." },
          { task: "After any manual fetch, refresh the score", url: null, action: "POST /api/snapshot/composite — the composite serves a stored snapshot, so new data does not reach it until the 04:45 job or an explicit refresh (F-0090)." },
          { task: "Per-country data age", url: null, action: "GET /api/diagnostics/data-age — the distribution of how old each country's data is, per source (A-0017)." },
        ].map((item, i) => (
          <div key={i} style={{ display: "flex", gap: 12, marginBottom: 10, alignItems: "flex-start" }}>
            <span style={{ fontFamily: "monospace", fontSize: 12, color: "#E8C547", marginTop: 1 }}>□</span>
            <div>
              <div style={{ fontFamily: "monospace", fontSize: 12, color: "#E8E0D0" }}>{item.task}</div>
              <div style={{ fontFamily: "monospace", fontSize: 11, color: "#5A6878", marginTop: 2 }}>{item.action}</div>
            </div>
          </div>
        ))}
      </div>

      {/* Signal Methodology */}
      <div style={{ marginBottom: 32 }}>
        <div style={{ fontFamily: "monospace", fontSize: 10, color: "#3A4D5C", letterSpacing: "0.15em", textTransform: "uppercase", marginBottom: 16, borderBottom: "1px solid #1A2530", paddingBottom: 6 }}>SIGNAL METHODOLOGY</div>
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {SIGNALS.map(s => (
            <div key={s.name} style={{ background: "#0A1520", border: `1px solid ${s.color}33`, borderLeft: `3px solid ${s.color}`, borderRadius: 2, padding: "16px 20px" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
                <span style={{ fontFamily: "monospace", fontSize: 10, color: s.color, background: `${s.color}18`, border: `1px solid ${s.color}44`, borderRadius: 2, padding: "1px 6px" }}>TIER {s.tier}</span>
                <span style={{ fontFamily: "monospace", fontSize: 13, color: "#E8E0D0", fontWeight: 600 }}>{s.name}</span>
              </div>
              <div style={{ fontFamily: "monospace", fontSize: 11, color: "#5A6878", marginBottom: 6 }}>Formula: {s.formula}</div>
              <div style={{ fontFamily: "monospace", fontSize: 11, color: "#5A6878", marginBottom: 6 }}>Threshold: {s.threshold}</div>
              <div style={{ fontFamily: "monospace", fontSize: 11, color: "#8A9BAC", lineHeight: 1.6 }}>{s.interpretation}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Future Pipelines */}
      <div style={{ marginBottom: 32 }}>
        <div style={{ fontFamily: "monospace", fontSize: 10, color: "#3A4D5C", letterSpacing: "0.15em", textTransform: "uppercase", marginBottom: 16, borderBottom: "1px solid #1A2530", paddingBottom: 6 }}>PLANNED PIPELINES</div>
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {FUTURE.map(f => (
            <div key={f.name} style={{ background: "#0A1520", border: "1px solid #1A2530", borderLeft: "3px solid #1E2D3D", borderRadius: 2, padding: "14px 20px" }}>
              <div style={{ fontFamily: "monospace", fontSize: 12, color: "#8A9BAC", fontWeight: 600, marginBottom: 4 }}>{f.name}</div>
              <div style={{ fontFamily: "monospace", fontSize: 11, color: "#5A6878", lineHeight: 1.6 }}>{f.why}</div>
            </div>
          ))}
        </div>
      </div>

      <div style={{ fontFamily: "monospace", fontSize: 11, color: "#1E2D3D", borderTop: "1px solid #1A2530", paddingTop: 16 }}>
        Project Sentinel · Built with FastAPI + PostgreSQL + React · Data: FRED, TIC, WGC
      </div>
    </div>
  );
}
