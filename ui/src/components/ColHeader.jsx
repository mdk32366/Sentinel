import { useState, useRef } from "react";
import { createPortal } from "react-dom";

export function ColHeader({ label, tip, align = "right", sortKey, activeSort, onSort, style = {} }) {
  const [rect, setRect] = useState(null);
  const thRef = useRef(null);
  const isSorted = sortKey && activeSort === sortKey;

  const handleEnter = () => {
    if (thRef.current) setRect(thRef.current.getBoundingClientRect());
  };
  const handleLeave = () => setRect(null);

  // Bubble sits just above the <th>, flush with its left or right edge
  const bubbleStyle = rect ? {
    position: "fixed",
    bottom: window.innerHeight - rect.top + 6,   // 6px gap above the header row
    ...(align === "left"
      ? { left: rect.left }
      : { right: window.innerWidth - rect.right }),
    zIndex: 99999,
    background: "#0A1520",
    border: "1px solid #2A3D50",
    borderTop: "2px solid #C8A96E",
    borderRadius: 3,
    padding: "10px 14px",
    minWidth: 240,
    maxWidth: 320,
    boxShadow: "0 4px 24px rgba(0,0,0,0.8)",
    pointerEvents: "none",
  } : null;

  return (
    <th
      ref={thRef}
      style={{
        fontFamily: "monospace",
        fontSize: 10,
        letterSpacing: "0.1em",
        color: isSorted ? "#C8A96E" : "#3A4D5C",
        textTransform: "uppercase",
        padding: "8px 12px",
        textAlign: align,
        borderBottom: "1px solid #1A2530",
        whiteSpace: "nowrap",
        cursor: onSort ? "pointer" : "default",
        userSelect: "none",
        ...style,
      }}
      onClick={onSort ? () => onSort(sortKey) : undefined}
      onMouseEnter={handleEnter}
      onMouseLeave={handleLeave}
    >
      <span style={{ borderBottom: "1px dashed #2A3D50", paddingBottom: 1 }}>
        {label}
      </span>
      {isSorted && <span style={{ marginLeft: 4 }}>↓</span>}

      {rect && tip && createPortal(
        <div style={bubbleStyle}>
          <div style={{ fontFamily: "monospace", fontSize: 10, color: "#C8A96E", fontWeight: 700, marginBottom: 5, letterSpacing: "0.12em", textTransform: "uppercase" }}>
            {label}
          </div>
          <div style={{ fontFamily: "monospace", fontSize: 11, color: "#8A9BAC", lineHeight: 1.65, textTransform: "none", letterSpacing: 0, fontWeight: 400, textAlign: "left" }}>
            {tip}
          </div>
        </div>,
        document.body
      )}
    </th>
  );
}

// ── Country Detail (shared between HOLDINGS and COUNTRY tabs) ─────────────────


// Sovereign yield FRED codes
