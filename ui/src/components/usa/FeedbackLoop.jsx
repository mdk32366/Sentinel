import { breakingPointRate, crisisRate } from "../../lib/fiscal";

const BREAK = breakingPointRate();
const CRISIS = crisisRate();

const STEPS = [
  { n: "1", t: "Foreign stress builds", d: "Countries need USD liquidity — sell Treasuries" },
  { n: "2", t: "Treasury prices fall", d: "Yields rise as supply exceeds demand" },
  { n: "3", t: "US borrowing costs rise", d: "$36T debt × higher yield = ballooning deficit" },
  { n: "4", t: "More Treasuries issued", d: "To fund the expanding deficit" },
  { n: "5", t: "Feedback tightens", d: "More supply → more yield pressure → back to step 2" },
];

/**
 * How foreign stress reaches the US.
 *
 * This is the editorial spine of the application: it names which tab shows
 * which step, so the monitoring has a stated purpose rather than being a
 * collection of charts.
 */
export function FeedbackLoop() {
  return (
    <div style={{ background: "#0A1520", border: "1px solid #1A2530", borderRadius: 2, padding: "20px 24px" }}>
      <div style={{ fontFamily: "monospace", fontSize: 10, color: "#3A4D5C", letterSpacing: "0.1em", marginBottom: 12 }}>THE FEEDBACK LOOP — HOW FOREIGN STRESS REACHES THE US</div>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center", marginBottom: 12 }}>
        {STEPS.map((step, i) => (
          <div key={step.n} style={{ display: "contents" }}>
            {i > 0 && <div style={{ fontFamily: "monospace", fontSize: 16, color: "#1E2D3D" }}>→</div>}
            <div style={{ background: "#0F1923", border: "1px solid #1A2530", borderRadius: 2, padding: "10px 12px", flex: "1 1 120px", marginBottom: 6 }}>
              <div style={{ fontFamily: "monospace", fontSize: 10, color: "#C8A96E", marginBottom: 3 }}>STEP {step.n}</div>
              <div style={{ fontFamily: "monospace", fontSize: 11, color: "#E8E0D0", fontWeight: 600, marginBottom: 2 }}>{step.t}</div>
              <div style={{ fontFamily: "monospace", fontSize: 10, color: "#5A6878" }}>{step.d}</div>
            </div>
          </div>
        ))}
      </div>
      <div style={{ fontFamily: "monospace", fontSize: 11, color: "#3A4D5C", borderTop: "1px solid #1A2530", paddingTop: 12 }}>
        Sentinel&apos;s stress signals across 34 countries are <span style={{ color: "#C8A96E" }}>Step 1</span> early indicators.
        The MARKETS tab yield data is <span style={{ color: "#C8A96E" }}>Step 2</span>.
        The breaking point calculator above shows where <span style={{ color: "#C8A96E" }}>Step 3</span> becomes irreversible.
        At {BREAK.toFixed(1)}% on the 10Y, the US crosses the emerging market danger threshold. At {CRISIS.toFixed(1)}%, it&apos;s Japan 2024.
      </div>
    </div>
  );
}
