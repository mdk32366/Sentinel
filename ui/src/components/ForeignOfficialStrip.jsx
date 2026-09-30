import { trillions } from "../lib/format";

/**
 * What central banks are doing, as distinct from everyone else.
 *
 * `D-0080`. Table 5 publishes "Of Which: Foreign Official" — Treasuries held by
 * central banks and sovereign funds, across **every** holder, named and unnamed.
 * It is a subset of Grand Total, **not** a part of All Other and never added to
 * it: the two are different cuts of the same number. All Other answers "what are
 * the countries we cannot see doing"; this answers "what are central banks
 * doing", which is the question this application exists to ask.
 *
 * The private side is Grand Total minus official, derived rather than stored, so
 * there is no third figure to keep in step.
 *
 * Like All Other, it describes a **group**. It is rendered once, above the
 * table, never on a row — attributing a group's move to a named sovereign is
 * `F-0097`, which cost 1,050 points across 32 countries.
 */

function pp(v) {
  return v == null ? "—" : `${v > 0 ? "+" : ""}${v.toFixed(2)}pp`;
}

function pct(v) {
  return v == null ? "—" : `${v > 0 ? "+" : ""}${v.toFixed(2)}%`;
}

export function ForeignOfficialStrip({ signal }) {
  if (!signal) return null;

  const sustained = signal.sustained;
  const accent = sustained ? "#C8A96E" : "#2A3D50";
  const dir = (v) => (v == null ? "#5A6878" : v < 0 ? "#E07B5A" : "#5DB87A");

  const figures = [
    { label: "official", val: `$${trillions(signal.level_bn)}T`, color: "#8A9BAC" },
    { label: "share of total", val: signal.share_pct == null ? "—" : `${signal.share_pct.toFixed(2)}%`, color: sustained ? "#C8A96E" : "#8A9BAC" },
    { label: "private", val: signal.private_bn == null ? "—" : `$${trillions(signal.private_bn)}T`, color: "#8A9BAC" },
    { label: "12mo", val: pct(signal.twelve_month_pct), color: dir(signal.twelve_month_pct) },
    { label: "share move 12mo", val: pp(signal.share_move_12m_points), color: dir(signal.share_move_12m_points) },
    { label: "in bills", val: signal.bills_share_of_official_pct == null ? "—" : `${signal.bills_share_of_official_pct.toFixed(2)}%`, color: "#8A9BAC" },
  ];

  return (
    <div style={{ background: "#0A1520", border: "1px solid #1A2530", borderLeft: `3px solid ${accent}`, borderRadius: 2, padding: "12px 16px", marginBottom: 10 }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: 14, flexWrap: "wrap" }}>
        <span style={{ fontFamily: "monospace", fontSize: 10, color: "#5A6878", letterSpacing: "0.1em" }}>
          TIC FOREIGN OFFICIAL
        </span>
        {figures.map((f) => (
          <span key={f.label} style={{ fontFamily: "monospace", fontSize: 11, color: "#3A4D5C" }}>
            {f.label} <span style={{ color: f.color, fontWeight: 600 }}>{f.val}</span>
          </span>
        ))}
        <span style={{ fontFamily: "monospace", fontSize: 10, color: "#3A4D5C" }}>
          as of {signal.as_of}
        </span>
      </div>

      <div style={{ fontFamily: "monospace", fontSize: 10, color: "#5A6878", lineHeight: 1.6, marginTop: 6 }}>
        {signal.note}
      </div>

      {sustained && (
        <div style={{ fontFamily: "monospace", fontSize: 10, color: "#C8A96E", lineHeight: 1.6, marginTop: 4 }}>
          {`Official holdings have fallen in ${signal.falls_of_last_12} of the last 12 months, taking the official share of all foreign holdings ${pp(signal.share_move_12m_points)}. Private holders hold the remainder by construction, so their share rose by the same amount. This describes central banks as a group and says nothing about any one of them.`}
        </div>
      )}

      {/* Table 5 publishes bills and bonds separately; they must sum to the
          headline. A failure means the parse or the source has changed, and it
          is louder than the signal itself because every figure above depends
          on it. */}
      {signal.components_reconcile === false && (
        <div style={{ fontFamily: "monospace", fontSize: 10, color: "#FF4444", lineHeight: 1.6, marginTop: 4 }}>
          Bills and bonds do not sum to the official total — the source layout or
          the parse has changed. Treat these figures as unverified.
        </div>
      )}
    </div>
  );
}
