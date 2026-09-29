import { SOVEREIGN_YIELD_CODES } from "../lib/constants";
import { goldSeries, momChange, reservesSeries, ticSeries } from "../lib/countrySeries";
import { useCountryDetail } from "../hooks/useCountryDetail";
import { useCountryNarrative } from "../hooks/useCountryNarrative";
import { AnalystBrief } from "./country/AnalystBrief";
import { CountryStatCards } from "./country/CountryStatCards";
import { LiquidationBanner } from "./country/LiquidationBanner";
import { SeriesChart } from "./country/SeriesChart";

/**
 * One country: holdings, gold, reserves ex-gold, spread, CDS and a brief.
 *
 * `standalone` is the COUNTRY tab's full-page presentation; the inline form
 * is what HOLDINGS and GOLD open beneath a table row.
 *
 * `latestAll` is the FLAT `{code: value}` map of latest values — not the
 * `{latest, prior}` wrapper. `F-0064`: three call sites once passed three
 * different things, and the one passing `{}` showed every country's spread
 * as a dash, indistinguishable from a country FRED does not cover.
 */
export function CountryDetail({ iso, onClose, standalone = false, latestAll = {} }) {
  const { ticHistory, goldHistory, reservesHistory, cds, loading } = useCountryDetail(iso);
  const { narrative, loading: narrativeLoading, generate } = useCountryNarrative(iso);

  if (loading) {
    return <div style={{ padding: 24, fontFamily: "monospace", fontSize: 13, color: "#3A4D5C" }}>loading {iso}...</div>;
  }

  const container = standalone
    ? { background: "#080E14", minHeight: "100%" }
    : { background: "#0A1520", border: "1px solid #1A2530", borderRadius: 2, padding: 24, marginTop: 12 };

  const ticRows = ticSeries(ticHistory);
  const goldRows = goldSeries(goldHistory);
  const reservesRows = reservesSeries(reservesHistory);
  const hasAnySeries = Boolean(ticRows.length || goldRows.length || reservesRows.length);

  const yieldCode = SOVEREIGN_YIELD_CODES[iso];

  return (
    <div style={container}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 20 }}>
        <div>
          <div style={{ fontFamily: "monospace", fontSize: 10, color: "#5A6878", letterSpacing: "0.1em", marginBottom: 4 }}>COUNTRY DETAIL</div>
          <div style={{ fontFamily: "monospace", fontSize: 20, color: "#E8E0D0", fontWeight: 700 }}>
            {ticHistory?.country_name ?? goldHistory?.country_name ?? iso}
            <span style={{ marginLeft: 10, fontSize: 13, color: "#3A4D5C" }}>{iso}</span>
          </div>
        </div>
        {onClose && (
          <button onClick={onClose} style={{ background: "transparent", border: "1px solid #1E2D3D", color: "#5A6878", borderRadius: 2, padding: "6px 14px", cursor: "pointer", fontFamily: "monospace", fontSize: 12 }}>✕</button>
        )}
      </div>

      <LiquidationBanner ticHistory={ticHistory} goldRows={goldRows} iso={iso} />

      <CountryStatCards
        latestTic={ticRows[ticRows.length - 1]}
        ticMom={momChange(ticRows)}
        latestGold={goldRows[goldRows.length - 1]}
        ticHistory={ticHistory}
        countryYield={yieldCode ? latestAll[yieldCode] : null}
        us10y={latestAll["DGS10"]}
        cds={cds}
      />

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))", gap: 16 }}>
        <SeriesChart
          title={`TREASURY HOLDINGS ($B) — ${ticHistory?.data_points} months`}
          rows={ticRows}
          dataKey="holdings"
          stroke="#C8A96E"
          tickFormat={(v) => `$${v.toFixed(0)}B`}
          tooltipFormat={(v) => `$${v.toFixed(1)}B`}
          tooltipLabel="Holdings"
        />
        <SeriesChart
          title={`GOLD RESERVES (tonnes) — ${goldHistory?.data_points} quarters`}
          rows={goldRows}
          dataKey="tonnes"
          stroke="#E8C547"
          tickFormat={(v) => `${v.toFixed(0)}t`}
          tooltipFormat={(v) => `${v.toFixed(1)}t`}
          tooltipLabel="Gold"
        />
        <SeriesChart
          title="TOTAL RESERVES EX-GOLD ($M) — non-dollar reserve diversification"
          rows={reservesRows}
          dataKey="value"
          stroke="#7EB8C9"
          axisWidth={56}
          tickFormat={(v) => `$${(v / 1000).toFixed(0)}B`}
          tooltipFormat={(v) => `$${(v / 1000).toFixed(1)}B`}
          tooltipLabel="Reserves ex-Gold"
          footnote="Source: IMF IFS · Includes FX, SDRs, IMF positions · Excludes gold · Monthly"
        />
      </div>

      {!hasAnySeries && (
        <div style={{ fontFamily: "monospace", fontSize: 13, color: "#3A4D5C", padding: 24, textAlign: "center" }}>
          No data available for {iso}
        </div>
      )}

      {hasAnySeries && (
        <AnalystBrief narrative={narrative} loading={narrativeLoading} onGenerate={generate} />
      )}
    </div>
  );
}
