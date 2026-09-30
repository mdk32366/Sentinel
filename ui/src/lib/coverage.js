/**
 * Which scoring dimensions can actually speak about a given country.
 *
 * `A-0019`. `F-0097` removed the false-exit path, and the honest consequence is
 * that dimension 1 — 50 points, the largest in the model — can only score the
 * twenty countries SLT Table 5 names. The other 28 get nothing from it, not
 * because they look calm but because their position is unknown.
 *
 * A composite that ranks 48 sovereigns while its largest dimension reaches 20
 * of them is weighted in a way no reader would infer from the number alone. So
 * the surface says so. **No score changes** — this is disclosure, and `A-0019`
 * chose it over re-weighting precisely because re-weighting would change every
 * number in the model and needs a decision rather than an implementation.
 *
 * It generalises a pattern that already existed for one dimension:
 * `StressContribution` explained a rejected CDS quote rather than showing a
 * blank. Explaining TIC while leaving broad money silently at zero would have
 * been the half-honest version, so all three reasons live here and there is one
 * mechanism instead of two.
 */

/** How a rejected CDS quote is explained, rather than shown as a blank. */
const CDS_COVERAGE_NOTE = {
  "not on the board": "No CDS quoted for this sovereign.",
  "no coverage": "No CDS quoted for this sovereign.",
  "not quoted as a running spread":
    "CDS exists but is not quoted as a running spread — a defaulted or " +
    "points-upfront credit. Excluded from the score rather than read as a number.",
};

export function cdsCoverageNote(coverage) {
  if (!coverage || coverage === "quoted") return null;
  if (coverage.startsWith("stale")) {
    return `The last CDS quote is ${coverage.replace(/^stale \(|\)$/g, "")} — too old to price today. Excluded from the score.`;
  }
  return CDS_COVERAGE_NOTE[coverage] ?? `CDS excluded: ${coverage}.`;
}

/** Dimension 1's reason, and the one A-0019 is about. */
export function ticCoverageNote(row) {
  if (!row) return null;
  if (row.tic_state === "below_threshold") {
    const bn = row.tic_last_reported_bn;
    const when = row.tic_last_reported_date
      ? ` in ${row.tic_last_reported_date.slice(0, 7)}`
      : "";
    return (
      `Not covered by the Treasury dimension. SLT Table 5 names only the twenty ` +
      `largest holders and folds the rest into one "All Other" row, so this ` +
      `country's current position is unknown` +
      (bn != null ? ` — it last reported $${bn}bn${when}` : "") +
      `. Scored as nothing, not as zero (F-0097). The combined position of ` +
      `everyone in that row is shown above the table as TIC ALL OTHER HOLDERS ` +
      `(A-0019 option 2) — it moves with this country in it, but says nothing ` +
      `about this country specifically.`
    );
  }
  if (row.tic_state === "no_data") {
    return (
      "Not covered by the Treasury dimension. This country has never appeared " +
      "in the TIC major-holders table, so there is no observation to score."
    );
  }
  return null;
}

/** Dimension 3's reason. Already disclosed in the signal text; stated here too. */
export function monetaryCoverageNote(row) {
  if (!row || !row.m2_stale) return null;
  return (
    `Not covered by the Monetary dimension. This country's newest broad money ` +
    `figure is ${row.m2_year}, more than three years old, so it is shown but ` +
    `not scored (F-0092).`
  );
}

/**
 * Every dimension that cannot score this country, with why.
 *
 * Ordered by the points at stake, so the most consequential gap reads first.
 */
export function unavailableDimensions(row) {
  if (!row) return [];
  return [
    { key: "tic_score", label: "Treasury", max: 50, reason: ticCoverageNote(row) },
    { key: "monetary_score", label: "Monetary / M2", max: 35, reason: monetaryCoverageNote(row) },
    { key: "cds_score", label: "Sovereign CDS", max: 20, reason: cdsCoverageNote(row.cds_coverage) },
  ].filter((d) => d.reason);
}

/** Points the model could not reach for this country. */
export function unreachablePoints(row) {
  return unavailableDimensions(row).reduce((sum, d) => sum + d.max, 0);
}

/**
 * A short badge for a dense table.
 *
 * Deliberately terse and deliberately not alarming: an unavailable dimension is
 * a limit on what the score means, not a finding about the country. Colouring it
 * like a risk signal would be the opposite of the point.
 */
export function coverageBadge(row) {
  const missing = unavailableDimensions(row);
  if (!missing.length) return null;
  return {
    text: `${missing.length}✕`,
    title:
      `${unreachablePoints(row)} of 165 points cannot be scored for this ` +
      `country:\n\n` +
      missing.map((d) => `• ${d.label} (max ${d.max}): ${d.reason}`).join("\n\n"),
  };
}
