/**
 * Shaping the three country-detail series into chart rows.
 *
 * Each of these was inline in `CountryDetail`, and each does the same two
 * things slightly differently: truncate the date to its day, and pull one
 * numeric field out under a fixed key. Pulled out here because the arithmetic
 * — particularly `momChange` — is worth testing without mounting a chart.
 */

/** `{date, holdings}` rows from the TIC holdings envelope. */
export function ticSeries(ticHistory) {
  return (ticHistory?.holdings || []).map((h) => ({
    date: String(h.date).split("T")[0],
    holdings: h.holdings_billions_usd,
  }));
}

/** `{date, tonnes}` rows from the gold reserves envelope. */
export function goldSeries(goldHistory) {
  return (goldHistory?.reserves || []).map((h) => ({
    date: String(h.date).split("T")[0],
    tonnes: h.metric_tonnes,
  }));
}

/**
 * `{date, value}` rows from a raw `/timeseries` response.
 *
 * The reserves-ex-gold series arrives with its values as strings, so this
 * parses and then drops anything that did not become a number — a NaN reaching
 * Recharts renders as a gap with no indication that a value was present and
 * unreadable.
 */
export function reservesSeries(reservesHistory) {
  if (!Array.isArray(reservesHistory)) return [];
  return reservesHistory
    .map((h) => ({ date: String(h.date).split("T")[0], value: parseFloat(h.value) }))
    .filter((h) => !Number.isNaN(h.value));
}

/**
 * Month-on-month percentage change between the last two TIC observations.
 *
 * Null when there is nothing to compare against, and null when the earlier
 * observation is zero — a country re-entering from a fully exited position is
 * an infinite percentage increase, which the card would print as "Infinity%".
 */
export function momChange(rows) {
  if (!rows || rows.length < 2) return null;
  const latest = rows[rows.length - 1];
  const previous = rows[rows.length - 2];
  if (previous.holdings == null || latest.holdings == null) return null;
  if (previous.holdings === 0) return null;
  return ((latest.holdings - previous.holdings) / previous.holdings) * 100;
}
