import { InfoTip } from "../InfoTip";

const cell = { background: "#0F1923", border: "1px solid #1A2530", borderRadius: 2, padding: "8px 12px", flex: "1 1 70px", fontFamily: "monospace" };

/**
 * Sentinel D-0115: the euro-area benchmark curve panel on FOREIGN-BONDS only.
 * ECB AAA and all-issuer Svensson spot curves at 2/5/7/10/30Y, plus the AAA
 * 2s10s and 10s30s in bp. A benchmark, not a country: no card, not in the
 * country list, nothing scored. `ea` is what `eaBenchmark()` returns.
 */
export function EaBenchmarkPanel({ ea }) {
  return (
    <section id="ea-benchmark" data-testid="ea-benchmark-panel" style={{ marginBottom: 24 }}>
      <div style={{ fontSize: 11, letterSpacing: 1, color: "#8A9AAA", marginBottom: 8, fontFamily: "monospace" }}>
        EURO AREA BENCHMARK CURVES (ECB) · not a country, display only
      </div>
      {ea.curves.map((c) => (
        <div key={c.id} data-testid={`ea-curve-${c.id}`} style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 8 }}>
          <div style={{ ...cell, flex: "0 0 120px", color: "#5A6878", fontSize: 10 }}>{c.label}</div>
          {c.points.map((p) => (
            <div key={p.code} style={cell} data-testid={`ea-${c.id}-${p.label}`}>
              <div style={{ fontSize: 10, color: "#5A6878" }}>{p.label}</div>
              <div style={{ fontSize: 14, fontWeight: 700, color: p.value == null ? "#3A4D5C" : "#7EB8C9" }}>
                {p.value == null ? "—" : `${p.value.toFixed(2)}%`}
              </div>
            </div>
          ))}
        </div>
      ))}
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        {ea.slopes.map((s) => (
          <InfoTip key={s.label} as="div" title={s.label} tip={s.tip} placement="below" align="left" tabIndex={0}
            style={{ ...cell, cursor: "help", outline: "none" }}>
            <div style={{ fontSize: 10, color: "#5A6878" }}>{s.label}</div>
            <div data-testid={`ea-slope-${s.label}`} style={{ fontSize: 14, fontWeight: 700, color: s.bp == null ? "#3A4D5C" : s.bp < 0 ? "#E07B5A" : "#5DB87A" }}>
              {s.bp == null ? "—" : `${s.bp > 0 ? "+" : ""}${s.bp.toFixed(0)}bp`}
            </div>
          </InfoTip>
        ))}
      </div>
      <div style={{ fontSize: 10, color: "#5A6878", marginTop: 6, fontFamily: "monospace" }}>{ea.attribution}</div>
    </section>
  );
}
