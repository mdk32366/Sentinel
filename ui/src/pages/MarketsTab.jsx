import { formatDate } from "../lib/format";
import { changeBetween, changeSuffix, changeWindowLabel } from "../lib/series";
import { useChartSeries } from "../hooks/useChartSeries";
import { useChartView } from "../hooks/useChartView";
import { DataConfidence } from "../components/DataConfidence";
import { InfoTip } from "../components/InfoTip";
import { StatCard } from "../components/StatCard";
import { MarketsChartPanel } from "./MarketsChartPanel";

/**
 * The MARKETS layout, as a component: DataConfidence -> StatCard grid ->
 * chart panel (series toggles, % CHANGE, ranges) -> spread strip -> source
 * footer.
 *
 * Sentinel D-0111 (vault:D-0057). Lifted VERBATIM out of App.jsx so the
 * FOREIGN-BONDS tab is the same surface with different inputs rather than a
 * fork of it. MARKETS renders byte-identical to master be64218 through this
 * component - `marketsDefault.ac1.dom.test.jsx` compares the bytes.
 *
 * Props:
 *   metrics       cards in grid order; an entry with `code: null` is a NO
 *                 SOURCE cell: it renders "—" and its tip, and has no toggle
 *   sourceKeys    watchdog sources for DataConfidence
 *   spreads       (latest) => [{label, val, tip, inverts?, unit?, display?}] | null; null or
 *                 empty hides the strip
 *   defaultActive codes drawn on the chart at first
 *   sourceNote    footer text
 *   lastDataPoint date for the footer, or null
 *   columns       grid columns (MARKETS 6, FOREIGN-BONDS 5)
 *   latest/prior  from useSeries / useMarketSeries
 *   view          optional, from useChartView() in a parent that outlives the
 *                 tab. Given, the chart state is controlled and survives the
 *                 tab unmounting (MARKETS, as on master); omitted, it is local.
 */
export function MarketsTab({
  metrics, sourceKeys, spreads, defaultActive, sourceNote, lastDataPoint,
  columns = 6, latest, prior, view,
}) {
  const local = useChartView(defaultActive);
  const { activeMetrics, setActiveMetrics, range, setRange, normalized, setNormalized } = view ?? local;

  const { rows: chartData, loading } = useChartSeries({ activeMetrics, range, normalized });

  const getChange = (code, unit) => {
    const previous = prior[code];
    if (!previous || latest[code] == null) return null;
    const value = changeBetween(latest[code], previous.value, unit);
    if (value == null) return null;
    return { value, suffix: changeSuffix(unit), window: changeWindowLabel(previous.actualDays) };
  };

  const charted = metrics.filter(m => m.code);
  const strip = normalized ? null : spreads(latest);

  return (
    <>
      <DataConfidence sourceKeys={sourceKeys} />
      <div style={{ display: "grid", gridTemplateColumns: `repeat(${columns}, 1fr)`, gap: 12, marginBottom: 28 }}>
        {metrics.map(m => (
          <StatCard
            key={m.key ?? m.code}
            label={m.label}
            value={m.code ? latest[m.code] : null}
            unit={m.unit}
            change={m.code ? getChange(m.code, m.unit) : null}
            color={m.color}
            tip={m.tip}
            stressRole={m.stressRole}
            scored={m.scored}
            badge={m.badge}
          />
        ))}
      </div>
      <MarketsChartPanel charted={charted} view={{ activeMetrics, setActiveMetrics, range, setRange, normalized, setNormalized }} chartData={chartData} loading={loading} />
      {strip && strip.length > 0 && (
        <div style={{ marginTop: 12, background: "#0A1520", border: "1px solid #1A2530", borderRadius: 2, padding: "14px 28px", display: "flex", gap: 32, alignItems: "center", flexWrap: "wrap" }}>
          <span style={{ fontFamily: "monospace", fontSize: 11, color: "#3A4D5C", letterSpacing: "0.1em" }}>SPREAD</span>
          {strip.map(s => (
            <div key={s.label} style={{ fontFamily: "monospace" }}>
              <InfoTip title={s.label} tip={s.tip} placement="above" style={{ fontSize: 11, color: "#3A4D5C", marginRight: 8 }}>
                <span style={{ borderBottom: "1px dashed #2A3D50", paddingBottom: 1 }}>{s.label}</span>
              </InfoTip>
              {s.val == null
                ? <span style={{ fontSize: 15, color: "#3A4D5C", fontWeight: 600 }}>{s.display ?? "—"}</span>
                : <span style={{ fontSize: 15, color: s.val < 0 ? "#E07B5A" : "#5DB87A", fontWeight: 600 }}>{s.val > 0 ? "+" : ""}{s.unit === "bp" ? `${s.val.toFixed(0)}bp` : `${s.val.toFixed(2)}pp`}</span>}
              {s.inverts && s.val < 0 && <span style={{ marginLeft: 8, fontSize: 10, color: "#E07B5A88" }}>INVERTED</span>}
            </div>
          ))}
        </div>
      )}
      <div style={{ marginTop: 24, display: "flex", justifyContent: "space-between" }}>
        <span style={{ fontFamily: "monospace", fontSize: 11, color: "#1E2D3D" }}>{sourceNote}</span>
        {lastDataPoint && <span style={{ fontFamily: "monospace", fontSize: 11, color: "#1E2D3D" }}>Last data point: {formatDate(lastDataPoint)}</span>}
      </div>
    </>
  );
}
