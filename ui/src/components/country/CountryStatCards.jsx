import { CDS_BANDS, cdsBandText } from "../../lib/dimensions";
import { spreadBasisPoints, spreadColor } from "../../lib/format";
import { InfoTip } from "../InfoTip";

/** A signed value with an explicit "+" on the positive side. */
const signed = (n, digits) => `${n > 0 ? "+" : ""}${n.toFixed(digits)}`;

/**
 * Colour a CDS level by the band it scores in.
 *
 * Derived from `CDS_BANDS` rather than restated, because this tile spent two
 * decisions coloured on the retired 100/250 rungs while the score used
 * 200/350/600 — the colour and the points disagreeing about the same number.
 */
function cdsBandColor(bps) {
  if (bps == null) return "#3A4D5C";
  const [elevated, significant, distress] = CDS_BANDS;
  if (bps > distress.bps) return "#FF4444";
  if (bps > significant.bps) return "#E07B5A";
  if (bps > elevated.bps) return "#C8A96E";
  return "#7EB8C9";
}

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
      tip: "Total US Treasury securities this sovereign holds, in billions, from the latest TIC monthly snapshot. EXITED means a reported position of exactly zero — a completed liquidation, not missing data. This feeds dimension 1, the largest in the composite score at up to 50 points.",
    },
    {
      label: "MoM Change",
      val: ticMom != null ? `${signed(ticMom, 2)}%` : exited ? "N/A" : "—",
      color: ticMom == null ? "#3A4D5C" : ticMom < 0 ? "#E07B5A" : "#5DB87A",
      tip: "Month-on-month change in those holdings; negative is selling. The Treasury dimension scores the magnitude at up to 30 points and each consecutive declining month at a further 4, capped at 20 — persistence is what separates strategic reduction from ordinary rebalancing. A dash means fewer than two observations to compare, and a re-entry from zero shows a dash rather than an infinite percentage (F-0066).",
    },
    {
      label: "Gold Reserves",
      val: latestGold ? `${latestGold.tonnes.toFixed(0)}t` : "—",
      color: "#E8C547",
      tip: "Central bank gold in metric tonnes, from the IMF's monthly IRFCL return (D-0076). Gold matters here as the alternative reserve asset: a sovereign selling Treasuries while accumulating gold is restructuring its reserves rather than raising cash, and selling both together triggers the 1.5× cross-asset multiplier.",
    },
    {
      label: "Sovereign Yield",
      val: countryYield != null ? `${countryYield.toFixed(2)}%` : "—",
      color: "#7EB8C9",
      tip: "This country's 10-year government bond yield, where FRED publishes one — fourteen developed markets do, most emerging markets do not. A dash means no series exists, not a yield of zero.",
    },
    {
      label: "Spread vs US 10Y",
      val: spreadBps != null ? `${signed(spreadBps, 0)}bps` : "—",
      color: spreadColor(spreadBps),
      tip: "This sovereign's 10-year yield minus the US 10-year, in basis points. Positive means investors demand more to lend here than to Washington. MEASURED ONLY — D-0066 retired this from scoring: it awarded points for trading above the US 10Y while holding yields for only fourteen developed markets, every one of which trades below it. Across all 48 scored countries it awarded zero points to zero countries.",
    },
    {
      label: "5Y CDS",
      val: cds.cds5y != null ? `${cds.cds5y.toFixed(0)}bps` : "No coverage",
      // D-0073: coloured from the SCORING ladder rather than its own numbers.
      // This tile still read >250 / >100 after D-0065 and D-0067 moved the
      // rungs to 200 / 350 / 600 — a tile whose colour disagrees with the
      // score it illustrates. Third time the same drift (F-0068, F-0076,
      // F-0081), so it is derived now instead of written down again.
      color: cdsBandColor(cds.cds5y),
      sub: cds.cds5y == null
        ? (cds.coverage && cds.coverage !== "quoted"
            ? cds.coverage
            : "Not factored into stress score")
        : cds.termSpread != null
          ? `Term ${signed(cds.termSpread, 0)}bps${cds.termSpread < 0 ? " (inverted)" : ""}`
          : "5Y only — no paired 10Y on this board",
      tip: `The market price of insuring this sovereign's debt against default for five years, in basis points — the only forward-looking, market-priced input in the model. Scored as dimension 7: ${cdsBandText()}, plus 5 more if it has widened by over 20% in three months. A dash says why it is absent: no quote, a stale one, or a figure too large to be a running spread (F-0074).`,
    },
  ];

  return (
    <div style={{ display: "flex", gap: 12, marginBottom: 24, flexWrap: "wrap" }}>
      {cards.map((s) => (
        <InfoTip
          key={s.label}
          as="div"
          title={s.label}
          tip={s.tip}
          placement="below"
          align="left"
          tabIndex={s.tip ? 0 : undefined}
          style={{ background: "#0F1923", border: `1px solid ${s.color}22`, borderTop: `2px solid ${s.color}`, borderRadius: 2, padding: "12px 16px", flex: "1 1 120px", cursor: s.tip ? "help" : "default", outline: "none" }}>
          <div style={{ fontFamily: "monospace", fontSize: 10, color: "#5A6878", textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 4 }}>
            <span style={s.tip ? { borderBottom: "1px dashed #2A3D50", paddingBottom: 1 } : undefined}>{s.label}</span>
          </div>
          <div style={{ fontFamily: "monospace", fontSize: 16, fontWeight: 700, color: s.color }}>{s.val}</div>
          {s.sub && <div style={{ fontFamily: "monospace", fontSize: 10, color: s.color, marginTop: 3, opacity: 0.8 }}>{s.sub}</div>}
        </InfoTip>
      ))}
    </div>
  );
}
