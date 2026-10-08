import { useState } from "react";

import { useApiResource } from "../hooks/useApiResource";
import { AuctionChart } from "../components/auctions/AuctionChart";
import { AuctionTable } from "../components/auctions/AuctionTable";
import { DataAsOf } from "../components/DataAsOf";
import { DataConfidence } from "../components/DataConfidence";
import { LoadFailure } from "../components/LoadFailure";
import { CHARTED_TERMS, STALE_BUSINESS_DAYS, businessDaysSince, isStale } from "../lib/auctions";

/**
 * Auction Demand (ORDER auction-demand §7, D-0097..D-0105).
 *
 * Treasury always sells the full offering, so the signal is how much demand
 * showed up against what was sold and who absorbed it. Bid-to-cover here is
 * the recomputed one, SOMA excluded (§2); a row where it disagrees with
 * Treasury's reported figure is marked, not hidden.
 *
 * With no term chosen the table is the latest auction for each charted term,
 * newest first. Choosing a term shows that term's recent auctions and its
 * bid-to-cover chart.
 *
 * `today` is injectable so the stale rule (D-0101) can be tested on a fixed
 * date. All copy is placeholder pending the owner's wording.
 */

const TABLE_LIMIT = 52;
const MONO = { fontFamily: "monospace" };

function TermButton({ label, active, onClick }) {
  return (
    <button type="button" onClick={onClick} style={{
      ...MONO, fontSize: 12, padding: "5px 12px", cursor: "pointer", borderRadius: 2,
      background: active ? "#1A2530" : "transparent",
      border: `1px solid ${active ? "#C8A96E" : "#1E2D3D"}`,
      color: active ? "#C8A96E" : "#5A6878",
    }}>{label}</button>
  );
}

export function AuctionsTab({ today }) {
  const now = today ?? new Date();
  const [term, setTerm] = useState(null);

  const summary = useApiResource("/auctions/summary");
  const list = useApiResource(term ? `/auctions?term=${term}` : null, { enabled: Boolean(term) });

  if (summary.loading) {
    return <div style={{ ...MONO, display: "flex", alignItems: "center", justifyContent: "center", height: 300, fontSize: 13, color: "#3A4D5C" }}>loading auctions...</div>;
  }
  if (summary.error || !summary.data) {
    return <LoadFailure what="Treasury auctions" error={summary.error}
      detail="If the table is empty, the Treasury_Auctions job has not run yet (ADMIN)." />;
  }

  const dataAsOf = summary.data.data_as_of;
  const termRows = list.data?.auctions ?? [];
  const rows = term ? termRows.slice(0, TABLE_LIMIT) : summary.data.terms;
  const stale = isStale(dataAsOf, now);
  const alerts = rows.filter((r) => r.demand_signal === "alert").length;
  const watches = rows.filter((r) => r.demand_signal === "watch").length;

  return (
    <div>
      <DataConfidence sourceKeys={["treasury_auctions"]} />

      {stale && (
        <div data-testid="stale-banner" style={{
          ...MONO, fontSize: 12, color: "#E8C547", border: "1px solid #E8C54766",
          background: "#E8C5470F", borderRadius: 2, padding: "10px 16px", marginBottom: 16,
        }}>
          No new auction for {businessDaysSince(dataAsOf, now)} business days (latest {dataAsOf}).
          More than {STALE_BUSINESS_DAYS} means the feed has stopped, not that Treasury has.
        </div>
      )}

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 16 }}>
        <TermButton label="Latest" active={term === null} onClick={() => setTerm(null)} />
        {CHARTED_TERMS.map((t) => (
          <TermButton key={t} label={t} active={term === t} onClick={() => setTerm(t)} />
        ))}
      </div>

      {term && list.error && <LoadFailure what={`${term} auctions`} error={list.error} />}
      {term && !list.loading && !list.error && <AuctionChart term={term} rows={termRows} />}

      <div style={{ background: "#0A1520", border: "1px solid #1A2530", borderRadius: 2, padding: "16px 0" }}>
        <div style={{ ...MONO, padding: "0 16px 12px", fontSize: 12, color: "#8A9BAC", letterSpacing: "0.1em" }}>
          {term ? `${term} AUCTIONS · MOST RECENT ${Math.min(TABLE_LIMIT, termRows.length)}` : "LATEST AUCTION PER TERM"}
          <span data-testid="signal-count" style={{ marginLeft: 10, color: alerts ? "#FF4444" : watches ? "#E8C547" : "#3A4D5C" }}>
            {alerts} alert{alerts === 1 ? "" : "s"} · {watches} watch{watches === 1 ? "" : "es"}
          </span>
          <span style={{ marginLeft: 10, fontSize: 10, color: "#3A4D5C" }}>
            B2C excludes SOMA · z against the previous {summary.data.window_n} auctions of the same term (at least {summary.data.min_observations}) · hover a row for bidders
          </span>
        </div>
        {term && list.loading
          ? <div style={{ ...MONO, padding: 16, fontSize: 12, color: "#3A4D5C" }}>loading {term}...</div>
          : <AuctionTable rows={rows} />}
      </div>

      <DataAsOf asOf={dataAsOf} label="Latest auction" source="US Treasury, Fiscal Data auctions_query" />
    </div>
  );
}
