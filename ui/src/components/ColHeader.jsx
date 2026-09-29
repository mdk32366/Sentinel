import { InfoTip } from "./InfoTip";

/**
 * A sortable table column header with an explanatory bubble.
 *
 * The bubble logic moved into `InfoTip` when the MARKETS stat cards needed
 * the same thing — measuring an anchor and portalling a fixed-position bubble
 * past every clipping ancestor is not worth having twice (`F-0062`).
 */
export function ColHeader({ label, tip, align = "right", sortKey, activeSort, onSort, style = {} }) {
  const isSorted = sortKey && activeSort === sortKey;

  return (
    <InfoTip
      as="th"
      title={label}
      tip={tip}
      placement="above"
      align={align}
      onClick={onSort ? () => onSort(sortKey) : undefined}
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
    >
      <span style={{ borderBottom: "1px dashed #2A3D50", paddingBottom: 1 }}>
        {label}
      </span>
      {isSorted && <span style={{ marginLeft: 4 }}>↓</span>}
    </InfoTip>
  );
}
