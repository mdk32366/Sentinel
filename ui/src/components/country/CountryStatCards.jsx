import { spreadBasisPoints, spreadColor } from "../../lib/format";

/** A signed value with an explicit "+" on the positive side. */
const signed = (n, digits) => `${n > 0 ? "+" : ""}${n.toFixed(digits)}`;

/**
 * The six tiles across the top of the country panel.
 *
 * Each tile is a value and a colour that carries the same information again,
 * so a tile with nothing to show is `#3A4D5C` — the same grey as a label,
 * deliberately not failure-red. Missing coverage is not a fault.
 */
export function CountryStatCards({ latestTic, ticMom, latestGold, ticHistory, countryYield, us10y, cds }) {
  const exited = ticHistory?.data_points === 0;
  const spreadBps = spreadBasisPoints(countryYield, us10y);

  const cards = [
    {
      label: "T-Bill Holdings",
      val: latestTic ? `$${latestTic.holdings.toFixed(1)}B` : exited ? "EXITED" : "—",
      color: latestTic ? "#C8A96E" : exited ? "#FF4444" : "#3A4D5C",
      sub: exited ? "Zero US Treasuries held" : null,
    },
    {
      label: "MoM Change",
      val: ticMom != null ? `${signed(ticMom, 2)}%` : exited ? "N/A" : "—",
      color: ticMom == null ? "#3A4D5C" : ticMom < 0 ? "#E07B5A" : "#5DB87A",
    },
    { label: "Gold Reserves", val: latestGold ? `${latestGold.tonnes.toFixed(0)}t` : "—", color: "#E8C547" },
    { label: "Sovereign Yield", val: countryYield != null ? `${countryYield.toFixed(2)}%` : "—", color: "#7EB8C9" },
    { label: "Spread vs US 10Y", val: spreadBps != null ? `${signed(spreadBps, 0)}bps` : "—", color: spreadColor(spreadBps) },
    {
      label: "5Y CDS",
      val: cds.cds5y != null ? `${cds.cds5y.toFixed(0)}bps` : "No coverage",
      color: cds.cds5y == null ? "#3A4D5C" : cds.cds5y > 250 ? "#E07B5A" : cds.cds5y > 100 ? "#C8A96E" : "#7EB8C9",
      sub: cds.cds5y == null
        ? "Not factored into stress score"
        : cds.termSpread != null
          ? `Term ${signed(cds.termSpread, 0)}bps${cds.termSpread < 0 ? " (inverted)" : ""}`
          : null,
    },
  ];

  return (
    <div style={{ display: "flex", gap: 12, marginBottom: 24, flexWrap: "wrap" }}>
      {cards.map((s) => (
        <div key={s.label} style={{ background: "#0F1923", border: `1px solid ${s.color}22`, borderTop: `2px solid ${s.color}`, borderRadius: 2, padding: "12px 16px", flex: "1 1 120px" }}>
          <div style={{ fontFamily: "monospace", fontSize: 10, color: "#5A6878", textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 4 }}>{s.label}</div>
          <div style={{ fontFamily: "monospace", fontSize: 16, fontWeight: 700, color: s.color }}>{s.val}</div>
          {s.sub && <div style={{ fontFamily: "monospace", fontSize: 10, color: s.color, marginTop: 3, opacity: 0.8 }}>{s.sub}</div>}
        </div>
      ))}
    </div>
  );
}
