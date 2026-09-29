import { useApiResource } from "../../hooks/useApiResource";
import { scoreBreakdown } from "../../lib/dimensions";

const TIER_COLORS = { CRISIS: "#FF4444", STRESSED: "#E07B5A", ELEVATED: "#E8C547", WATCH: "#5A6878" };

/** How a rejected CDS quote is explained, rather than shown as a blank. */
const CDS_COVERAGE_NOTE = {
  "not on the board": "No CDS quoted for this sovereign.",
  "no coverage": "No CDS quoted for this sovereign.",
  "not quoted as a running spread":
    "CDS exists but is not quoted as a running spread — a defaulted or " +
    "points-upfront credit. Excluded from the score rather than read as a number.",
};

function coverageNote(coverage) {
  if (!coverage || coverage === "quoted") return null;
  if (coverage.startsWith("stale")) {
    return `The last CDS quote is ${coverage.replace(/^stale \(|\)$/g, "")} — too old to price today. Excluded from the score.`;
  }
  return CDS_COVERAGE_NOTE[coverage] ?? `CDS excluded: ${coverage}.`;
}

/**
 * What this country's composite stress score is actually made of.
 *
 * `D-0060`. The COMPOSITE tab ranks countries and the CDS tab lists spreads,
 * and neither said how the two relate. This is where they meet: one country,
 * its tier, and the dimensions that produced the number — including CDS,
 * which for some countries is most of it.
 *
 * Renders nothing for a country the scorer does not rank. That is the common
 * case — 48 of 105 countries score — and an empty panel on every other
 * country would be noise.
 */
export function StressContribution({ iso }) {
  const { data, loading } = useApiResource(`/stress/composite`);

  if (loading || !data) return null;

  const row = [...(data.crisis || []), ...(data.stressed || []),
               ...(data.elevated || []), ...(data.watch || [])]
    .find((r) => r.country_iso === iso);

  if (!row) return null;

  const parts = scoreBreakdown(row);
  const tier = (row.tier || "").toUpperCase();
  const tierColor = TIER_COLORS[tier] ?? "#5A6878";
  const note = coverageNote(row.cds_coverage);

  return (
    <div style={{ background: "#0A1520", border: "1px solid #1A2530", borderLeft: `3px solid ${tierColor}`, borderRadius: 2, padding: "16px 20px", marginTop: 16 }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: 12, flexWrap: "wrap", marginBottom: 12 }}>
        <div style={{ fontFamily: "monospace", fontSize: 11, color: "#5A6878", letterSpacing: "0.1em" }}>
          COMPOSITE STRESS
        </div>
        <div style={{ fontFamily: "monospace", fontSize: 18, fontWeight: 700, color: tierColor }}>
          {Number(row.composite_score).toFixed(1)}
        </div>
        <div style={{ fontFamily: "monospace", fontSize: 11, color: tierColor, background: `${tierColor}18`, border: `1px solid ${tierColor}44`, borderRadius: 2, padding: "1px 8px" }}>
          {tier || "SCORED"}
        </div>
        {row.multiplier > 1 && (
          <div style={{ fontFamily: "monospace", fontSize: 10, color: "#E07B5A" }}>
            × {row.multiplier} applied
          </div>
        )}
      </div>

      {parts.length > 0 ? (
        <>
          {/* One bar, segmented by dimension — the share each contributed. */}
          <div style={{ display: "flex", height: 8, borderRadius: 2, overflow: "hidden", marginBottom: 10, background: "#0F1923" }}>
            {parts.map((p) => (
              <div key={p.key} style={{ width: `${p.share}%`, background: p.color }} title={`${p.label} ${p.value}`} />
            ))}
          </div>
          <div style={{ display: "flex", gap: 18, flexWrap: "wrap" }}>
            {parts.map((p) => (
              <div key={p.key} style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <div style={{ width: 8, height: 8, borderRadius: "50%", background: p.color, flexShrink: 0 }} />
                <div style={{ fontFamily: "monospace", fontSize: 11, color: "#8A9BAC" }}>
                  {p.label} <span style={{ color: "#E8E0D0", fontWeight: 600 }}>{p.value}</span>
                  <span style={{ color: "#3A4D5C" }}> · {p.share.toFixed(0)}%</span>
                </div>
              </div>
            ))}
          </div>
        </>
      ) : (
        <div style={{ fontFamily: "monospace", fontSize: 11, color: "#5A6878" }}>
          Ranked, but no single dimension is contributing points.
        </div>
      )}

      {note && (
        <div style={{ fontFamily: "monospace", fontSize: 10, color: "#8A6A5A", lineHeight: 1.6, marginTop: 12, paddingTop: 10, borderTop: "1px solid #1A2530" }}>
          {note}
        </div>
      )}
    </div>
  );
}
