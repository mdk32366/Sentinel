import { useApiResource } from "../../hooks/useApiResource";
import { tabHref } from "../../lib/countryRoute";
import { InfoTip } from "../InfoTip";

/**
 * Treasury auction demand on the USA card (D-0108).
 *
 * The card's case is that US stress is whether the market keeps accepting
 * the terms as foreign demand weakens. Auction demand is the most direct
 * measure of that, so the card shows the last 90 days of weak-demand signals
 * (D-0107) and links to AUCTIONS for the detail.
 *
 * Display only. The composite excludes the US, and whether auction demand
 * feeds any score is an owner ruling not yet made (ORDER auction-demand §11).
 */
const MONO = { fontFamily: "monospace" };
const RED = "#FF4444";
const AMBER = "#E8C547";

export function AuctionDemandStrip() {
  const { data } = useApiResource("/auctions/signals?days=90");
  if (!data?.counts) return null;

  const { alert = 0, watch = 0 } = data.counts;
  const recent = [...(data.signals ?? [])]
    .sort((a, b) => (a.auction_date < b.auction_date ? 1 : -1))[0];
  const color = alert ? RED : watch ? AMBER : "#5DB87A";

  const tiles = [
    { label: "Alerts, 90 days", val: `${alert} alert${alert === 1 ? "" : "s"}`,
      tip: "Auctions where bid-to-cover was 2 or more sd below normal for the term AND primary dealers took 2 or more sd more than normal: low cover, with dealers left holding the issue (D-0107)." },
    { label: "Watches, 90 days", val: `${watch} watch${watch === 1 ? "" : "es"}`,
      tip: "Auctions where either one of those went past 2.5 sd on its own (D-0107)." },
    { label: "Most recent", val: recent ? `${recent.term} · ${recent.auction_date}` : "—",
      tip: "The latest flagged auction in the window, alert or watch. The AUCTIONS tab ranks them all, worst first." },
  ];

  return (
    <div data-testid="usa-auction-demand" style={{
      ...MONO, background: "#0A1520", border: "1px solid #1A2530", borderLeft: `3px solid ${color}`,
      borderRadius: 2, padding: "12px 18px", marginBottom: 20,
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 10 }}>
        <span style={{ fontSize: 11, color: "#8A9BAC", letterSpacing: "0.1em" }}>
          TREASURY AUCTION DEMAND
          <span style={{ marginLeft: 10, fontSize: 10, color: "#3A4D5C" }}>shown, not scored</span>
        </span>
        <a href={tabHref("AUCTIONS")} style={{ fontSize: 11, color: "#5A6878", textDecoration: "none" }}>
          Open AUCTIONS →
        </a>
      </div>
      {alert + watch === 0 ? (
        <div style={{ fontSize: 12, color: "#5DB87A" }}>
          No weak-demand signal at any Treasury auction in the last 90 days.
        </div>
      ) : (
        <div style={{ display: "flex", gap: 24, flexWrap: "wrap" }}>
          {tiles.map((s) => (
            <div key={s.label}>
              <InfoTip as="div" title={s.label} tip={s.tip} placement="below" style={{ fontSize: 10, color: "#5A6878", marginBottom: 3 }}>
                <span style={{ borderBottom: "1px dashed #2A3D50" }}>{s.label}</span>
              </InfoTip>
              <div style={{ fontSize: 14, color: s.label.startsWith("Alerts") && alert ? RED
                : s.label.startsWith("Watches") && watch ? AMBER : "#E8E0D0" }}>{s.val}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
