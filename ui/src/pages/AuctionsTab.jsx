import { useState } from "react";

import { useApiResource } from "../hooks/useApiResource";
import { AuctionChart } from "../components/auctions/AuctionChart";
import { AuctionTable } from "../components/auctions/AuctionTable";
import { FrequencyChart } from "../components/auctions/FrequencyChart";
import { BAND, frequencyContext } from "../lib/auctions";
import { DataAsOf } from "../components/DataAsOf";
import { DataConfidence } from "../components/DataConfidence";
import { InfoTip } from "../components/InfoTip";
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

// D-0108. Leaderboard windows: label -> days (0 = all history since 2008).
const WINDOWS = [["90D", 90], ["1Y", 365], ["3Y", 1095], ["Since 2008", 0]];

function SignalTally({ byTerm }) {
  const tiles = byTerm.map((t) => ({
    label: t.term,
    val: t.alerts || t.watches
      ? [t.alerts ? `${t.alerts} alert${t.alerts === 1 ? "" : "s"}` : null,
         t.watches ? `${t.watches} watch${t.watches === 1 ? "" : "es"}` : null].filter(Boolean).join(" · ")
      : "none",
    tip: t.last_signal_date
      ? `Weak-demand signals at ${t.term} auctions in this window. The most recent was on ${t.last_signal_date}.`
      : `No ${t.term} auction was flagged in this window.`,
    color: t.alerts ? "#FF4444" : t.watches ? "#E8C547" : "#3A4D5C",
  }));
  // One fixed row of ten. flex-wrap left the tenth tile (30Y) alone on a
  // second line, stretched across the page; minmax(0, 1fr) lets a long value
  // ("1 alert · 1 watch") wrap inside its own tile instead.
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(10, minmax(0, 1fr))", gap: 8, marginBottom: 16 }}>
      {tiles.map((s) => (
        <div key={s.label} data-testid={`tally-${s.label}`} style={{
          ...MONO, minWidth: 0, background: "#0F1923", border: "1px solid #1A2530",
          borderTop: `2px solid ${s.color}`, borderRadius: 2, padding: "8px 12px",
        }}>
          <InfoTip as="div" title={s.label} tip={s.tip} placement="below" style={{ fontSize: 10, color: "#5A6878", marginBottom: 4 }}>
            <span style={{ borderBottom: "1px dashed #2A3D50" }}>{s.label}</span>
          </InfoTip>
          <div style={{ fontSize: 12, color: s.color === "#3A4D5C" ? "#3A4D5C" : s.color }}>{s.val}</div>
        </div>
      ))}
    </div>
  );
}

const fmtRatio = (r) => (r == null ? "—" : `${Math.round(r * 100)}%`);

function RegimePanel() {
  const { data } = useApiResource("/auctions/regime");
  if (!data?.frequency) return null;
  const f = data.frequency;
  const band = BAND[f.band] ?? BAND.normal;
  const drift = (data.drift ?? []).map((d) => ({
    label: d.term,
    val: fmtRatio(d.ratio),
    drifting: d.drifting,
    tip: d.ratio == null
      ? `No ratio: ${d.term} does not yet have five years of auctions.`
      : `${d.term}: median bid-to-cover over the last 52 weeks is ${d.median_52w.toFixed(2)}, against ${d.median_5y.toFixed(2)} over five years. Drifting at 85% or less (D-0110).`,
  }));
  return (
    <div data-testid="signal-frequency" style={{
      ...MONO, background: "#0A1520", border: "1px solid #1A2530", borderLeft: `3px solid ${band.color}`,
      borderRadius: 2, padding: "14px 18px", marginBottom: 16, display: "grid", gap: 10,
    }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: 14, flexWrap: "wrap" }}>
        <InfoTip as="span" title="Signal frequency" placement="below"
          tip={`D-0109: weak-demand signals (D-0107 alerts and watches) across the ten charted terms in the last ${f.window_days} days. One weak auction is noise; a run of them is a regime. ELEVATED at ${f.elevated_at} or more, the top fifth of months since 2009; HIGH at ${f.high_at} or more, the top 3%.`}
          style={{ fontSize: 11, color: "#8A9BAC", letterSpacing: "0.1em" }}>
          <span style={{ borderBottom: "1px dashed #2A3D50" }}>SIGNAL FREQUENCY · 12 MONTHS</span>
        </InfoTip>
        <span data-testid="frequency-count" style={{ fontSize: 28, fontWeight: 700, color: band.color }}>{f.count}</span>
        <span data-testid="frequency-band" style={{
          fontSize: 10, color: band.color, border: `1px solid ${band.color}66`, background: `${band.color}14`,
          borderRadius: 2, padding: "1px 6px", letterSpacing: "0.08em",
        }}>{band.label}</span>
        <span style={{ fontSize: 11, color: "#8A9BAC" }}>
          {f.alerts} alert{f.alerts === 1 ? "" : "s"} · {f.watches} watch{f.watches === 1 ? "" : "es"}
        </span>
        <span style={{ fontSize: 11, color: "#5A6878" }}>{frequencyContext(f)}</span>
      </div>
      <FrequencyChart frequency={f} />
      <div style={{ display: "grid", gridTemplateColumns: "repeat(10, minmax(0, 1fr))", gap: 6 }}>
        {drift.map((d) => (
          <div key={d.label} data-testid={`drift-${d.label}`} style={{ minWidth: 0, fontSize: 11 }}>
            <InfoTip as="div" title={`${d.label} cover drift`} tip={d.tip} placement="below" style={{ color: "#5A6878", fontSize: 10 }}>
              <span style={{ borderBottom: "1px dashed #2A3D50" }}>{d.label}</span>
            </InfoTip>
            <span style={{ color: d.drifting ? "#E8C547" : "#8A9BAC" }}>{d.val}</span>
            {d.drifting && <span aria-label="drifting" style={{ marginLeft: 4, color: "#E8C547" }}>↓</span>}
          </div>
        ))}
      </div>
      <div style={{ fontSize: 10, color: "#3A4D5C" }}>
        Row above: each term&apos;s 52-week median cover as a share of its 5-year median (D-0110). The z-scores cannot see a slow decline; this can.
      </div>
    </div>
  );
}

export function AuctionsTab({ today, initialView }) {
  const now = today ?? new Date();
  // view: "latest", a charted term label ("26W"), or "signals" (D-0108).
  // `initialView` comes from the address: #/auctions/signals (D-0109).
  const [view, setView] = useState(initialView === "signals" ? "signals" : "latest");
  const [days, setDays] = useState(365);
  const term = CHARTED_TERMS.includes(view) ? view : null;
  const signals = view === "signals";

  const summary = useApiResource("/auctions/summary");
  const list = useApiResource(term ? `/auctions?term=${term}` : null, { enabled: Boolean(term) });
  const board = useApiResource(signals ? `/auctions/signals?days=${days}` : null, { enabled: signals });

  if (summary.loading) {
    return <div style={{ ...MONO, display: "flex", alignItems: "center", justifyContent: "center", height: 300, fontSize: 13, color: "#3A4D5C" }}>loading auctions...</div>;
  }
  if (summary.error || !summary.data) {
    return <LoadFailure what="Treasury auctions" error={summary.error}
      detail="If the table is empty, the Treasury_Auctions job has not run yet (ADMIN)." />;
  }

  const dataAsOf = summary.data.data_as_of;
  const termRows = list.data?.auctions ?? [];
  const rows = signals ? (board.data?.signals ?? [])
    : term ? termRows.slice(0, TABLE_LIMIT) : summary.data.terms;
  const stale = isStale(dataAsOf, now);
  const alerts = rows.filter((r) => r.demand_signal === "alert").length;
  const watches = rows.filter((r) => r.demand_signal === "watch").length;
  const loading = (term && list.loading) || (signals && board.loading);
  const windowLabel = WINDOWS.find(([, d]) => d === days)?.[0];

  const heading = signals
    ? `WEAK-DEMAND SIGNALS · ${windowLabel === "Since 2008" ? "SINCE 2008" : `LAST ${windowLabel}`} · ALERTS FIRST, WEAKEST FIRST`
    : term ? `${term} AUCTIONS · MOST RECENT ${Math.min(TABLE_LIMIT, termRows.length)}` : "LATEST AUCTION PER TERM";

  return (
    <div>
      <DataConfidence sourceKeys={["treasury_auctions"]} />
      <RegimePanel />

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
        <TermButton label="Latest" active={view === "latest"} onClick={() => setView("latest")} />
        <TermButton label="Signals" active={signals} onClick={() => setView("signals")} />
        <span style={{ width: 8 }} />
        {CHARTED_TERMS.map((t) => (
          <TermButton key={t} label={t} active={view === t} onClick={() => setView(t)} />
        ))}
      </div>

      {signals && (
        <div style={{ display: "flex", gap: 6, marginBottom: 12 }}>
          {WINDOWS.map(([label, d]) => (
            <TermButton key={label} label={label} active={days === d} onClick={() => setDays(d)} />
          ))}
        </div>
      )}
      {signals && board.error && <LoadFailure what="auction signals" error={board.error} />}
      {signals && board.data && <SignalTally byTerm={board.data.by_term} />}

      {term && list.error && <LoadFailure what={`${term} auctions`} error={list.error} />}
      {term && !list.loading && !list.error && <AuctionChart term={term} rows={termRows} />}

      <div style={{ background: "#0A1520", border: "1px solid #1A2530", borderRadius: 2, padding: "16px 0" }}>
        <div style={{ ...MONO, padding: "0 16px 12px", fontSize: 12, color: "#8A9BAC", letterSpacing: "0.1em" }}>
          {heading}
          <span data-testid="signal-count" style={{ marginLeft: 10, color: alerts ? "#FF4444" : watches ? "#E8C547" : "#3A4D5C" }}>
            {alerts} alert{alerts === 1 ? "" : "s"} · {watches} watch{watches === 1 ? "" : "es"}
          </span>
          <span style={{ marginLeft: 10, fontSize: 10, color: "#3A4D5C" }}>
            B2C excludes SOMA · z against the previous {summary.data.window_n} auctions of the same term (at least {summary.data.min_observations}) · hover a row for bidders
          </span>
        </div>
        {loading
          ? <div style={{ ...MONO, padding: 16, fontSize: 12, color: "#3A4D5C" }}>loading...</div>
          : signals && rows.length === 0
            ? <div style={{ ...MONO, padding: 16, fontSize: 12, color: "#5A6878" }}>No auction was flagged in this window.</div>
            : <AuctionTable key={view} rows={rows} withWeakness={signals} initialSort={signals ? { key: null } : undefined} />}
      </div>

      <DataAsOf asOf={dataAsOf} label="Latest auction" source="US Treasury, Fiscal Data auctions_query" />
    </div>
  );
}
