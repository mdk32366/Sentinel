/**
 * A movement, and what kind of movement it was.
 *
 * `D-0087`. A change in holdings is not self-explanatory. Japan's July 2026 was
 * **-$12.7bn of position and +$0.9bn of transactions** — it bought, and the
 * position fell on price. A column showing only the change invites exactly the
 * reading that misranked Japan for as long as dimension 1 existed (`F-0099`).
 *
 * The label comes from the server (`pipelines/tic_state.classify_movement`), so
 * the word a reader sees and the rule the score applies are the same thing.
 * `repriced` is the case dimension 1 refuses to score as selling (`A-0021`).
 *
 * Gold uses the same component with `accumulating` / `selling` / `stable`,
 * because tonnes are a pure quantity: there is no price component to separate,
 * so the kind of movement is its direction and persistence.
 */

const TONE = {
  sold: "#E07B5A",
  selling: "#E07B5A",
  bought: "#5DB87A",
  accumulating: "#5DB87A",
  // Gold on purpose: a position that moved on price is not a decision, so it is
  // neither good news nor bad. Muted rather than coloured like a signal.
  repriced: "#C8A96E",
  flat: "#5A6878",
  stable: "#5A6878",
  unknown: "#3A4D5C",
};

const LABEL = {
  sold: "sold",
  selling: "selling",
  bought: "bought",
  accumulating: "buying",
  repriced: "repriced",
  flat: "flat",
  stable: "stable",
  unknown: "—",
};

export function MovementCell({ change, unit = "bn", movement, note, pct }) {
  const tone = TONE[movement] ?? "#5A6878";
  const label = LABEL[movement] ?? "—";

  return (
    <div title={note || undefined} style={{ cursor: note ? "help" : "default" }}>
      <div style={{ fontFamily: "monospace", fontSize: 12, color: tone }}>
        {change == null
          ? "—"
          : `${change > 0 ? "+" : change < 0 ? "−" : ""}${
              unit === "bn" ? "$" : ""
            }${Math.abs(change).toFixed(1)}${unit === "t" ? "t" : "B"}`}
      </div>
      <div style={{ fontFamily: "monospace", fontSize: 9, color: "#3A4D5C", marginTop: 1 }}>
        {label}
        {pct != null && ` · ${pct > 0 ? "+" : ""}${pct.toFixed(1)}%`}
      </div>
    </div>
  );
}
