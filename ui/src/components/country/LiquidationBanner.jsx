/**
 * Shown when a country holds zero US Treasuries and still holds gold.
 *
 * Failure-red, and deliberately so: unlike a missing data point, a completed
 * liquidation is the signal this whole application exists to surface.
 * Renders nothing unless BOTH conditions hold — zero Treasuries with no gold
 * position is an absence of data, not a de-dollarisation posture.
 */
export function LiquidationBanner({ ticHistory, goldRows, iso }) {
  if (ticHistory?.data_points !== 0 || !goldRows?.length) return null;

  const latestGold = goldRows[goldRows.length - 1];

  return (
    <div style={{ background: "#FF444415", border: "1px solid #FF444444", borderLeft: "4px solid #FF4444", borderRadius: 2, padding: "12px 18px", marginBottom: 20 }}>
      <div style={{ fontFamily: "monospace", fontSize: 12, color: "#FF4444", fontWeight: 700, marginBottom: 4 }}>
        ⚠ COMPLETED TREASURY LIQUIDATION
      </div>
      <div style={{ fontFamily: "monospace", fontSize: 11, color: "#8A9BAC", lineHeight: 1.6 }}>
        {ticHistory?.country_name ?? iso} holds zero US Treasury securities. Position has been fully exited.
        {` Gold reserves: ${latestGold?.tonnes?.toFixed(0)}t — gold accumulation pattern confirms de-dollarization posture.`}
      </div>
    </div>
  );
}
