import { METRICS, TABS, US_SPREADS } from "./lib/constants";
import { navigateToTab } from "./lib/countryRoute";
// ORDER-03 Part F step 4: App owns which tab is open and what is selected.
// Everything that talks to the API lives in a hook (F-0063).
import { useApiResource } from "./hooks/useApiResource";
import { useHashRoute } from "./hooks/useHashRoute";
import { useMarketSeries } from "./hooks/useMarketSeries";
import { Ticker } from "./components/Ticker";
import { AboutTab } from "./pages/AboutTab";
import { AdminTab } from "./pages/AdminTab";
import { AuctionsTab } from "./pages/AuctionsTab";
import { CDSTab } from "./pages/CDSTab";
import { CompositeTab } from "./pages/CompositeTab";
import { CountryTab } from "./pages/CountryTab";
import { CrossAssetTab } from "./pages/CrossAssetTab";
import { ForeignBondsTab } from "./pages/ForeignBondsTab";
import { GoldReservesTab } from "./pages/GoldReservesTab";
import { HoldingsTab } from "./pages/HoldingsTab";
import { MarketsTab } from "./pages/MarketsTab";



export default function App() {
  // D-0091: the open tab and the country card live in the URL hash
  // (`#/holdings`, `#/country/RUS`), so a card has an address that can be
  // linked, refreshed, opened in a new tab and walked with Back.
  const { tab, iso: countryIso, view } = useHashRoute();
  const { latest, prior } = useMarketSeries();
  const { data: stats } = useApiResource(`/stats`);
  const { data: health } = useApiResource(`/health`);

  const tickerData = METRICS.map(m => ({ ...m, latest: latest[m.code] })).filter(m => m.latest != null);

  return (
    <div style={{ minHeight: "100vh", background: "#060D14", color: "#E8E0D0", fontFamily: "'Inter', system-ui, sans-serif" }}>
      {/* Header */}
      <div style={{ borderBottom: "1px solid #1A2530", padding: "0 32px", display: "flex", alignItems: "center", justifyContent: "space-between", height: 52 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <div style={{ width: 8, height: 8, borderRadius: "50%", background: "#C8A96E", boxShadow: "0 0 8px #C8A96E" }} />
          <span style={{ fontFamily: "monospace", fontSize: 13, letterSpacing: "0.15em", color: "#8A9BAC", textTransform: "uppercase" }}>Project Sentinel</span>
          <span style={{ color: "#1E2D3D", margin: "0 4px" }}>|</span>
          <span style={{ fontFamily: "monospace", fontSize: 11, color: "#3A4D5C", letterSpacing: "0.1em" }}>TREASURY MONITOR</span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          {health && <span style={{ fontFamily: "monospace", fontSize: 11, color: health.status === "healthy" ? "#5DB87A" : "#E07B5A" }}>● {health.status}</span>}
          {stats && <span style={{ fontFamily: "monospace", fontSize: 11, color: "#3A4D5C" }}>{stats.timeseries_records?.toLocaleString()} records</span>}
        </div>
      </div>

      <Ticker data={tickerData} />

      {/* Tabs */}
      <div style={{ borderBottom: "1px solid #1A2530", padding: "0 32px", display: "flex", gap: 0 }}>
        {TABS.map(t => (
          <button key={t} onClick={() => navigateToTab(t)} style={{
            background: "transparent", border: "none",
            borderBottom: `2px solid ${tab === t ? "#C8A96E" : "transparent"}`,
            color: tab === t ? "#C8A96E" : "#3A4D5C",
            padding: "12px 20px", cursor: "pointer",
            fontFamily: "monospace", fontSize: 12, letterSpacing: "0.1em", marginBottom: -1,
          }}>{t}</button>
        ))}
      </div>

      <div style={{ padding: "28px 32px", maxWidth: 1400, margin: "0 auto" }}>

        {tab === "MARKETS" && (
          // D-0074: the twelve cards draw on four sources of different
          // cadence - daily yields, weekly dollar index, monthly CPI and M2.
          // Sentinel D-0111: the layout now lives in pages/MarketsTab.jsx so
          // FOREIGN-BONDS reuses it; MARKETS renders byte-identical (AC-1).
          <MarketsTab
            metrics={METRICS}
            sourceKeys={["treasury_yields", "oil", "dollar_index", "gold_price"]}
            spreads={US_SPREADS}
            defaultActive={["DGS10", "DGS2", "DFF", "DCOILWTICO"]}
            sourceNote="Source: FRED / Federal Reserve Bank of St. Louis"
            lastDataPoint={stats?.data_latest}
            latest={latest}
            prior={prior}
          />
        )}
        {tab === "FOREIGN-BONDS" && <ForeignBondsTab />}

        {/* D-0091: every country mention is a <CountryLink> to #/country/<ISO3>,
            so the tabs no longer need a select callback from here. */}
        {tab === "HOLDINGS" && <HoldingsTab latestAll={latest} />}
        {tab === "CROSS-ASSET" && <CrossAssetTab />}
        {tab === "GOLD" && <GoldReservesTab latestAll={latest} />}
        {tab === "COMPOSITE" && <CompositeTab />}
        {tab === "CDS" && <CDSTab />}
        {tab === "AUCTIONS" && <AuctionsTab key={view ?? "latest"} initialView={view} />}
        {tab === "COUNTRY" && (
          <CountryTab initialIso={countryIso} latestAll={latest} />
        )}
        {tab === "ADMIN" && <AdminTab />}
        {tab === "ABOUT" && <AboutTab />}

      </div>
    </div>
  );
}

