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
 * The tolerance for each source, in days, before an age is worth flagging.
 *
 * TIC publishes monthly with roughly a two-month lag, so ~100 days is the
 * outer edge of ordinary. It matches `MAX_SOURCE_AGE_DAYS` in
 * `pipelines/treasury_holdings.py`, which is the threshold at which the
 * pipeline itself refuses the file — the UI and the pipeline should agree
 * about what "too old" means.
 */
export const TIC_TOLERANCE_DAYS = 100;

/**
 * A freshness verdict for a date the UI is about to display.
 *
 * Returns `{ age, stale, text, color }`. `text` is what to put beside the
 * date — an age, and when it is beyond tolerance, what that means. Saying
 * "302 days old" is the part that turns a true sentence into a useful one.
 */
export function freshness(asOf, toleranceDays = TIC_TOLERANCE_DAYS, now = new Date()) {
  const age = ageInDays(asOf, now);
  if (age == null) return { age: null, stale: false, text: "", color: "#1E2D3D" };

  const stale = age > toleranceDays;
  return {
    age,
    stale,
    text: stale ? `${age} days old` : `${age}d`,
    // Failure-red only when it is genuinely beyond what the source's own
    // cadence explains. An ordinary monthly lag is not a fault.
    color: stale ? "#E07B5A" : "#1E2D3D",
  };
}
