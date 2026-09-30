/**
 * What this country's change in Treasury holdings was actually made of.
 *
 * `D-0083` / `A-0021` option 1. Dimension 1 scores the month-on-month change in
 * **holdings**, and holdings move for two reasons: someone transacted, or the
 * bonds repriced. The scorer cannot tell them apart.
 *
 * Japan's July 2026 is the case that made this worth building: holdings
 * **-$12.7bn**, net transactions **+$0.9bn**, long-term valuation **-$12.1bn**.
 * Japan was a net buyer that month and dimension 1 scored it as a seller.
 *
 * Over the three months to July, Japan's net transactions were **-$88.6bn** —
 * genuinely large selling, mostly short-term bills. Dimension 1 saw a 1.15%
 * monthly move and scored 15.4, while Argentina scored 38.0 on a $1.1bn move
 * having *bought* over the same window. Percentage scoring is worth 0.27 points
 * per $bn to Japan and 90.91 to Uruguay (`F-0099`).
 *
 * **This changes no score.** `A-0021` option 1 was chosen over switching the
 * input because the position change and the published flows disagree by more
 * than 10% of the move in 65% of country-months — net sales is cleaner about
 * intent and worse about completeness. So the reader is shown the split and the
 * model is left alone.
 */

function bn(v, dp = 1) {
  if (v == null) return "—";
  return `${v > 0 ? "+" : v < 0 ? "−" : ""}$${Math.abs(v).toFixed(dp)}bn`;
}

export function TreasuryFlow({ row }) {
  if (!row) return null;

  const net1 = row.tic_net_1m_bn;
  const val1 = row.tic_valuation_1m_bn;
  const net3 = row.tic_net_3m_bn;
  if (net1 == null && net3 == null) return null;

  const dir = (v) => (v == null ? "#5A6878" : v < 0 ? "#E07B5A" : "#5DB87A");

  // The case worth naming: holdings and transactions point opposite ways, so
  // the score is reading price as posture.
  const mom = row.tic_mom_pct;
  const contradicts =
    mom != null && net1 != null && Math.sign(mom) !== Math.sign(net1)
    && Math.abs(net1) > 0.05;

  return (
    <div style={{ background: "#0A1520", border: "1px solid #1A2530", borderLeft: `3px solid ${contradicts ? "#C8A96E" : "#2A3D50"}`, borderRadius: 2, padding: "12px 16px", marginTop: 12 }}>
      <div style={{ fontFamily: "monospace", fontSize: 10, color: "#5A6878", letterSpacing: "0.1em", marginBottom: 8 }}>
        TREASURY FLOWS · WHAT THE MOVE WAS MADE OF
      </div>

      <div style={{ display: "flex", gap: 18, flexWrap: "wrap" }}>
        <span style={{ fontFamily: "monospace", fontSize: 11, color: "#3A4D5C" }}>
          holdings 1mo{" "}
          <span style={{ color: dir(mom), fontWeight: 600 }}>
            {mom == null ? "—" : `${mom > 0 ? "+" : ""}${mom.toFixed(2)}%`}
          </span>
        </span>
        <span style={{ fontFamily: "monospace", fontSize: 11, color: "#3A4D5C" }}>
          of which transacted{" "}
          <span style={{ color: dir(net1), fontWeight: 600 }}>{bn(net1)}</span>
        </span>
        <span style={{ fontFamily: "monospace", fontSize: 11, color: "#3A4D5C" }}>
          repriced{" "}
          <span style={{ color: dir(val1), fontWeight: 600 }}>{bn(val1)}</span>
        </span>
        <span style={{ fontFamily: "monospace", fontSize: 11, color: "#3A4D5C" }}>
          transacted {row.tic_flow_months ?? 3}mo{" "}
          <span style={{ color: dir(net3), fontWeight: 600 }}>{bn(net3)}</span>
        </span>
      </div>

      {contradicts && (
        <div style={{ fontFamily: "monospace", fontSize: 10, color: "#C8A96E", lineHeight: 1.6, marginTop: 8 }}>
          {`Holdings moved ${mom > 0 ? "up" : "down"} while transactions went the other way (${bn(net1)}). The Treasury dimension scores the holdings change, so this month it is reading price rather than posture (A-0021).`}
        </div>
      )}

      <div style={{ fontFamily: "monospace", fontSize: 10, color: "#5A6878", lineHeight: 1.6, marginTop: 8 }}>
        Holdings change includes price; transactions do not. The two disagree by
        more than a tenth of the move in most country-months, so neither is the
        whole story — the split is shown rather than scored.
      </div>
    </div>
  );
}
