// @vitest-environment jsdom
/**
 * `D-0074` — the surface says whether its own data can be trusted.
 *
 * The watchdog has always produced a per-source verdict and `/api/freshness`
 * has always served it. Nothing consumed it: the machinery was right and the
 * screen was silent.
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DataConfidence } from "./DataConfidence";
import { worstStatus } from "../lib/freshness";
import { TRESEG_CODES } from "../lib/constants";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

/** The real shape, with the real production values as of 2026-09-29. */
const SOURCES = [
  // D-0077: the server now sends the period and its coverage end. The stored
  // date labels the period; the age is measured from when that period ended.
  { key: "tic", label: "TIC Treasury holdings", status: "critical",
    latest_date: "2025-12-01", coverage_end: "2025-12-31", period: "month",
    age_days: 273, max_age_days: 85,
    note: "Release date drifts within the month." },
  { key: "money_supply", label: "Broad money growth", status: "stale",
    latest_date: "2025-01-01", age_days: 637, max_age_days: 420,
    note: "MANUAL JSON. Feeds composite dimension 3." },
  { key: "cds", label: "Sovereign CDS spreads", status: "ok",
    latest_date: "2026-09-29", age_days: 1, max_age_days: 4, note: "WGB board." },
  { key: "reserves_ex_gold", label: "Total reserves ex-gold", status: "ok",
    latest_date: "2026-08-01", age_days: 60, max_age_days: 100,
    // Imported, not spelled. constants.test.js forbids a second copy of a
    // FRED code anywhere in the tree and was right to fail this file: a
    // fixture that hardcodes the code is a copy that will not be updated
    // with the others.
    laggard: { code: TRESEG_CODES.RUS, date: "2025-11-01", age_days: 333 },
    note: "Feeds dimension 6." },
];

function stub(sources = SOURCES) {
  vi.stubGlobal("fetch", vi.fn(() => Promise.resolve({
    ok: true, status: 200, statusText: "OK",
    json: () => Promise.resolve({ sources }),
  })));
}

describe("worstStatus", () => {
  it("reports the worst, not the most common", () => {
    // Three green and one critical is a critical panel. An average would
    // report it as mostly fine, which is the opposite of the point.
    expect(worstStatus(SOURCES)).toBe("critical");
  });

  it("ranks stale above ok and critical above stale", () => {
    expect(worstStatus([{ status: "ok" }, { status: "stale" }])).toBe("stale");
    expect(worstStatus([{ status: "stale" }, { status: "critical" }])).toBe("critical");
  });

  it("is ok for an empty or all-ok set", () => {
    expect(worstStatus([])).toBe("ok");
    expect(worstStatus([{ status: "ok" }, { status: "ok" }])).toBe("ok");
  });
});

describe("DataConfidence", () => {
  it("summarises how many of THIS tab's sources are not current", async () => {
    stub();
    render(<DataConfidence sourceKeys={["tic", "cds"]} />);
    await waitFor(() => expect(screen.getByText(/1 of 2 source is not current/)).toBeTruthy());
  });

  it("says all current when they are", async () => {
    stub();
    render(<DataConfidence sourceKeys={["cds"]} />);
    await waitFor(() => expect(screen.getByText(/all 1 sources current/)).toBeTruthy());
  });

  it("only reports the sources the tab declared", async () => {
    // A tab must not be reddened by a source it does not draw on.
    stub();
    render(<DataConfidence sourceKeys={["cds"]} />);
    await waitFor(() => expect(screen.getByText(/all 1 sources current/)).toBeTruthy());
    expect(screen.queryByText(/not current/)).toBeNull();
  });

  it("shows each source's date, age and tolerance on demand", async () => {
    stub();
    render(<DataConfidence sourceKeys={["tic"]} />);
    await waitFor(() => expect(screen.getByText(/detail/)).toBeTruthy());
    fireEvent.click(screen.getByText(/detail/));

    expect(screen.getByText("TIC Treasury holdings")).toBeTruthy();
    // The COVERAGE END, not the period label. Showing "2025-12-01" beside an
    // age measured from 2025-12-31 is how a reader concludes the two disagree,
    // which is F-0087 one layer up.
    expect(screen.getByText("2025-12-31")).toBeTruthy();
    expect(screen.queryByText("2025-12-01")).toBeNull();
    expect(screen.getByText(/273d since period end, tolerance 85d/)).toBeTruthy();
  });

  it("surfaces a laggard hidden inside an otherwise current source", async () => {
    // reserves_ex_gold is "ok" at 60 days and contains a 333-day-old series.
    // An aggregate that hides that is the thing this component exists to
    // stop.
    stub();
    render(<DataConfidence sourceKeys={["reserves_ex_gold"]} />);
    fireEvent.click(await screen.findByText(/detail/));
    expect(screen.getByText(new RegExp(`${TRESEG_CODES.RUS} is 333d`))).toBeTruthy();
  });

  it("renders nothing before the report arrives rather than claiming health", async () => {
    // An empty strip is honest; a green one would not be.
    vi.stubGlobal("fetch", vi.fn(() => new Promise(() => {})));
    const { container } = render(<DataConfidence sourceKeys={["tic"]} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders nothing when the declared source is not in the report", async () => {
    stub();
    const { container } = render(<DataConfidence sourceKeys={["no_such_source"]} />);
    await waitFor(() => expect(container.firstChild).toBeNull());
  });

  it("reads the tolerance from the report rather than holding one", async () => {
    // F-0087: there were three different numbers for how stale TIC may be —
    // 100 in the pipeline that refuses the file, 55 in the watchdog, and 100
    // again in a frontend constant I had added. Asserted behaviourally with
    // a value nobody would hardcode: if the component carried its own
    // number, this fails.
    stub([{
      key: "tic", label: "TIC Treasury holdings", status: "critical",
      latest_date: "2025-12-01", age_days: 303, max_age_days: 37, note: "x",
    }]);
    render(<DataConfidence sourceKeys={["tic"]} />);
    fireEvent.click(await screen.findByText(/detail/));
    expect(screen.getByText(/tolerance 37d/)).toBeTruthy();
  });
});
