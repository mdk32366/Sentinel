import { useApiResource } from "../../hooks/useApiResource";
import { viewHref } from "../../lib/countryRoute";
import { FrequencyChart } from "../auctions/FrequencyChart";
import { BAND, frequencyContext } from "../../lib/auctions";
import { InfoTip } from "../InfoTip";

/**
 * Treasury auction signal frequency on the USA card (D-0109).
 *
 * Owner, 2026-10-08: signal spikes get a card of their own here, with a
 * tooltip and a link to the Signals view on AUCTIONS. The number of signals is
 * the signal: one weak auction is noise, a run of them is a regime in demand
 * for US debt. Shown, not scored (ORDER auction-demand §11).
 */
const MONO = { fontFamily: "monospace" };

export function SignalFrequencyCard() {
  const { data } = useApiResource("/auctions/regime");
  const f = data?.frequency;
  if (!f) return null;
  const band = BAND[f.band] ?? BAND.normal;

  return (
    <div data-testid="usa-signal-frequency" style={{
      ...MONO, background: "#0F1923", border: "1px solid #1A2530", borderTop: `2px solid ${band.color}`,
      borderRadius: 2, padding: "14px 20px", marginBottom: 20, display: "grid", gap: 10,
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 12, flexWrap: "wrap" }}>
        <InfoTip as="div" title="Auction signal frequency" placement="below"
          tip={`How many Treasury auctions showed weak demand in the last ${f.window_days} days, across the ten charted terms: low bid-to-cover with dealers left holding the issue (alert), or either one alone and stronger (watch). One weak auction is noise; a run of them says buyers are stepping back from US debt. ELEVATED at ${f.elevated_at} or more, the top fifth of months since 2009. HIGH at ${f.high_at} or more, the top 3%. Shown, not scored.`}
          style={{ fontSize: 10, color: "#5A6878", textTransform: "uppercase", letterSpacing: "0.1em" }}>
          <span style={{ borderBottom: "1px dashed #2A3D50" }}>Auction signal frequency · 12 months</span>
        </InfoTip>
        <a href={viewHref("AUCTIONS", "signals")} style={{ fontSize: 11, color: "#5A6878", textDecoration: "none" }}>
          See every signal on AUCTIONS → Signals
        </a>
      </div>
      <div style={{ display: "flex", alignItems: "baseline", gap: 12, flexWrap: "wrap" }}>
        <span data-testid="usa-frequency-count" style={{ fontSize: 26, fontWeight: 700, color: band.color }}>{f.count}</span>
        <span data-testid="usa-frequency-band" style={{
          fontSize: 10, color: band.color, border: `1px solid ${band.color}66`, background: `${band.color}14`,
          borderRadius: 2, padding: "1px 6px", letterSpacing: "0.08em",
        }}>{band.label}</span>
        <span style={{ fontSize: 11, color: "#8A9BAC" }}>
          {f.alerts} alert{f.alerts === 1 ? "" : "s"} · {f.watches} watch{f.watches === 1 ? "" : "es"}
        </span>
        <span style={{ fontSize: 11, color: "#5A6878" }}>{frequencyContext(f)}</span>
      </div>
      <FrequencyChart frequency={f} height={60} />
    </div>
  );
}
