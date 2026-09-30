import { useApiResource } from "../hooks/useApiResource";
import { useAsyncAction } from "../hooks/useAsyncAction";
import { ColHeader } from "../components/ColHeader";

/**
 * How long to wait after a pipeline returns before re-reading its log row.
 *
 * A-0011: this was a bare `setTimeout(loadLogs, 1000)` and the reason is not
 * recorded anywhere. Kept at its original value rather than removed, because
 * a pipeline whose log row is written after the response would silently show
 * the PREVIOUS run, and nothing here proves it is not.
 */
const LOG_SETTLE_MS = 1000;

export function AdminTab() {
  const logsResource = useApiResource(`/pipeline-logs?limit=20`);
  const statsResource = useApiResource(`/stats`);
  const { running, results, run } = useAsyncAction();

  const logs = Array.isArray(logsResource.data) ? logsResource.data : [];
  const stats = statsResource.data;

  const refresh = () => {
    logsResource.reload();
    statsResource.reload();
  };

  const runPipeline = async (name, endpoint, method = "POST") => {
    await run(name, endpoint, { method });
    setTimeout(refresh, LOG_SETTLE_MS);
  };

  const PIPELINES = [
    {
      group: "Automatic (runs on schedule)",
      items: [
        { name: "FRED Data", endpoint: "/fetch/fred", method: "POST", desc: "Fetch 24 FRED metrics (yields, oil, dollar, CPI, M2, sovereign yields). Runs daily at 2am.", schedule: "Daily 2:00am UTC" },
        { name: "TIC Holdings", endpoint: "/fetch/treasury-holdings", method: "POST", desc: "Fetch Treasury holdings from ticdata.treasury.gov. 45 countries, monthly.", schedule: "15th of month, 3:00am UTC" },
        { name: "Stress Score", endpoint: "/stress-score", method: "GET", desc: "Recalculate 4-factor macro stress index (yield curve, concentration, volatility, gold accumulation).", schedule: "Daily 4:30am UTC" },
      ]
    },
    {
      group: "Manual (CSV import)",
      items: [
        { name: "Gold Reserves", endpoint: "/fetch/gold-reserves", method: "POST", desc: "Import WGC gold reserves CSV from data/gold_reserves.csv. Re-download quarterly from gold.org.", schedule: "Manual — re-download CSV quarterly" },
      ]
    },
  ];

  return (
    <div>
      {/* Stats bar */}
      {stats && (
        <div style={{ display: "flex", gap: 12, marginBottom: 24, flexWrap: "wrap" }}>
          {[
            { label: "Total Records", val: stats.timeseries_records?.toLocaleString() },
            { label: "Metrics Tracked", val: stats.metrics },
            { label: "Countries", val: stats.countries },
            { label: "Data From", val: stats.data_earliest ? new Date(stats.data_earliest).getFullYear() : "—" },
            { label: "Latest Data", val: stats.data_latest ? new Date(stats.data_latest).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }) : "—" },
          ].map(s => (
            <div key={s.label} style={{ background: "#0F1923", border: "1px solid #1A2530", borderRadius: 2, padding: "12px 18px", flex: "1 1 140px" }}>
              <div style={{ fontFamily: "monospace", fontSize: 10, color: "#5A6878", textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 4 }}>{s.label}</div>
              <div style={{ fontFamily: "monospace", fontSize: 18, fontWeight: 700, color: "#E8E0D0" }}>{s.val}</div>
            </div>
          ))}
        </div>
      )}

      {/* Pipeline triggers */}
      {PIPELINES.map(group => (
        <div key={group.group} style={{ marginBottom: 28 }}>
          <div style={{ fontFamily: "monospace", fontSize: 10, color: "#3A4D5C", letterSpacing: "0.15em", textTransform: "uppercase", marginBottom: 12, borderBottom: "1px solid #1A2530", paddingBottom: 6 }}>{group.group}</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {group.items.map(p => {
              const res = results[p.name];
              const busy = running[p.name];
              return (
                <div key={p.name} style={{ background: "#0A1520", border: "1px solid #1A2530", borderRadius: 2, padding: "16px 20px" }}>
                  <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 16 }}>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontFamily: "monospace", fontSize: 13, color: "#E8E0D0", fontWeight: 600, marginBottom: 4 }}>{p.name}</div>
                      <div style={{ fontFamily: "monospace", fontSize: 11, color: "#5A6878", marginBottom: 4 }}>{p.desc}</div>
                      <div style={{ fontFamily: "monospace", fontSize: 10, color: "#3A4D5C" }}>⏱ {p.schedule}</div>
                    </div>
                    <button
                      onClick={() => runPipeline(p.name, p.endpoint, p.method ?? "POST")}
                      disabled={busy}
                      style={{
                        background: busy ? "#1A2530" : "#0F1923",
                        border: `1px solid ${busy ? "#3A4D5C" : "#C8A96E"}`,
                        color: busy ? "#3A4D5C" : "#C8A96E",
                        borderRadius: 2, padding: "8px 20px",
                        cursor: busy ? "not-allowed" : "pointer",
                        fontFamily: "monospace", fontSize: 12,
                        whiteSpace: "nowrap",
                      }}>
                      {busy ? "running..." : "▶ Run Now"}
                    </button>
                  </div>
                  {res && (
                    <div style={{ marginTop: 12, background: res.ok ? "#0D2010" : "#200D0D", border: `1px solid ${res.ok ? "#2A4A30" : "#4A2A2A"}`, borderRadius: 2, padding: "10px 14px" }}>
                      <div style={{ fontFamily: "monospace", fontSize: 11, color: res.ok ? "#5DB87A" : "#E07B5A", marginBottom: 4 }}>
                        {res.ok ? "✓ Success" : "✗ Failed"}
                      </div>
                      <div style={{ fontFamily: "monospace", fontSize: 11, color: "#5A6878" }}>
                        {res.ok
                          ? `Inserted: ${res.data.inserted ?? "—"} · Updated: ${res.data.updated ?? "—"} · Countries: ${res.data.countries_tracked ?? res.data.skipped !== undefined ? `${res.data.inserted + res.data.updated} records` : ""}`
                          : res.data.detail || JSON.stringify(res.data).slice(0, 120)
                        }
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      ))}

      {/* Pipeline logs */}
      <div style={{ background: "#0A1520", border: "1px solid #1A2530", borderRadius: 2, padding: "20px 0", marginTop: 8 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "0 20px 16px" }}>
          <div style={{ fontFamily: "monospace", fontSize: 12, color: "#8A9BAC", letterSpacing: "0.1em" }}>PIPELINE LOG</div>
          <button onClick={refresh} style={{ background: "transparent", border: "1px solid #1E2D3D", color: "#3A4D5C", borderRadius: 2, padding: "4px 10px", cursor: "pointer", fontFamily: "monospace", fontSize: 11 }}>↻ refresh</button>
        </div>
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr>
                <ColHeader label="Pipeline" tip="Name of the data ingestion pipeline. FRED = Federal Reserve Economic Data (daily); TIC_Holdings = US Treasury foreign holdings (monthly, ~15th); Gold_Reserves_IMF = IMF IRFCL central bank gold (monthly, 25th); Gold_Reserves = World Gold Council backfill for non-filers; Stress_Score = composite index recalculation." align="left" style={{ padding: "6px 16px" }} />
                <ColHeader label="Status" tip="Execution result: success = all records processed without errors; partial = some records processed, some skipped or errored; failed = pipeline did not complete. Check the Error column for failure details." align="left" style={{ padding: "6px 16px" }} />
                <ColHeader label="Inserted" tip="Number of new time-series records added to the database in this run. High counts on first run; near-zero on subsequent runs indicates data is current and no new points were available." align="left" style={{ padding: "6px 16px" }} />
                <ColHeader label="Updated" tip="Number of existing records updated (e.g. revised values from data providers). FRED occasionally revises historical data; TIC and gold data are generally not revised after publication." align="left" style={{ padding: "6px 16px" }} />
                <ColHeader label="Completed" tip="UTC timestamp when the pipeline finished (success or failure). Use this to verify that automated runs are executing on schedule — FRED should run daily ~2am, TIC on the 15th of each month." align="left" style={{ padding: "6px 16px" }} />
                <ColHeader label="Error" tip="Error message if the pipeline failed or partially failed. Common errors: API rate limits (FRED), network timeouts (Fly.io cold starts), missing data (TIC not yet published for the month)." align="left" style={{ padding: "6px 16px" }} />
              </tr>
            </thead>
            <tbody>
              {logs.map((log, i) => (
                <tr key={i} style={{ borderBottom: "1px solid #080E14" }}>
                  <td style={{ padding: "8px 16px", fontFamily: "monospace", fontSize: 12, color: "#E8E0D0" }}>{log.pipeline_name}</td>
                  <td style={{ padding: "8px 16px", fontFamily: "monospace", fontSize: 12, color: log.status === "success" ? "#5DB87A" : log.status === "partial" ? "#E8C547" : "#E07B5A" }}>{log.status}</td>
                  <td style={{ padding: "8px 16px", fontFamily: "monospace", fontSize: 12, color: "#8A9BAC" }}>{log.records_inserted?.toLocaleString()}</td>
                  <td style={{ padding: "8px 16px", fontFamily: "monospace", fontSize: 12, color: "#8A9BAC" }}>{log.records_updated?.toLocaleString()}</td>
                  <td style={{ padding: "8px 16px", fontFamily: "monospace", fontSize: 12, color: "#5A6878", whiteSpace: "nowrap" }}>
                    {log.completed_at ? new Date(log.completed_at).toLocaleString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "—"}
                  </td>
                  <td style={{ padding: "8px 16px", fontFamily: "monospace", fontSize: 11, color: "#E07B5A", maxWidth: 300, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{log.error_message || ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
