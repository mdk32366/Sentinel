import { freshness } from "../lib/freshness";

/**
 * A data date, with its age when the age is the point.
 *
 * `F-0083`: three tabs printed a bare date — "Data as of 2025-12", "Dec 2025"
 * — while that data was 302 days old because the TIC source stopped
 * publishing. Each sentence was true. None of them was informative: a
 * December date on a monthly series reads as the ordinary one-to-two-month
 * lag TIC normally has.
 *
 * One component rather than three inline copies, because three copies of a
 * freshness rule is how two of them end up disagreeing (`F-0062`, `F-0081`).
 *
 * `note` is the caller's sentence about what being stale *means here* — the
 * component knows the age, only the tab knows the consequence.
 */
export function DataAsOf({ asOf, label = "Data as of", source, note, toleranceDays, style }) {
  const f = freshness(asOf, toleranceDays);
  const shown = asOf ?? "—";

  return (
    <div style={{ marginTop: 12, fontFamily: "monospace", fontSize: 11, color: "#1E2D3D", ...style }}>
      {source && <>Source: {source} · </>}
      {label} {shown}
      {f.age != null && (
        <span style={{ color: f.color, marginLeft: 6 }}>
          ({f.text}{f.stale && note ? ` — ${note}` : ""})
        </span>
      )}
    </div>
  );
}
