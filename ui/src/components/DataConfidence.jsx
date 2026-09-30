import { useState } from "react";

import { useApiResource } from "../hooks/useApiResource";
import { InfoTip } from "./InfoTip";
import { worstStatus } from "../lib/freshness";

/**
 * Can the reader trust what this tab is showing?
 *
 * `D-0074`. `pipelines/freshness_watchdog.py` has always known the answer —
 * per source, with a tolerance tuned to that source's own release cadence and
 * a note explaining it — and `GET /api/freshness` has always served it. **No
 * surface consumed it.** A check nobody can see is the same as a check nobody
 * must obey (`P9`): the machinery was right and the screen was silent.
 *
 * Each tab declares the sources it draws on and this says, in its own colour,
 * whether those are current. Not a generic "last updated" — a per-source
 * verdict against what that source is supposed to do.
 *
 * The tolerances live server-side on purpose. `F-0087`: there were three
 * different numbers for how stale TIC may be — 100 in the pipeline that
 * refuses the file, 55 in the watchdog, and 100 again in a constant I had
 * added to the frontend. The UI now asks rather than deciding.
 */

const STATUS = {
  ok: { color: "#5DB87A", label: "current" },
  stale: { color: "#E8C547", label: "stale" },
  critical: { color: "#FF4444", label: "not current" },
  anomaly: { color: "#E07B5A", label: "anomalous" },
  unknown: { color: "#5A6878", label: "unknown" },
};


export function DataConfidence({ sourceKeys = [], label = "Data confidence" }) {
  const { data } = useApiResource(`/freshness`);
  const [open, setOpen] = useState(false);

  const all = data?.sources ?? [];
  const mine = sourceKeys.length
    ? sourceKeys.map((k) => all.find((s) => s.key === k)).filter(Boolean)
    : all;

  if (!mine.length) return null;

  const worst = worstStatus(mine);
  const tone = STATUS[worst] ?? STATUS.unknown;
  const bad = mine.filter((s) => s.status !== "ok");

  return (
    <div style={{ background: "#0A1520", border: `1px solid ${tone.color}33`, borderLeft: `3px solid ${tone.color}`, borderRadius: 2, padding: "10px 14px", marginBottom: 16 }}>
      <div
        onClick={() => setOpen((v) => !v)}
        style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap", cursor: "pointer" }}>
        <span style={{ fontFamily: "monospace", fontSize: 10, color: "#5A6878", letterSpacing: "0.1em" }}>
          {label.toUpperCase()}
        </span>
        <span style={{ fontFamily: "monospace", fontSize: 11, color: tone.color, fontWeight: 700 }}>
          {bad.length === 0
            ? `all ${mine.length} sources current`
            : `${bad.length} of ${mine.length} ${bad.length === 1 ? "source is" : "sources are"} ${tone.label}`}
        </span>
        <span style={{ fontFamily: "monospace", fontSize: 10, color: "#3A4D5C" }}>
          {open ? "▾ hide" : "▸ detail"}
        </span>
      </div>

      {open && (
        <div style={{ marginTop: 10, display: "flex", flexDirection: "column", gap: 6 }}>
          {mine.map((s) => {
            const st = STATUS[s.status] ?? STATUS.unknown;
            return (
              <InfoTip
                key={s.key}
                as="div"
                title={s.label}
                tip={`${s.note ?? ""} Tolerance for this source is ${s.max_age_days} days, set from its own release cadence. Latest observation is dated ${s.latest_date ?? "none"} and covers a ${s.period ?? "day"} ending ${s.coverage_end ?? "—"}; the age is measured from that end, not from the label (D-0077).`}
                placement="below"
                align="left"
                style={{ display: "flex", alignItems: "baseline", gap: 8, cursor: "help" }}>
                <span style={{ width: 7, height: 7, borderRadius: "50%", background: st.color, flexShrink: 0 }} />
                <span style={{ fontFamily: "monospace", fontSize: 11, color: "#8A9BAC", minWidth: 190 }}>
                  {s.label}
                </span>
                {/* D-0077: the stored date labels the period; coverage_end is
                    when the period it describes actually ended, and it is what
                    the age is measured from. Showing the label beside an age
                    derived from the end is how a reader concludes the two
                    disagree (F-0087). */}
                <span style={{ fontFamily: "monospace", fontSize: 11, color: st.color }}>
                  {s.coverage_end ?? s.latest_date ?? "—"}
                </span>
                <span style={{ fontFamily: "monospace", fontSize: 10, color: "#5A6878" }}>
                  {s.age_days != null
                    ? `${s.age_days}d since period end, tolerance ${s.max_age_days}d`
                    : ""}
                </span>
                {/* A laggard is one metric inside an otherwise current
                    source. Reported because an "ok" source containing a
                    333-day-old series is the kind of thing an aggregate
                    hides. */}
                {s.laggard && (
                  <span style={{ fontFamily: "monospace", fontSize: 10, color: "#E8C547" }}>
                    · {s.laggard.code} is {s.laggard.age_days}d
                  </span>
                )}
              </InfoTip>
            );
          })}
        </div>
      )}
    </div>
  );
}
