import { trillions } from "../lib/format";
import { InfoTip } from "./InfoTip";

/**
 * What the countries the model cannot see individually are doing together.
 *
 * `D-0079` / `A-0019` option 2. SLT Table 5 names twenty holders and folds every
 * other foreign holder into one "All Other" row. `F-0097` established that a
 * country absent from the table is inside that row rather than at zero, and
 * `D-0078` marked that on each score as a gap. This is the aggregate itself:
 * the row is published, so the non-reporters' combined position is knowable even
 * though no individual position is.
 *
 * **Rendered once, above the table, never on a row.** All Other covers roughly a
 * hundred holders — sovereign wealth funds, private institutions and the 28
 * scored countries outside the table. A move says *someone* reduced; it does not
 * say who. Putting it beside a country would invite exactly the reading that
 * cost 1,050 points across 32 countries (`F-0097`).
 *
 * Neutral by default, and coloured only when the SHARE of total moves. The level
 * rose 2.74% over the twelve months to 2026-07 while its share fell — total
 * foreign holdings grew faster — so a level-based colour would have called that
 * accumulation.
 */

function pct(v) {
  return v == null ? "—" : `${v > 0 ? "+" : ""}${v.toFixed(2)}%`;
}

export function AllOtherStrip({ signal }) {
  if (!signal) return null;

  const notable = signal.notable;
  const accent = notable ? "#E8C547" : "#2A3D50";
  const dirColor = (v) =>
    v == null ? "#5A6878" : v < 0 ? "#E07B5A" : "#5DB87A";

  const figures = [
    { label: "level", val: `$${trillions(signal.level_bn)}T`, color: "#8A9BAC",
      tip: "The All Other row of SLT Table 5: Treasuries held by every foreign holder too small to be named among the twenty, added together. Roughly a hundred holders, including sovereign funds, private institutions and the 28 scored countries outside the table (D-0079)." },
    { label: "share of total", val: signal.share_pct == null ? "—" : `${signal.share_pct.toFixed(2)}%`, color: "#8A9BAC",
      tip: "All Other as a percentage of Table 5's Grand Total for the same month. This separates the unnamed holders buying or selling from total foreign holdings simply growing, which the level alone cannot do." },
    { label: "1mo", val: pct(signal.mom_pct), color: dirColor(signal.mom_pct),
      tip: "Change in the All Other level against the previous monthly release. Green is a rise, red a fall. It says someone among the unnamed holders moved; it never says who (F-0097)." },
    { label: "3mo", val: pct(signal.three_month_pct), color: dirColor(signal.three_month_pct),
      tip: "Change in the All Other level over three monthly releases. A level can rise while the share falls, when total foreign holdings grow faster, so read it beside the share." },
    { label: "12mo", val: pct(signal.twelve_month_pct), color: dirColor(signal.twelve_month_pct),
      tip: "Change in the All Other level over twelve monthly releases, the full depth of the thirteen months SLT Table 5 publishes." },
    {
      label: "share move 3mo",
      tip: "Change in All Other's share of the Grand Total over three months, in percentage points. A move of half a point or more lights this strip: the share moved within about 19.3%-20.1% over the thirteen months to 2026-07, so that is outside ordinary drift. Who moved is not knowable from this row.",
      val: signal.share_move_3m_points == null
        ? "—"
        : `${signal.share_move_3m_points > 0 ? "+" : ""}${signal.share_move_3m_points.toFixed(2)}pp`,
      color: notable ? "#E8C547" : "#5A6878",
    },
  ];

  return (
    <div style={{ background: "#0A1520", border: "1px solid #1A2530", borderLeft: `3px solid ${accent}`, borderRadius: 2, padding: "12px 16px", marginBottom: 16 }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: 14, flexWrap: "wrap" }}>
        <span style={{ fontFamily: "monospace", fontSize: 10, color: "#5A6878", letterSpacing: "0.1em" }}>
          TIC ALL OTHER HOLDERS
        </span>
        {figures.map((f) => (
          <span key={f.label} style={{ fontFamily: "monospace", fontSize: 11, color: "#3A4D5C" }}>
            <InfoTip title={f.label} tip={f.tip} placement="below">
              <span style={{ borderBottom: "1px dashed #2A3D50" }}>{f.label}</span>
            </InfoTip>{" "}
            <span style={{ color: f.color, fontWeight: 600 }}>{f.val}</span>
          </span>
        ))}
        {signal.consecutive_declines > 0 && (
          <span style={{ fontFamily: "monospace", fontSize: 10, color: "#E07B5A" }}>
            {signal.consecutive_declines}mo consecutive ↓
          </span>
        )}
        <span style={{ fontFamily: "monospace", fontSize: 10, color: "#3A4D5C" }}>
          as of {signal.as_of}
        </span>
      </div>
      <div style={{ fontFamily: "monospace", fontSize: 10, color: "#5A6878", lineHeight: 1.6, marginTop: 6 }}>
        {signal.note}
      </div>
      {notable && (
        <div style={{ fontFamily: "monospace", fontSize: 10, color: "#E8C547", lineHeight: 1.6, marginTop: 4 }}>
          The share of total foreign holdings has moved more than half a point in
          three months — something changed among the holders the table does not
          name. Which of them is not knowable from this row.
        </div>
      )}
    </div>
  );
}
