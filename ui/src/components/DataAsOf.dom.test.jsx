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

describe("DataAsOf", () => {
  it("carries the age beside the date", () => {
    render(<DataAsOf asOf="2025-12" source="US Treasury TIC" note="the source has not published since then" />);
    expect(screen.getByText(/Data as of/)).toBeTruthy();
    expect(screen.getByText(/days old/)).toBeTruthy();
  });

  it("says what being stale MEANS, not just that it is", () => {
    // The component knows the age; only the tab knows the consequence.
    render(<DataAsOf asOf="2025-12" note="Treasury scores are computed from it" />);
    expect(screen.getByText(/Treasury scores are computed from it/)).toBeTruthy();
  });

  it("stays quiet about an ordinary lag", () => {
    // TIC is normally one to two months behind. Flagging that would train
    // the reader to ignore the flag.
    const recent = new Date();
    recent.setDate(recent.getDate() - 40);
    const asOf = recent.toISOString().slice(0, 7);

    render(<DataAsOf asOf={asOf} note="the source has not published since then" />);
    expect(screen.queryByText(/has not published/)).toBeNull();
  });

  it("shows an age even when it is not stale", () => {
    const recent = new Date();
    recent.setDate(recent.getDate() - 3);
    render(<DataAsOf asOf={recent.toISOString().slice(0, 10)} />);
    expect(screen.getByText(/\(3d\)/)).toBeTruthy();
  });

  it("renders a dash and no age when there is no date", () => {
    const { container } = render(<DataAsOf asOf={null} note="whatever" />);
    expect(container.textContent).toMatch(/—/);
    expect(container.textContent).not.toMatch(/days old|whatever/);
  });

  it("names the source when given one", () => {
    render(<DataAsOf asOf="2025-12" source="US Treasury TIC · World Gold Council" />);
    expect(screen.getByText(/World Gold Council/)).toBeTruthy();
  });

  it("does not attach a note to a date that is fine", () => {
    const recent = new Date();
    recent.setDate(recent.getDate() - 5);
    const { container } = render(
      <DataAsOf asOf={recent.toISOString().slice(0, 10)} note="the source has stopped" />,
    );
    expect(container.textContent).not.toMatch(/the source has stopped/);
  });
});
