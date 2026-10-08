/**
 * The four rate paths the USA dashboard will model, and their consequences.
 *
 * `A-0012`: these are editorial judgement, not model output. They are stated
 * as ranges, and the panel's own subtitle says why — the Fed controls the
 * short end and the bond market controls the long end. Nothing here is
 * derived from the database, so nothing here goes stale silently; it goes
 * stale loudly, by being wrong in a way a reader can see.
 *
 * Separate from the component because a file that exports both a component
 * and a constant breaks fast refresh, and because these are worth testing.
 */
export const SCENARIOS = [
  { label: "Hold (4%)", ff: 4.0, color: "#5A6878", desc: "Status quo. Yield curve flat. Deficit serviceable but growing. Foreign holders reducing slowly." },
  { label: "Cut to 2%", ff: 2.0, color: "#E8C547", desc: "Moderate easing. Long end likely rises 50-100bps — bear steepener. Dollar weakens. Foreign selling continues." },
  { label: "Cut to 1%", ff: 1.0, color: "#E07B5A", desc: "Aggressive signal. Long end rises 100-200bps. Dollar weakens sharply. Foreign holders accelerate selling. Deficit widens as long-term borrowing costs stay high." },
  { label: "Cut to 0% (ZIRP)", ff: 0.0, color: "#FF4444", desc: "2020-2022 playbook: M2 surged 27%, CPI hit 9%, 10Y rose from 0.5% to 3.5%. The bond market doesn't care what the Fed says." },
];

/**
 * The six consequences shown for a selected scenario.
 *
 * Every one of them gets harsher as the Fed Funds target falls, which is the
 * point the panel is making: cutting the short end does not relieve the long
 * end, and on this reading it does the opposite.
 */
export function scenarioOutcomes({ ff }) {
  const hot = ff <= 1;
  return [
    {
      label: "Fed Funds Target", val: `${ff.toFixed(1)}%`, color: "#5DB87A",
      tip: "The policy rate this scenario assumes. The Fed sets it directly; everything beside it is the market's likely response, which the Fed does not control.",
    },
    {
      label: "Likely 10Y Response",
      val: ff <= 0 ? "Rises 150-250bps" : ff <= 1 ? "Rises 100-200bps" : ff <= 2 ? "Rises 50-100bps" : "Holds ±25bps",
      color: hot ? "#E07B5A" : "#E8C547",
      tip: "Editorial range for the 10-year yield's move under this path, not model output (A-0012). The reference is 2020-22: after the Fed went to zero, the 10Y rose from 0.5% to 3.5%.",
    },
    {
      label: "Yield Curve Shape", val: hot ? "Bear Steepener ⚠" : ff <= 2 ? "Steepens" : "Flat", color: hot ? "#E07B5A" : "#E8C547",
      tip: "Editorial judgement. A bear steepener is short rates falling while long rates rise: the market charging more to lend long even as the Fed eases.",
    },
    {
      label: "Dollar Effect", val: hot ? "Weakens sharply" : ff <= 2 ? "Weakens" : "Stable", color: hot ? "#E07B5A" : "#E8C547",
      tip: "Editorial judgement of the dollar's direction under this path. Lower policy rates cut the return on holding dollars.",
    },
    {
      label: "Foreign Selling", val: hot ? "Accelerates" : "Continues", color: hot ? "#E07B5A" : "#E8C547",
      tip: "Editorial judgement of foreign holders' behaviour under this path. What foreign official holders are actually doing is measured from TIC in the Foreign Official strip at the top of this page.",
    },
    {
      label: "Breaking Point Risk",
      val: ff <= 0 ? "CRISIS" : hot ? "HIGH" : "MODERATE",
      color: ff <= 0 ? "#FF4444" : hot ? "#E07B5A" : "#E8C547",
      tip: "Editorial rating of how close this path pushes interest toward the 25% and 35% of revenue lines in the Fiscal Breaking Point Calculator.",
    },
  ];
}
