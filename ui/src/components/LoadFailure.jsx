/**
 * What a tab shows when its resource did not load.
 *
 * `F-0063`: before this existed, each tab invented its own answer, and two of
 * them had none — a failed `/holdings` rendered an empty table that read as
 * "no country holds Treasuries". This keeps a failure looking like a failure:
 * failure-red, the endpoint that failed, and the status when there is one.
 *
 * `detail` carries the tab's own sentence about what is missing, since "run
 * POST /api/fetch/gold-reserves" is useful and "500" on its own is not.
 */
export function LoadFailure({ what, error, detail }) {
  const status = error?.status ? ` — ${error.message}` : error ? ` — ${error.message}` : "";
  return (
    <div style={{ fontFamily: "monospace", color: "#E07B5A", padding: 24, lineHeight: 1.6 }}>
      <div style={{ fontSize: 13 }}>Could not load {what}{status}</div>
      {detail && <div style={{ fontSize: 12, color: "#8A6A5A", marginTop: 6 }}>{detail}</div>}
    </div>
  );
}
