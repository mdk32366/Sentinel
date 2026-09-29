import { useRef, useState } from "react";
import { createPortal } from "react-dom";

/**
 * A hover bubble anchored to whatever it wraps.
 *
 * `ColHeader` had this logic inline — measure the anchor, portal a fixed
 * bubble to `document.body` so no ancestor's `overflow` clips it. The stat
 * cards need the same thing, and a second copy is `F-0062` again.
 *
 * The portal is the load-bearing part. Both tables here scroll horizontally
 * and both grids clip, so a bubble rendered in place is cut off on exactly
 * the columns furthest from the middle.
 *
 * `placement` is "above" for table headers, which sit near the bottom of
 * their container, and "below" for the stat cards, which sit at the top of
 * the page where an upward bubble would leave the viewport.
 */
export function InfoTip({
  title, tip, footer, footerColor = "#5A6878",
  placement = "above", align = "left",
  as: Tag = "span", children, style, ...rest
}) {
  const [rect, setRect] = useState(null);
  const anchorRef = useRef(null);

  const show = () => { if (anchorRef.current) setRect(anchorRef.current.getBoundingClientRect()); };
  const hide = () => setRect(null);

  const bubbleStyle = rect ? {
    position: "fixed",
    ...(placement === "above"
      ? { bottom: window.innerHeight - rect.top + 6 }
      : { top: rect.bottom + 6 }),
    ...(align === "left"
      ? { left: Math.max(8, Math.min(rect.left, window.innerWidth - 340)) }
      : { right: Math.max(8, window.innerWidth - rect.right) }),
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
    <Tag
      ref={anchorRef}
      style={style}
      onMouseEnter={show}
      onMouseLeave={hide}
      onFocus={show}
      onBlur={hide}
      {...rest}
    >
      {children}
      {rect && tip && createPortal(
        <div style={bubbleStyle} role="tooltip">
          <div style={{ fontFamily: "monospace", fontSize: 10, color: "#C8A96E", fontWeight: 700, marginBottom: 5, letterSpacing: "0.12em", textTransform: "uppercase" }}>
            {title}
          </div>
          <div style={{ fontFamily: "monospace", fontSize: 11, color: "#8A9BAC", lineHeight: 1.65, textTransform: "none", letterSpacing: 0, fontWeight: 400, textAlign: "left" }}>
            {tip}
          </div>
          {footer && (
            <div style={{ fontFamily: "monospace", fontSize: 10, color: footerColor, lineHeight: 1.6, marginTop: 8, paddingTop: 7, borderTop: "1px solid #1A2530", textTransform: "none", letterSpacing: 0, fontWeight: 400, textAlign: "left" }}>
              {footer}
            </div>
          )}
        </div>,
        document.body,
      )}
    </Tag>
  );
}
