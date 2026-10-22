import { useChartSeries } from "../../hooks/useChartSeries";
import { useChartView } from "../../hooks/useChartView";
import { fbCardMetrics } from "../../lib/constants";
import { MarketsChartPanel } from "../../pages/MarketsChartPanel";
import { InfoTip } from "../InfoTip";

const SLOPE_TIP = {
  "2s10s": "10Y minus 2Y on this country's daily FB curve, in basis points. A dash when either leg is missing, stale beyond its source's freshness limit, or dated differently from the other leg: a slope is never computed across dates (Sentinel D-0113). Display only.",
  "3s10s": "10Y minus 3Y on this country's daily FB curve, in basis points: the source publishes no 2Y, so the front leg is 3Y (Sentinel D-0115). A dash when either leg is missing, stale beyond its source's freshness limit, or dated differently from the other leg: a slope is never computed across dates. Display only.",
  "10s30s": "30Y minus 10Y on this country's daily FB curve, in basis points. A dash when either leg is missing, stale beyond its source's freshness limit, or dated differently from the other leg: a slope is never computed across dates (Sentinel D-0113). Display only.",
};

const cell = { background: "#0F1923", border: "1px solid #1A2530", borderRadius: 2, padding: "8px 12px", flex: "1 1 70px", fontFamily: "monospace" };

/**
 * Sentinel D-0113: the daily curve row (2/5/7/10/30Y; D-0115: each source's own tenors), the 2s10s and 10s30s
 * slopes, and the Foreign Bonds chart filtered to this one country. Display
 * only. The chart's state is local, so it lives and dies with this country's
 * panel (CountryDetail keys it by ISO) and never touches MARKETS' state.
 */
export function CountryBondCurve({ iso, bond, chart = false }) {
  return (
    <div style={{ marginBottom: 24 }}>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 8 }}>
        {bond.curve.map((c) => (
          <div key={c.code} style={cell} data-testid={`curve-${c.label}`}>
            <div style={{ fontSize: 10, color: "#5A6878" }}>{c.label}</div>
            <div style={{ fontSize: 14, fontWeight: 700, color: c.value == null ? "#3A4D5C" : "#7EB8C9" }}>
              {c.value == null ? "NO SOURCE" : `${c.value.toFixed(2)}%`}
            </div>
          </div>
        ))}
        {bond.slopes.map((s) => (
          <InfoTip key={s.label} as="div" title={s.label} tip={s.tip ?? SLOPE_TIP[s.label]} placement="below" align="left" tabIndex={0}
            style={{ ...cell, cursor: "help", outline: "none" }}>
            <div style={{ fontSize: 10, color: "#5A6878" }}>{s.label}</div>
            <div data-testid={`slope-${s.label}`} style={{ fontSize: 14, fontWeight: 700, color: s.bp == null ? "#3A4D5C" : s.bp < 0 ? "#E07B5A" : "#5DB87A" }}>
              {s.bp == null ? "—" : `${s.bp > 0 ? "+" : ""}${s.bp.toFixed(0)}bp`}
            </div>
          </InfoTip>
        ))}
      </div>
      {chart && <CountryBondChart iso={iso} />}
    </div>
  );
}

function CountryBondChart({ iso }) {
  const charted = fbCardMetrics(iso);
  const view = useChartView(charted.map((m) => m.code));
  const { rows, loading } = useChartSeries({ activeMetrics: view.activeMetrics, range: view.range, normalized: view.normalized });
  return <MarketsChartPanel charted={charted} view={view} chartData={rows} loading={loading} height={260} testId="country-bond-chart" pressedState />;
}
