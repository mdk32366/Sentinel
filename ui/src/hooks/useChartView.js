import { useState } from "react";

import { RANGES } from "../lib/constants";

/**
 * The MARKETS-style chart state: which series are drawn, the range and
 * % CHANGE. Sentinel D-0111 review: a parent that outlives the tab (App, for
 * MARKETS) holds it and passes it to MarketsTab as `view`, so the choice
 * survives a tab change, as on master be64218.
 */
export function useChartView(defaultActive) {
  const [activeMetrics, setActiveMetrics] = useState(defaultActive);
  const [range, setRange] = useState(RANGES[1]);
  const [normalized, setNormalized] = useState(false);
  return { activeMetrics, setActiveMetrics, range, setRange, normalized, setNormalized };
}
