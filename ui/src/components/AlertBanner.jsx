export function AlertBanner({ message, color = "#E07B5A" }) {
  return (
    <div style={{ background: `${color}15`, border: `1px solid ${color}44`, borderLeft: `3px solid ${color}`, borderRadius: 2, padding: "10px 16px", marginBottom: 12, fontFamily: "monospace", fontSize: 12, color }}>
      ⚠ {message}
    </div>
  );
}
