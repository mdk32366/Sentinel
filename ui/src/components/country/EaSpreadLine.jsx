import { InfoTip } from "../InfoTip";

const mono = { fontFamily: "monospace", fontSize: 12 };

function format(bp) {
  if (bp == null) return "—";
  if (bp > 0) return `+${bp} bp`;
  if (bp < 0) return `\u2212${Math.abs(bp)} bp`;
  return "0 bp";
}

/**
 * Sentinel D-0117: one line under the headline 10Y on a euro-area member card,
 * "Spread to EA AAA 10Y: +NNN bp (as of …)", plus the "EA benchmark →" link,
 * which shows even when the readout is a dash. `readout` is
 * `eaSpreadReadout(...)`; null (a non-member) renders nothing.
 */
export function EaSpreadLine({ readout }) {
  if (!readout) return null;
  const { bp, monthly, asOf, tip, href } = readout;
  return (
    <div data-testid="ea-spread" style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap", margin: "0 0 12px", ...mono }}>
      <InfoTip as="div" title="Spread to EA AAA 10Y" tip={tip} placement="below" align="left" tabIndex={0} style={{ cursor: "help", outline: "none", color: "#8A9AAA" }}>
        Spread to EA AAA 10Y:{" "}
        <span data-testid="ea-spread-value" style={{ fontWeight: 700, color: bp == null ? "#3A4D5C" : bp < 0 ? "#E07B5A" : "#7EB8C9" }}>{format(bp)}</span>
        {asOf ? ` (as of ${asOf})` : ""}
      </InfoTip>
      {monthly && (
        <span data-testid="ea-spread-badge" style={{ fontSize: 9, letterSpacing: 1, color: "#C8A96E", border: "1px solid #3A3020", padding: "1px 4px", borderRadius: 2 }}>MONTHLY</span>
      )}
      <a data-testid="ea-spread-link" href={href} style={{ color: "#7EB8C9", textDecoration: "none" }}>EA benchmark →</a>
    </div>
  );
}
