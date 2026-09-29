/**
 * Why is this country on the cross-asset table?
 *
 * `D-0070`. The table carried nine columns of numbers and a 140px gauge, and
 * left the reader to assemble the story from them. The row already knows the
 * story — `signal_tier`, the two MoM figures, the consecutive counts, whether
 * spot gold is rising — it just never said it.
 *
 * Composed here rather than inline in the table so it can be tested. The
 * alternative is a ternary chain inside a `<td>`, which is where the COMPOSITE
 * tab's stale tooltips came from (`F-0081`).
 *
 * Deliberately not an LLM call. This is a description of figures already in
 * the row: it must be identical for identical rows, cost nothing, and work
 * when the brief endpoint is down.
 */

const pct = (v, digits = 1) => `${v > 0 ? "+" : ""}${Number(v).toFixed(digits)}%`;

/**
 * A short analysis of one cross-asset row.
 *
 * Returns `{ headline, detail }`. `headline` is the mechanism in a few words;
 * `detail` is the evidence for it. Both are plain strings — the caller styles
 * them, and a test can read them.
 */
export function describeCrossAsset(row) {
  if (!row) return { headline: "", detail: "" };

  const tic = row.tic_mom_pct;
  const gold = row.gold_mom_pct;
  const ticMonths = row.tic_consecutive_months ?? 0;
  const goldMonths = row.gold_consecutive_months ?? 0;
  const exited = Boolean(row.no_tic_holdings);
  const spotRising = Boolean(row.spot_gold_rising);
  const spot3m = row.spot_gold_3m_pct;

  const evidence = [];
  if (exited) {
    evidence.push("holds zero US Treasuries");
  } else if (tic != null && tic < 0) {
    evidence.push(`Treasuries ${pct(tic, 2)}${ticMonths >= 2 ? ` for ${ticMonths}mo` : ""}`);
  }
  if (gold != null && gold < 0) {
    evidence.push(`gold ${pct(gold, 2)}${goldMonths >= 2 ? ` for ${goldMonths}mo` : ""}`);
  }
  if (row.gold_tonnes) {
    evidence.push(`${Number(row.gold_tonnes).toLocaleString()}t held`);
  }
  if (row.treseg_signal === "REBUILDING" && row.treseg_trend_pct != null) {
    evidence.push(`non-$ reserves ${pct(row.treseg_trend_pct)} YoY`);
  } else if (row.treseg_signal === "DEPLETING" && row.treseg_trend_pct != null) {
    evidence.push(`non-$ reserves ${pct(row.treseg_trend_pct)} YoY`);
  }

  let headline;
  switch (row.signal_tier) {
    case "DIVERGENCE":
      // The one that matters most: selling an asset whose price is rising is
      // not portfolio management, it is a liquidity need.
      headline = spotRising && spot3m != null
        ? `Selling gold into a ${pct(spot3m)} 3M rally — raising cash, not rebalancing`
        : "Selling gold into a rising price — raising cash, not rebalancing";
      break;
    case "CROSS-ASSET":
      headline = "Reducing Treasuries and gold together — broad reserve drawdown";
      break;
    case "EXITED":
      headline = row.gold_tonnes
        ? "Fully out of Treasuries while retaining gold — deliberate reserve restructuring"
        : "Fully out of US Treasuries";
      break;
    case "T-ONLY":
      headline = ticMonths >= 3
        ? "Sustained Treasury reduction — structural, not tactical"
        : "Reducing Treasury holdings";
      break;
    case "AU-ONLY":
    case "Au ONLY":
      headline = "Reducing gold while Treasuries hold — the reverse of the usual pattern";
      break;
    default:
      headline = "Scored on a single dimension";
  }

  if (row.multiplier > 1) {
    headline += ` · ${row.multiplier}× applied`;
  }

  return { headline, detail: evidence.join(" · ") };
}
