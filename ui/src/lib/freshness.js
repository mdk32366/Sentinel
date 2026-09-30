/**
 * How old is this data, and should the reader be told loudly?
 *
 * `F-0083`: the COMPOSITE tab's footer read "Data as of 2025-12" while that
 * data was **302 days old**. The date was correct and the sentence was true,
 * and a reader would take a monthly series dated December for a monthly
 * series that is a month or two behind — which is what TIC normally is.
 *
 * A date is not a freshness statement. An age is.
 */

/** Days between `asOf` and now. Accepts "2025-12", "2025-12-01" and ISO. */
export function ageInDays(asOf, now = new Date()) {
  if (!asOf) return null;
  const text = String(asOf);
  const parts = /^(\d{4})-(\d{2})(?:-(\d{2}))?/.exec(text);
  if (!parts) return null;
  // Both endpoints as UTC midnight, then a whole-day difference.
  //
  // Not local midnight: the interval Dec 2025 -> Sep 2026 crosses a DST
  // transition, so the naive millisecond difference is 302 days MINUS an
  // hour, and Math.floor turns that into 301. The test caught it against the
  // real case. Calendar arithmetic on local Dates is off by one whenever the
  // span crosses a clock change - the same hazard as F-0071, one layer up.
  const then = Date.UTC(+parts[1], +parts[2] - 1, parts[3] ? +parts[3] : 1);
  const today = Date.UTC(now.getFullYear(), now.getMonth(), now.getDate());
  return Math.round((today - then) / 86400000);
}

/**
 * A freshness verdict for a date the UI is about to display.
 *
 * Returns `{ age, stale, text, color }`. `text` is what to put beside the
 * date — an age, and when it is beyond tolerance, what that means. Saying
 * "302 days old" is the part that turns a true sentence into a useful one.
 *
 * `F-0087`: this used to default `toleranceDays` to a `TIC_TOLERANCE_DAYS`
 * of 100, copied here from the threshold at which
 * `pipelines/treasury_holdings.py` refuses the file. But that is the
 * pipeline's *rejection* threshold, not the point at which a reader should
 * be worried, and `pipelines/freshness_watchdog.py` — the component that
 * actually owns this question — judges TIC at **55**. So a 60-day-old TIC
 * date would have been called fine by the footer and "not current" by the
 * confidence strip immediately above it. Two components contradicting each
 * other about one date is worse than either being wrong alone.
 *
 * Called without a tolerance it now reports the age and **makes no ruling**:
 * `stale` stays false and the colour stays neutral. The tolerances live on
 * the server, one per source, and reach the screen through
 * `DataConfidence`. A caller that has the server's number for its source may
 * pass it; nothing in the client invents one.
 */
export function freshness(asOf, toleranceDays = null, now = new Date()) {
  const age = ageInDays(asOf, now);
  if (age == null) return { age: null, stale: false, text: "", color: "#1E2D3D" };

  const stale = toleranceDays != null && age > toleranceDays;
  return {
    age,
    stale,
    // One wording, always spelled out. It used to read `${age}d` unless
    // this function had ruled the date stale - so once the ruling moved to
    // DataConfidence (F-0087), a 302-day-old TIC footer would have read
    // "(302d)". That is the terse form of exactly the sentence F-0083 was
    // about. A format that depends on a verdict this no longer makes is a
    // format that hides the number when it matters most.
    text: age === 1 ? "1 day old" : `${age} days old`,
    // Failure-red only when it is genuinely beyond what the source's own
    // cadence explains. An ordinary monthly lag is not a fault.
    color: stale ? "#E07B5A" : "#1E2D3D",
  };
}


/** The worst status in a set — what the strip reports at a glance. */
export function worstStatus(sources) {
  const order = ["ok", "unknown", "anomaly", "stale", "critical"];
  return (sources || []).reduce(
    (worst, s) => (order.indexOf(s.status) > order.indexOf(worst) ? s.status : worst),
    "ok",
  );
}
