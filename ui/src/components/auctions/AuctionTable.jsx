import { useState } from "react";

import {
  fmtBn, fmtPct, fmtRatio, fmtShare, fmtZ, reasonText, sortRows,
} from "../../lib/auctions";
import { InfoTip } from "../InfoTip";

/**
 * Latest-auctions table (ORDER auction-demand §7).
 *
 * - A missing value is a dash with its reason on hover, and sorts last in
 *   both directions (§3). It never renders as zero.
 * - `b2c_check = mismatch` carries a visible marker: nothing is hidden because
 *   the two bid-to-cover paths disagree (§2).
 * - z-scores are plain numbers in one colour. Highlight thresholds are an
 *   owner ruling not yet made, and an unruled threshold is not an alert
 *   (D-0102).
 * - Hovering a row shows the bidder breakdown and SOMA, labelled as excluded
 *   from bid-to-cover.
 *
 * Column labels are placeholders; panel copy is owner-ruled (§7).
 */

const NEUTRAL = "#8A9BAC";
const MONO = { fontFamily: "monospace" };

const COLUMNS = [
  { key: "term", label: "Term", align: "left",
    tip: "The auction's term family (D-0103): a bill's own term, or a note's or bond's original term, so a 10-year reopening counts as 10Y." },
  { key: "auction_date", label: "Auction date", align: "left",
    tip: "The day the auction was held and its results published." },
  { key: "b2c_recomputed", label: "B2C", fmt: fmtRatio,
    tip: "Bid-to-cover: dollars bid for every dollar sold. Recomputed from Treasury's totals with the Fed's SOMA rollover taken out of both sides, which is how Treasury defines its own figure (D-0098). Higher means more demand. ≠ marks a row where this differs from Treasury's reported figure by more than 0.01." },
  { key: "b2c_z", label: "Z (B2C)", fmt: fmtZ, reasonKey: "b2c_z_reason",
    tip: "How unusual this bid-to-cover is against the previous 26 auctions of the same term, in standard deviations, needing at least 8 (D-0099). Negative means weaker demand than usual. Not colour-coded until alert thresholds are ruled (D-0102)." },
  { key: "primary_dealer_share", label: "Dealer share", fmt: fmtShare,
    tip: "Share of competitive accepted bids taken by primary dealers (D-0097). Dealers are expected to bid at every auction, so a high share means less outside demand took the securities." },
  { key: "dealer_z", label: "Z (dealer)", fmt: fmtZ, reasonKey: "dealer_z_reason",
    tip: "How unusual the dealer share is against the same 26-auction window. Positive means dealers were left holding more than usual." },
  { key: "indirect_bidder_share", label: "Indirect share", fmt: fmtShare,
    tip: "Share taken by indirect bidders: investors bidding through a dealer or the New York Fed, including foreign central banks and international accounts. A rough read on foreign demand." },
  { key: "allocation_pct", label: "% at high", fmt: fmtPct,
    tip: "Of the bids placed at the auction's highest accepted rate, the percentage that were filled. Treasury's 'allotted at high' figure." },
];

function reasonFor(row, column) {
  const code = column.reasonKey ? row[column.reasonKey] : row.null_reasons?.[column.key];
  return reasonText(code);
}

function Cell({ row, column }) {
  const raw = row[column.key];
  const shown = column.fmt ? column.fmt(raw) : raw;
  const missing = shown == null;
  const mismatch = column.key === "b2c_recomputed" && row.b2c_check === "mismatch";

  return (
    <td
      data-testid={`cell-${column.key}`}
      title={missing ? reasonFor(row, column) : undefined}
      style={{
        ...MONO, padding: "7px 14px", fontSize: 12,
        textAlign: column.align ?? "right",
        color: missing ? "#3A4D5C" : column.key === "term" ? "#E8E0D0" : NEUTRAL,
      }}
    >
      {missing ? "—" : shown}
      {mismatch && (
        <span
          aria-label="bid-to-cover mismatch"
          title={`Recomputed ${fmtRatio(row.b2c_recomputed)} vs Treasury's reported ${fmtRatio(row.b2c_reported)}. Both are stored; neither is chosen.`}
          style={{ marginLeft: 6, color: "#E8C547", fontWeight: 700 }}
        >
          ≠
        </span>
      )}
    </td>
  );
}

function Breakdown({ row }) {
  const line = (label, value, note) => (
    <div style={{ display: "flex", justifyContent: "space-between", gap: 16 }}>
      <span style={{ color: "#5A6878" }}>{label}</span>
      <span>
        <span style={{ color: "#E8E0D0" }}>{value ?? "—"}</span>
        {note && <span style={{ color: "#5A6878", marginLeft: 6 }}>{note}</span>}
      </span>
    </div>
  );
  return (
    <div role="tooltip" style={{
      ...MONO, fontSize: 11, marginTop: 10, padding: "12px 16px", maxWidth: 420,
      background: "#0A1520", border: "1px solid #2A3D50", borderRadius: 2, display: "grid", gap: 4,
    }}>
      <div style={{ color: "#C8A96E", marginBottom: 4 }}>
        Bidder breakdown · {row.term ?? row.security_term} · {row.auction_date}
      </div>
      {line("Primary dealers", fmtShare(row.primary_dealer_share))}
      {line("Direct bidders", fmtShare(row.direct_bidder_share))}
      {line("Indirect bidders", fmtShare(row.indirect_bidder_share))}
      {line("Competitive accepted", fmtBn(row.comp_accepted))}
      {line("SOMA accepted", fmtBn(row.soma_accepted), "excluded from bid-to-cover")}
      {row.shares_check === "gap" && line("Bidder classes short by", fmtBn(row.bidder_gap))}
    </div>
  );
}

export function AuctionTable({ rows }) {
  const [sort, setSort] = useState({ key: "auction_date", dir: "desc" });
  const [hovered, setHovered] = useState(null);

  const sorted = sortRows(rows, sort.key, sort.dir);
  const toggle = (key) => setSort((s) => (
    s.key === key ? { key, dir: s.dir === "desc" ? "asc" : "desc" } : { key, dir: "desc" }
  ));

  return (
    <div>
      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr>
              {COLUMNS.map((c) => (
                <InfoTip as="th" key={c.key} title={c.label} tip={c.tip} placement="above" align={c.align === "left" ? "left" : "right"}
                  style={{ padding: "6px 14px", textAlign: c.align ?? "right", borderBottom: "1px solid #1A2530" }}>
                  <button type="button" onClick={() => toggle(c.key)} style={{
                    ...MONO, background: "transparent", border: "none", cursor: "pointer", padding: 0,
                    fontSize: 10, letterSpacing: "0.08em", textTransform: "uppercase",
                    color: sort.key === c.key ? "#C8A96E" : "#5A6878",
                  }}>
                    <span style={{ borderBottom: "1px dashed #2A3D50" }}>{c.label}</span>
                    {sort.key === c.key ? (sort.dir === "desc" ? " ▼" : " ▲") : ""}
                  </button>
                </InfoTip>
              ))}
            </tr>
          </thead>
          <tbody>
            {sorted.map((r) => (
              <tr
                key={`${r.cusip}-${r.auction_date}`}
                data-testid="auction-row"
                data-term={r.term ?? ""}
                data-date={r.auction_date}
                onMouseEnter={() => setHovered(r)}
                onMouseLeave={() => setHovered(null)}
                style={{ borderBottom: "1px solid #0F1923", background: hovered === r ? "#0D1820" : "transparent" }}
              >
                {COLUMNS.map((c) => <Cell key={c.key} row={r} column={c} />)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {hovered && <Breakdown row={hovered} />}
    </div>
  );
}
