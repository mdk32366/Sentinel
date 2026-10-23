import { useApiResource } from "../hooks/useApiResource";
import { useSeries } from "../hooks/useMarketSeries";
import {
  FOREIGN_BOND_CODES, bdfAttribution, eaBenchmark, foreignBondCells, foreignBondSourceKey, foreignBondSpreads,
} from "../lib/constants";
import { EaBenchmarkPanel } from "../components/foreignBonds/EaBenchmarkPanel";
import { MarketsTab } from "./MarketsTab";

const SOURCE_KEYS = [
  "foreign_bonds_de", "foreign_bonds_gb", "foreign_bonds_jp", "foreign_bonds_fr",
  // Sentinel D-0115 (batch 2a).
  "foreign_bonds_ca", "foreign_bonds_se", "foreign_bonds_au", "foreign_bonds_no", "foreign_bonds_es",
  "foreign_bonds_ea",
  // Sentinel D-0116 (batch 2b-1).
  "foreign_bonds_pl", "foreign_bonds_it",
];
const DEFAULT_ACTIVE = ["FB_DE_10Y", "FB_GB_10Y", "FB_JP_10Y"];
const SOURCE_NOTE = "Source: Deutsche Bundesbank · Bank of England · Ministry of Finance Japan · Bank of Canada · Sveriges Riksbank · Reserve Bank of Australia · Norges Bank · Banco de España · Ministry of Finance Poland (as of last auction) · Banca d'Italia (monthly)";
const OK = new Set(["ok", "anomaly"]);

/**
 * FOREIGN-BONDS (#/foreign-bonds) - Sentinel D-0111, vault:D-0057.
 *
 * MARKETS with different inputs: Germany, UK, Japan and France at
 * 2/5/7/10/30Y from official published curves (France: Banque de France TEC,
 * Sentinel D-0112; amendment 1 took the monthly OECD FR 10Y off this tab).
 * Display only - nothing here feeds a score. Sentinel D-0115 adds Canada,
 * Sweden, Australia, Norway and Spain at their own published tenors, and the
 * euro-area ECB benchmark panel (AAA and all-issuer curves) above the grid.
 *
 * A spread quotes a number only while the watchdog calls both legs' sources
 * current; one stale leg leaves it in place reading "—" rather than a number
 * against a frozen leg (amendment 3). Every entry, OAT–Bund included, is pp.
 */
export function ForeignBondsTab() {
  const { latest, prior, latestDate, dates, series } = useSeries(FOREIGN_BOND_CODES);
  const { data: freshness } = useApiResource(`/freshness`);

  const statusOf = {};
  for (const s of freshness?.sources ?? []) statusOf[s.key] = s.status;
  // Until the watchdog answers, legs count as fresh: the strip then shows what
  // MARKETS would, and the DataConfidence strip above it carries the verdict.
  const fresh = (code) => {
    const key = foreignBondSourceKey(code);
    return !freshness || !key || statusOf[key] == null || OK.has(statusOf[key]);
  };

  return (
    <>
    <EaBenchmarkPanel ea={eaBenchmark(latest, dates)} />
    <MarketsTab
      metrics={foreignBondCells()}
      sourceKeys={SOURCE_KEYS}
      spreads={(l) => foreignBondSpreads(l, fresh, series)}
      defaultActive={DEFAULT_ACTIVE}
      sourceNote={`${SOURCE_NOTE} · ${bdfAttribution(dates)}`}
      lastDataPoint={latestDate}
      columns={5}
      latest={latest}
      prior={prior}
    />
    </>
  );
}
