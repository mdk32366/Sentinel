import { Area, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

/**
 * Recomputed bid-to-cover over time for one term, with the trailing-window
 * mean ± 1 sd as a band (ORDER auction-demand §7).
 *
 * The band is the server's window (`b2c_window_mean`, `b2c_window_sd`, D-0099):
 * the same 26 auctions the z-score uses, so the band and the z-score cannot
 * disagree. Where the window is too short there is no band, not a band drawn
 * on three points.
 */
export function AuctionChart({ term, rows }) {
  const data = [...rows]
    .sort((a, b) => (a.auction_date < b.auction_date ? -1 : 1))
    .map((r) => ({
      date: r.auction_date,
      b2c: r.b2c_recomputed,
      mean: r.b2c_window_mean,
      band: r.b2c_window_mean != null && r.b2c_window_sd != null
        ? [r.b2c_window_mean - r.b2c_window_sd, r.b2c_window_mean + r.b2c_window_sd]
        : null,
    }));

  return (
    <div data-testid="auction-chart" data-term={term} style={{
      background: "#0A1520", border: "1px solid #1A2530", borderRadius: 2, padding: "20px 24px", marginBottom: 16,
    }}>
      <div style={{ fontFamily: "monospace", fontSize: 11, color: "#5A6878", marginBottom: 12, letterSpacing: "0.1em" }}>
        BID-TO-COVER OVER TIME · {term}
        <span style={{ marginLeft: 10, color: "#3A4D5C" }}>band: trailing-window mean ± 1 sd · SOMA excluded</span>
      </div>
      <ResponsiveContainer width="100%" height={260}>
        <ComposedChart data={data} margin={{ top: 4, right: 8, bottom: 4, left: 8 }}>
          <CartesianGrid strokeDasharray="2 6" stroke="#0F1923" vertical={false} />
          <XAxis dataKey="date" tick={{ fill: "#3A4D5C", fontFamily: "monospace", fontSize: 10 }} axisLine={{ stroke: "#1A2530" }} tickLine={false} minTickGap={60} />
          <YAxis domain={["auto", "auto"]} tick={{ fill: "#3A4D5C", fontFamily: "monospace", fontSize: 10 }} axisLine={false} tickLine={false} width={40} tickFormatter={(v) => v.toFixed(1)} />
          <Tooltip contentStyle={{ background: "#0A1520", border: "1px solid #1E2D3D", borderRadius: 2, fontFamily: "monospace", fontSize: 11 }} labelStyle={{ color: "#5A6878" }}
            formatter={(v, name) => (Array.isArray(v) ? [`${v[0].toFixed(2)} – ${v[1].toFixed(2)}`, "window ±1 sd"] : [v?.toFixed(2), name])} />
          <Area dataKey="band" stroke="none" fill="#2A3D50" fillOpacity={0.5} isAnimationActive={false} connectNulls={false} name="window ±1 sd" />
          <Line dataKey="mean" stroke="#5A6878" strokeDasharray="4 4" strokeWidth={1} dot={false} isAnimationActive={false} name="window mean" />
          <Line dataKey="b2c" stroke="#C8A96E" strokeWidth={1.5} dot={false} isAnimationActive={false} name="bid-to-cover" />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
