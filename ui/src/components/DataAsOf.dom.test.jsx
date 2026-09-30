// @vitest-environment jsdom
/**
 * `F-0083` — a date is not a freshness statement.
 *
 * Three tabs printed "Data as of 2025-12" / "Dec 2025" while that data was
 * 302 days old, because the TIC source stopped publishing. Every sentence was
 * true; none was informative.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { DataAsOf } from "./DataAsOf";

afterEach(cleanup);

/**
 * A local calendar date N days ago.
 *
 * NOT toISOString().slice(0,10): that is the UTC date, and west of UTC in
 * the evening it is already tomorrow - so a "3 days ago" fixture became a
 * 2-day age and the test failed by the clock rather than by the code. The
 * app treats these as calendar dates (F-0071), and so must the fixture.
 */
function daysAgo(n) {
  const d = new Date();
  d.setDate(d.getDate() - n);
  const pad = (v) => String(v).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}


describe("DataAsOf", () => {
  it("carries the age beside the date", () => {
    render(<DataAsOf asOf="2025-12" source="US Treasury TIC" />);
    expect(screen.getByText(/Data as of/)).toBeTruthy();
    expect(screen.getByText(/days old/)).toBeTruthy();
  });

  it("shows the age of a recent date too", () => {
    render(<DataAsOf asOf={daysAgo(3)} />);
    expect(screen.getByText(/\(3 days old\)/)).toBeTruthy();
  });

  it("says '1 day old', not '1 days old'", () => {
    render(<DataAsOf asOf={daysAgo(1)} />);
    expect(screen.getByText(/\(1 day old\)/)).toBeTruthy();
  });

  it("renders a dash and no age when there is no date", () => {
    const { container } = render(<DataAsOf asOf={null} />);
    expect(container.textContent).toMatch(/—/);
    expect(container.textContent).not.toMatch(/days old/);
  });

  it("names the source when given one", () => {
    render(<DataAsOf asOf="2025-12" source="US Treasury TIC · World Gold Council" />);
    expect(screen.getByText(/World Gold Council/)).toBeTruthy();
  });

  it("passes no judgement on an age it was given no tolerance for", () => {
    // F-0087. This replaces three cases that asserted this component
    // attached a caller-supplied `note` to a date it had decided was stale.
    // The decision was made against a 100-day threshold copied from the
    // pipeline that REFUSES the TIC file, while the watchdog calls TIC
    // stale at 55 — so on a 60-day-old date this footer would have read
    // "fine" directly beneath a DataConfidence strip reading "not current".
    //
    // The ruling moved to DataConfidence, which reads the watchdog's own
    // per-source tolerance. This states the age in neutral ink.
    const { container } = render(<DataAsOf asOf="2025-12" />);
    expect(container.textContent).toMatch(/days old/);
    expect(container.innerHTML).not.toMatch(/rgb\(224, 123, 90\)/);
  });

  it("still colours it when a caller hands it that source's tolerance", () => {
    // The capability is intact — it is the invented default that is gone.
    const { container } = render(<DataAsOf asOf="2025-12" toleranceDays={55} />);
    expect(container.innerHTML).toMatch(/rgb\(224, 123, 90\)/);
  });
});
