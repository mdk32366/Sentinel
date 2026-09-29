export function CDSCoverageBanner({ coverage, fetching, fetchResult, onFetch }) {
  const pipe = coverage?.last_pipeline;
  const started = pipe?.started_at ? new Date(pipe.started_at).toLocaleString("en-US", {
    month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", timeZone: "UTC",
  }) + " UTC" : "never";
  return (
    <div style={{
      background: "#1A1010",
      border: "1px solid #E07B5A",
      borderRadius: 2,
      padding: "16px 20px",
      marginBottom: 20,
    }}>
      <div style={{ fontFamily: "monospace", fontSize: 13, color: "#E07B5A", fontWeight: 700, letterSpacing: "0.06em", marginBottom: 8 }}>
        CDS COVERAGE EMPTY — pipeline has no latest points
      </div>
      <div style={{ fontFamily: "monospace", fontSize: 12, color: "#C8A96E", marginBottom: 6 }}>
        configured {coverage?.configured ?? "—"} · with data {coverage?.with_data ?? 0} · without data {coverage?.without_data ?? "—"}
        {Array.isArray(coverage?.missing_codes) ? ` · ${coverage.missing_codes.length} codes missing latest points` : ""}
      </div>
      <div style={{ fontFamily: "monospace", fontSize: 12, color: "#8A9BAC", marginBottom: 10 }}>
        Last CDS_MultiTenor: {pipe ? `${pipe.status} · started ${started} · inserted ${pipe.inserted ?? 0} · updated ${pipe.updated ?? 0}` : "no pipeline run recorded"}
        {pipe?.error_message ? (
          <div style={{ color: "#E07B5A", marginTop: 6, maxHeight: 72, overflow: "hidden" }}>{pipe.error_message}</div>
        ) : null}
      </div>
      <button
        onClick={onFetch}
        disabled={fetching}
        style={{
          background: fetching ? "#1A2530" : "#0F1923",
          border: `1px solid ${fetching ? "#3A4D5C" : "#C8A96E"}`,
          color: fetching ? "#3A4D5C" : "#C8A96E",
          borderRadius: 2, padding: "8px 16px",
          cursor: fetching ? "not-allowed" : "pointer",
          fontFamily: "monospace", fontSize: 12,
        }}
      >
        {fetching ? "fetching CDS…" : "▶ Run CDS fetch"}
      </button>
      {fetchResult && (
        <div style={{ marginTop: 10, fontFamily: "monospace", fontSize: 11, color: fetchResult.ok ? "#5DB87A" : "#E07B5A" }}>
          {fetchResult.ok
            ? `Fetch ${fetchResult.data?.status}: ok ${fetchResult.data?.ok}/${fetchResult.data?.attempted} · inserted ${fetchResult.data?.inserted} · updated ${fetchResult.data?.updated}`
            : (fetchResult.data?.detail || fetchResult.data?.error || "Fetch failed")}
        </div>
      )}
    </div>
  );
}
