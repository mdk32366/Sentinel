import { useState } from "react";
import { useApiResource } from "../hooks/useApiResource";
import { useAsyncAction } from "../hooks/useAsyncAction";
import { CDSCoverageBanner } from "../components/CDSCoverageBanner";
import { ColHeader } from "../components/ColHeader";

const FETCH_KEY = "cds";

export function CDSTab({ onCountrySelect }) {
  const rows = useApiResource(`/cds/all`);
  const coverageResource = useApiResource(`/cds/coverage`);
  const { running, results, run } = useAsyncAction();
  const [sort, setSort] = useState("cds5y");

  // Both reads fail soft into the empty state, which is what this tab showed
  // before: CDS is the one source with no automatic pipeline, so "nothing
  // here yet" is the ordinary condition and the banner already says how to
  // fix it. That is a deliberate exception to F-0063, not an oversight.
  const data = Array.isArray(rows.data) ? rows.data : [];
  const coverage = coverageResource.data;
  const loading = rows.loading || coverageResource.loading;
  const fetching = Boolean(running[FETCH_KEY]);
  const fetchResult = results[FETCH_KEY];

  const runFetch = async () => {
    await run(FETCH_KEY, `/cds/fetch`);
    rows.reload();
    coverageResource.reload();
  };

  if (loading) {
    return <div style={{ padding: 40, fontFamily: "monospace", color: "#3A4D5C" }}>Loading CDS data...</div>;
  }

  const emptyCoverage = !coverage || coverage.with_data === 0;
  const emptyTable = data.length === 0;

  if (emptyCoverage && emptyTable) {
    return (
      <div>
        <div style={{ marginBottom: 20 }}>
          <div style={{ fontFamily: "monospace", fontSize: 22, color: "#C8A96E", fontWeight: 700 }}>
            Sovereign CDS Monitor
          </div>
          <div style={{ fontFamily: "monospace", fontSize: 12, color: "#5A6878", marginTop: 4 }}>
            5Y conventional/par CDS spreads (not the ISDA coupon) • 10Y only when same source and as-of as 5Y
          </div>
        </div>
        <CDSCoverageBanner coverage={coverage} fetching={fetching} fetchResult={fetchResult} onFetch={runFetch} />
      </div>
    );
  }

  // Sorting
  const sortedData = [...data].sort((a, b) => {
    if (sort === "cds5y") return (b.cds_5y || 0) - (a.cds_5y || 0);
    if (sort === "term") return (b.cds_term_spread || 0) - (a.cds_term_spread || 0);
    if (sort === "country") return a.country_name.localeCompare(b.country_name);
    return 0;
  });

  return (
    <div>
      <div style={{ marginBottom: 20 }}>
        <div style={{ fontFamily: "monospace", fontSize: 22, color: "#C8A96E", fontWeight: 700 }}>
          Sovereign CDS Monitor
        </div>
        <div style={{ fontFamily: "monospace", fontSize: 12, color: "#5A6878", marginTop: 4 }}>
          5Y conventional/par CDS spreads (not the ISDA coupon) • 10Y only when same source and as-of as 5Y
        </div>
      </div>

      {emptyCoverage && (
        <CDSCoverageBanner coverage={coverage} fetching={fetching} fetchResult={fetchResult} onFetch={runFetch} />
      )}

      {/* Summary Cards */}
      <div style={{ display: "flex", gap: 12, marginBottom: 24, flexWrap: "wrap" }}>
        {[
          { label: "Countries with CDS", val: data.length },
          { label: "Highest 5Y CDS", val: `${Math.max(...data.map(d => d.cds_5y || 0))} bps` },
          { label: "Inverted Curves", val: data.filter(d => (d.cds_term_spread || 0) < 0).length },
          { label: "Very High (>300 bps)", val: data.filter(d => (d.cds_5y || 0) > 300).length },
        ].map((s, i) => (
          <div key={i} style={{ background: "#0F1923", border: "1px solid #1A2530", borderTop: "2px solid #C8A96E", borderRadius: 2, padding: "14px 20px", flex: "1 1 150px" }}>
            <div style={{ fontFamily: "monospace", fontSize: 10, color: "#5A6878", textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 4 }}>{s.label}</div>
            <div style={{ fontFamily: "monospace", fontSize: 22, fontWeight: 700, color: "#E8E0D0" }}>{s.val}</div>
          </div>
        ))}
      </div>

      {/* CDS Table */}
      <div style={{ background: "#0A1520", border: "1px solid #1A2530", borderRadius: 2, padding: "20px 0" }}>
        <div style={{ padding: "0 20px 16px", fontFamily: "monospace", fontSize: 12, color: "#8A9BAC", letterSpacing: "0.1em" }}>
          CDS LEADERBOARD — Click row to view country details
        </div>

        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr>
                <ColHeader label="Country" align="left" />
                <ColHeader label="5Y CDS" tip="5-year sovereign CDS spread (basis points)" sortKey="cds5y" activeSort={sort} onSort={setSort} align="right" />
                <ColHeader label="10Y CDS" tip="10-year sovereign CDS spread (basis points)" align="right" />
                <ColHeader 
  label="Term Structure" 
  tip="10Y CDS − 5Y CDS. Negative = inverted curve (often a sign of acute sovereign stress)" 
  sortKey="term" 
  activeSort={sort} 
  onSort={setSort} 
  align="right" 
/>
                <ColHeader label="Signal" align="left" />
              </tr>
            </thead>
            <tbody>
              {sortedData.map((c, i) => {
                const isHigh = (c.cds_5y || 0) > 300;
                const isInverted = (c.cds_term_spread || 0) < 0;
                return (
                  <tr 
                    key={i} 
                    onClick={() => onCountrySelect && onCountrySelect(c.country_iso)}
                    style={{ 
                      borderBottom: "1px solid #0F1923", 
                      cursor: onCountrySelect ? "pointer" : "default" 
                    }}
                    onMouseEnter={e => e.currentTarget.style.background = "#0D1820"}
                    onMouseLeave={e => e.currentTarget.style.background = "transparent"}
                  >
                    <td style={{ padding: "10px 16px", fontFamily: "monospace", fontSize: 13, color: "#E8E0D0" }}>
                      {c.country_name} <span style={{ color: "#3A4D5C", fontSize: 10 }}>{c.country_iso}</span>
                    </td>
                    <td style={{ padding: "10px 16px", fontFamily: "monospace", fontSize: 13, textAlign: "right", color: isHigh ? "#E07B5A" : "#8A9BAC", fontWeight: isHigh ? 600 : 400 }}>
                      {c.cds_5y ? `${c.cds_5y} bps` : "—"}
                    </td>
                    <td style={{ padding: "10px 16px", fontFamily: "monospace", fontSize: 13, textAlign: "right", color: "#8A9BAC" }}>
                      {c.cds_10y ? `${c.cds_10y} bps` : "—"}
                    </td>
                    <td style={{ padding: "10px 16px", fontFamily: "monospace", fontSize: 13, textAlign: "right", color: isInverted ? "#FF4444" : "#8A9BAC", fontWeight: isInverted ? 600 : 400 }}>
                      {c.cds_term_spread != null ? `${c.cds_term_spread > 0 ? "+" : ""}${c.cds_term_spread} bps` : "—"}
                    </td>
                    <td style={{ padding: "10px 16px" }}>
                      {isInverted && (
                        <span style={{ fontFamily: "monospace", fontSize: 10, color: "#FF4444", background: "#FF444418", border: "1px solid #FF444444", borderRadius: 2, padding: "1px 6px" }}>
                          INVERTED
                        </span>
                      )}
                      {isHigh && !isInverted && (
                        <span style={{ fontFamily: "monospace", fontSize: 10, color: "#E07B5A", background: "#E07B5A18", border: "1px solid #E07B5A44", borderRadius: 2, padding: "1px 6px" }}>
                          HIGH
                        </span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      <div style={{ marginTop: 12, fontFamily: "monospace", fontSize: 11, color: "#1E2D3D" }}>
        Data source: {data.find(d => d.source)?.source || "World Government Bonds"} (indicative USD mid) · 5Y is the conventional/par spread, not the coupon
        {data.find(d => d.as_of)?.as_of ? ` · as-of ${data.find(d => d.as_of).as_of}` : ""}
      </div>
    </div>
  );
}
