import { TBILLS_EXPLAINER } from "../lib/tbillsExplainer";

const CARD = {
  background: "#0A1520",
  border: "1px solid #1A2530",
  borderLeft: "3px solid #C8A96E",
  borderRadius: 2,
  padding: "16px 20px",
};

const HEADER = {
  fontFamily: "monospace",
  fontSize: 10,
  color: "#3A4D5C",
  letterSpacing: "0.15em",
  textTransform: "uppercase",
  borderBottom: "1px solid #1A2530",
  paddingBottom: 6,
  marginBottom: 16,
};

const BODY = {
  fontFamily: "monospace",
  fontSize: 12,
  color: "#8A9BAC",
  lineHeight: 1.8,
  margin: "0 0 8px",
};

/**
 * D-0092. Plain-language T-bills explainer for ABOUT.
 * Imports only the static copy module — no hooks, no api, no fetch.
 */
export function TBillsExplainer() {
  const { title, sections, myth, cheatSheet } = TBILLS_EXPLAINER;

  return (
    <section id="t-bills" aria-labelledby="tbills-heading" style={{ marginBottom: 32, maxWidth: 800 }}>
      <div id="tbills-heading" style={HEADER}>{title}</div>

      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        {sections.map((s) => (
          <div key={s.id} style={CARD}>
            <div style={{ fontFamily: "monospace", fontSize: 13, color: "#E8E0D0", fontWeight: 600, marginBottom: 8 }}>
              {s.heading}
            </div>
            {s.paragraphs.map((p, i) => (
              <p key={i} style={BODY}>{p}</p>
            ))}
          </div>
        ))}

        {/* Myth card — always expanded, never inside <details>. Amber left border. */}
        <div style={{ ...CARD, borderLeft: "3px solid #E8C547" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
            <span style={{
              fontFamily: "monospace", fontSize: 10, color: "#E8C547",
              background: "#E8C54718", border: "1px solid #E8C54744",
              borderRadius: 2, padding: "1px 6px",
            }}>{myth.chip}</span>
            <span style={{ fontFamily: "monospace", fontSize: 13, color: "#E8E0D0", fontWeight: 600 }}>
              {myth.heading}
            </span>
          </div>
          {myth.paragraphs.map((p, i) => {
            const isMyth = i === 0;
            const isFact = i === 1;
            return (
              <p
                key={i}
                style={{
                  ...BODY,
                  color: isFact ? "#E8E0D0" : BODY.color,
                }}
              >
                {(isMyth || isFact) && (
                  <span style={{
                    fontFamily: "monospace", fontSize: 10, color: isMyth ? "#E8C547" : "#E8E0D0",
                    background: isMyth ? "#E8C54718" : "#E8E0D018",
                    border: `1px solid ${isMyth ? "#E8C54744" : "#E8E0D044"}`,
                    borderRadius: 2, padding: "1px 6px", marginRight: 8,
                  }}>{isMyth ? "MYTH" : "FACT"}</span>
                )}
                {p}
              </p>
            );
          })}
        </div>

        <details style={{ ...CARD, borderLeft: "3px solid #1A2530" }}>
          <summary style={{
            cursor: "pointer", fontFamily: "monospace", fontSize: 11,
            color: "#8A9BAC", listStyle: "revert",
          }}>{cheatSheet.summary}</summary>
          <table style={{
            width: "100%", marginTop: 12, borderCollapse: "collapse",
            fontFamily: "monospace", fontSize: 11, color: "#8A9BAC",
          }}>
            <thead>
              <tr>
                {cheatSheet.headers.map((h) => (
                  <th key={h} style={{
                    textAlign: "left", padding: "4px 8px", color: "#5A6878",
                    borderBottom: "1px solid #1A2530", fontWeight: 600,
                  }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {cheatSheet.rows.map((row, i) => (
                <tr key={i}>
                  {row.map((cell, j) => (
                    <td key={j} style={{ padding: "4px 8px", borderBottom: "1px solid #1A2530" }}>{cell}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          <div style={{ fontFamily: "monospace", fontSize: 11, color: "#5A6878", marginTop: 10, lineHeight: 1.6 }}>
            {cheatSheet.note}
          </div>
        </details>
      </div>
    </section>
  );
}
