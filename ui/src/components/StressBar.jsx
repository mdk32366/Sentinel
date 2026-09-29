import { scoreColor } from "../lib/format";

export function StressBar({ score, max = 100 }) {
  const w = Math.min(100, (score / max) * 100);
  const color = scoreColor(score);
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <div style={{ flex: 1, background: "#0F1923", borderRadius: 2, height: 6, overflow: "hidden" }}>
        <div style={{ width: `${w}%`, background: color, height: "100%", borderRadius: 2, transition: "width 0.3s" }} />
      </div>
      <span style={{ fontFamily: "monospace", fontSize: 11, color, minWidth: 32, textAlign: "right" }}>{score.toFixed(0)}</span>
    </div>
  );
}

// Tables clip position:absolute children — we portal the bubble to document.body
// and use position:fixed so getBoundingClientRect() coords work directly
// (no scroll offset math needed).
