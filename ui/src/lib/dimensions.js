/**
 * The composite stress model, as the scorer actually computes it.
 *
 * `F-0076`: the COMPOSITE tab's methodology panel listed **four** dimensions.
 * `pipelines/composite_stress.py` sums **six** and then applies multipliers:
 *
 *     raw_score = tic_score + gold_score + monetary_score
 *               + petro_score + cds_score
 *
 * Monetary/M2 (0-35), Sovereign CDS (0-20) and the non-dollar reserve
 * multiplier were all absent from the explanation.
 *
 * `D-0066` then retired Sovereign Spread from scoring: it could not fire
 * for any country (`F-0079`). It is still measured and shown - the spread
 * itself is a real fact - but it is not a scoring dimension, so it is not
 * in this list. A reader could not
 * reconcile a score of 179.7 with a panel whose parts sum to 130, and CDS —
 * which is the entire score for some countries — appeared nowhere.
 *
 * `key` matches the field name in the composite API response, so the panel and
 * the per-country breakdown read from the same list, and
 * `tests/test_composite_dimensions.py` cross-checks these keys and maxima
 * against the Python scorer.
 */
export const STRESS_DIMENSIONS = [
  {
    key: "tic_score",
    label: "Treasury",
    max: 50,
    color: "#C8A96E",
    desc: "MoM decline + consecutive months",
  },
  {
    key: "gold_score",
    label: "Gold Reserves",
    max: 40,
    color: "#E8C547",
    desc: "QoQ decline + consecutive quarters",
  },
  {
    key: "monetary_score",
    label: "Monetary / M2",
    max: 35,
    color: "#6A8FC4",
    desc: "Broad money growth — domestic debasement",
  },
  {
    key: "petro_score",
    label: "Petrodollar",
    max: 20,
    color: "#E07B5A",
    desc: "Oil price drop for oil-dependent nations",
  },
  {
    key: "cds_score",
    label: "Sovereign CDS",
    max: 20,
    color: "#C47EB8",
    desc: "5Y level + widening — the market's own default price",
  },
];

/**
 * The CDS level ladder, mirroring `CDS_ELEVATED_BPS` / `CDS_SIGNIFICANT_BPS`
 * / `CDS_DISTRESS_BPS` in `pipelines/composite_stress.py`.
 *
 * `F-0081`: the COMPOSITE table's CDS tooltip said ">100bps = 5 pts; >250 =
 * 10; >500 = 15" for as long as those numbers were right, and kept saying it
 * after `D-0065` and `D-0067` changed them. Prose describing a constant drifts
 * the moment the constant moves, and nothing tests prose.
 *
 * The tooltip is now built from this, and
 * `tests/test_composite_dimensions.py` cross-checks it against the Python
 * constants — so the text cannot describe a ladder the scorer does not use.
 */
export const CDS_BANDS = [
  { bps: 200, pts: 5, label: "elevated" },
  { bps: 350, pts: 10, label: "significant" },
  { bps: 600, pts: 15, label: "distress" },
];

/** "…>200bps = 5 pts (elevated); >350bps = 10 pts (significant); …" */
export function cdsBandText() {
  return CDS_BANDS.map((b) => `>${b.bps}bps = ${b.pts} pts (${b.label})`).join("; ");
}

/** The highest raw score before multipliers. */
export const MAX_RAW_SCORE = STRESS_DIMENSIONS.reduce((sum, d) => sum + d.max, 0);

/**
 * Applied to the raw score rather than added to it.
 *
 * The non-dollar reserve trend is dimension 6 in the scorer and is a
 * multiplier, not points — which is exactly why it was easy to leave out of a
 * panel headed "SCORE =".
 */
export const STRESS_MULTIPLIERS = [
  { label: "× 1.5 cross-asset", desc: "Treasury and gold both selling", color: "#E07B5A" },
  { label: "× 2.0 divergence", desc: "Gold sold into a rising gold price", color: "#FF4444" },
  { label: "× 1.2 non-$ reserves", desc: "Exited Treasuries and rebuilding reserves ex-gold", color: "#7EC4A0" },
];

/**
 * A country's score broken into the dimensions that actually contributed.
 *
 * Returns the non-zero ones, largest first, each with its share of the raw
 * total — the question "what is driving this score?" answered from the same
 * numbers the tiering used, rather than re-derived.
 */
export function scoreBreakdown(row) {
  if (!row) return [];
  const parts = STRESS_DIMENSIONS
    .map((d) => ({ ...d, value: Number(row[d.key]) || 0 }))
    .filter((d) => d.value > 0)
    .sort((a, b) => b.value - a.value);

  const raw = parts.reduce((sum, d) => sum + d.value, 0);
  return parts.map((d) => ({ ...d, share: raw > 0 ? (d.value / raw) * 100 : 0 }));
}
