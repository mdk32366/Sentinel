import { useApiResource } from "../hooks/useApiResource";
import { MANUAL_TRIGGERS, SCHEDULED_JOBS } from "../lib/adminActions";
import { useAsyncAction } from "../hooks/useAsyncAction";
import { ColHeader } from "../components/ColHeader";
import { InfoTip } from "../components/InfoTip";

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

  // F-0098. This list used to be four items held locally: it described TIC as
  // "45 countries" (Table 5 names twenty), filed Gold Reserves under "Manual
  // (CSV import)" with instructions to re-download from gold.org months after
  // D-0076 automated it, and omitted seven scheduled jobs and six triggers.
  // Moved to lib/adminActions.js so tests/test_admin_surface.py can assert from
  // the Python side that every POST route and every registered job id appears.
  const PIPELINES = [
    {
      group: `Scheduled (${SCHEDULED_JOBS.length} jobs, all automatic)`,
      items: SCHEDULED_JOBS.map((j) => ({
        name: j.name,
        desc: j.desc,
        schedule: `${j.schedule} · ${j.pipeline}`,
        // A scheduled job is run by name through its own trigger below rather
        // than from here, so these carry no button.
        endpoint: null,
      })),
    },
    {
      group: `Manual triggers (${MANUAL_TRIGGERS.length})`,
      items: MANUAL_TRIGGERS.map((t) => ({
        name: t.name,
        desc: t.desc,
        schedule: `${t.method} /api${t.endpoint}`,
        endpoint: t.endpoint,
        method: t.method,
      })),
    },
  ];

  return (
    <div>
      {/* Stats bar */}
      {stats && (
        <div style={{ display: "flex", gap: 12, marginBottom: 24, flexWrap: "wrap" }}>
          {[
            { label: "Total Records", val: stats.timeseries_records?.toLocaleString(),
              tip: "Rows in the timeseries table: every stored observation, across every metric and country (GET /api/stats). A count of data points, not of series. Treasury auction results live in their own table and are not counted here." },
            { label: "Metrics Tracked", val: stats.metrics,
              tip: "Rows in the metrics table: each distinct series code the pipelines have written, such as DGS10 or GOLD_RESERVES. A code registered once stays counted even if its source has since stopped." },
            { label: "Countries", val: stats.countries,
              tip: "Rows in the countries table: every country any pipeline has ever written a value for. This is not the number reporting now. TIC and IMF coverage differ, and each tab states its own." },
            { label: "Data From", val: stats.data_earliest ? new Date(stats.data_earliest).getFullYear() : "—",
              tip: "Year of the oldest date in the timeseries table, across all series. Most series start much later; this is the deepest history any one of them reaches." },
            { label: "Latest Data", val: stats.data_latest ? new Date(stats.data_latest).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }) : "—",
              tip: "Newest date in the timeseries table, across all series. One daily series is enough to make this current, so it does not mean every source is. The per-source verdict is the data-confidence strip on each tab (D-0074)." },
          ].map(s => (
            <div key={s.label} style={{ background: "#0F1923", border: "1px solid #1A2530", borderRadius: 2, padding: "12px 18px", flex: "1 1 140px" }}>
              <InfoTip title={s.label} tip={s.tip} placement="below" as="div" style={{ fontFamily: "monospace", fontSize: 10, color: "#5A6878", textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 4 }}>
                <span style={{ borderBottom: "1px dashed #2A3D50", paddingBottom: 1 }}>{s.label}</span>
              </InfoTip>
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
                    {p.endpoint && <button
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
                    </button>}
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
