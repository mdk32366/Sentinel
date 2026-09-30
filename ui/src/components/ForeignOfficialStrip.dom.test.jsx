// @vitest-environment jsdom
/**
 * `D-0080` — what central banks are doing, and the two things it must not say.
 *
 * "Of Which: Foreign Official" is a SUBSET of Grand Total spanning every holder,
 * named and unnamed. It is not part of All Other and never additive with it.
 * Like All Other it describes a group, so attributing its move to a named
 * sovereign would be `F-0097` — the defect that cost 1,050 points across 32
 * countries.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { ForeignOfficialStrip } from "./ForeignOfficialStrip";

afterEach(cleanup);

/** The real production figures for 2026-07. */
const SIGNAL = {
  as_of: "2026-07-01",
  level_bn: 3773.1,
  share_pct: 40.8,
  private_bn: 5475.0,
  private_share_pct: 59.2,
  mom_pct: -0.13,
  three_month_pct: -3.37,
  twelve_month_pct: -2.92,
  share_move_12m_points: -1.86,
  falls_of_last_12: 9,
  bills_bn: 354.4,
  bonds_bn: 3418.8,
  bills_share_of_official_pct: 9.39,
  bills_share_move_12m_points: -1.16,
  components_reconcile: true,
  // D-0088: 79 months from Table 3, not the 13 Table 5 carries.
  points: 79,
  sustained: false,
  unusual: false,
  share_move_percentile: 84,
  median_move_12m_points: -3.23,
  trend: {
    from: "2020-01-01", from_share_pct: 59.34, to_share_pct: 40.8,
    share_change_pp: -18.54, level_change_pct: -9.51, months: 79,
  },
  note:
    "US Treasuries held by foreign official institutions — central banks and " +
    "sovereign funds — across every holder, named and unnamed. A subset of the " +
    "Grand Total, not a part of All Other and never added to it. Like All Other " +
    "it describes a group, not any one country.",
};

describe("ForeignOfficialStrip", () => {
  it("renders nothing before the series has been imported", () => {
    const { container } = render(<ForeignOfficialStrip signal={null} />);
    expect(container.firstChild).toBeNull();
  });

  it("shows the official and private sides", () => {
    render(<ForeignOfficialStrip signal={SIGNAL} />);
    expect(screen.getByText("$3.77T")).toBeTruthy();
    expect(screen.getByText("40.80%")).toBeTruthy();
    expect(screen.getByText("$5.48T")).toBeTruthy();
  });

  it("shows the twelve-month decline and the share move", () => {
    render(<ForeignOfficialStrip signal={SIGNAL} />);
    expect(screen.getByText("-2.92%")).toBeTruthy();
    expect(screen.getByText("-1.86pp")).toBeTruthy();
  });

  it("shows the duration mix", () => {
    // Bills as a share of official is a posture: shortening duration is a
    // classic pre-stress move, and it is only visible because Table 5
    // decomposes the headline.
    render(<ForeignOfficialStrip signal={SIGNAL} />);
    expect(screen.getByText("9.39%")).toBeTruthy();
  });

  it("states that it is not about any one country", () => {
    render(<ForeignOfficialStrip signal={SIGNAL} />);
    expect(screen.getByText(/not any one country/)).toBeTruthy();
  });

  it("states that it is not part of All Other", () => {
    // The one arithmetic error a reader could make with two aggregates on one
    // screen is adding them. Official spans every holder; All Other spans the
    // unnamed ones. They overlap.
    render(<ForeignOfficialStrip signal={SIGNAL} />);
    expect(screen.getByText(/never added to it/)).toBeTruthy();
  });

  it("names no country", () => {
    const { container } = render(<ForeignOfficialStrip signal={SIGNAL} />);
    for (const iso of ["China", "CHN", "Japan", "JPN", "Germany", "Russia"]) {
      expect(container.textContent).not.toContain(iso);
    }
  });

  it("reports the structural trend rather than a 12-month flag", () => {
    // D-0088. The original rule flagged a "sustained decline" on 9 falls in 12.
    // Against the 79 months Table 3 carries, 9 falls is the MEDIAN window and
    // that rule fired on 70% of windows — decoration (D-0024). The finding is
    // the six-year drift, which no 12-month window can show.
    render(<ForeignOfficialStrip signal={SIGNAL} />);
    expect(screen.getByText(/59\.34% → 40\.80%/)).toBeTruthy();
    expect(screen.getByText(/-18\.54pp over 79 months/)).toBeTruthy();
  });

  it("says where the last twelve months sit in that history", () => {
    // The context that turned the flag from a finding into decoration: the
    // current window is at the 84th percentile, i.e. milder than most.
    render(<ForeignOfficialStrip signal={SIGNAL} />);
    expect(screen.getByText(/84th percentile/)).toBeTruthy();
    expect(screen.getByText(/not unusual within it/)).toBeTruthy();
  });

  it("speaks up only when the window is in the steepest tenth", () => {
    render(<ForeignOfficialStrip signal={{ ...SIGNAL, unusual: true, share_move_12m_points: -5.8 }} />);
    expect(screen.getByText(/steepest tenth/)).toBeTruthy();
    expect(screen.getByText(/accelerating/)).toBeTruthy();
  });

  it("says the private share rose by construction, not as a claim about buyers", () => {
    // private = Grand Total - official, so the complement is arithmetic. Saying
    // "private buyers stepped in" would assert a behaviour nobody observed.
    render(<ForeignOfficialStrip signal={SIGNAL} />);
    expect(screen.getByText(/by construction/)).toBeTruthy();
  });

  it("renders without a trend when the series is too short to have one", () => {
    // A fresh database has Table 5's 13 months before Table 3 has run.
    const thin = { ...SIGNAL, trend: undefined };
    const { container } = render(<ForeignOfficialStrip signal={thin} />);
    expect(container.textContent).not.toMatch(/undefined|NaN/);
    expect(screen.queryByText(/Since 2020/)).toBeNull();
  });

  it("reports an ordinary window as ordinary, with the percentile", () => {
    // D-0088. This test used to assert the absence of "fallen in", a string the
    // component stopped producing when `sustained` was retired - it passed
    // because nothing could make it fail (D-0024). It now exercises the rule
    // that is actually live: -1.86pp is the 84th percentile, not an alarm.
    const calm = { ...SIGNAL, unusual: false, share_move_12m_points: -1.86,
      share_move_percentile: 84 };
    render(<ForeignOfficialStrip signal={calm} />);
    expect(screen.queryByText(/steepest tenth/)).toBeNull();
    expect(screen.getByText(/84th percentile/)).toBeTruthy();
    expect(screen.getByText(/not unusual within it/)).toBeTruthy();
  });

  it("shouts when bills and bonds do not reconcile", () => {
    // Every figure on the strip depends on the parse. A component mismatch
    // means the source layout changed, and that is louder than the signal.
    render(<ForeignOfficialStrip signal={{ ...SIGNAL, components_reconcile: false }} />);
    expect(screen.getByText(/do not sum to the official total/)).toBeTruthy();
    expect(screen.getByText(/unverified/)).toBeTruthy();
  });

  it("stays silent about reconciliation when it holds", () => {
    render(<ForeignOfficialStrip signal={SIGNAL} />);
    expect(screen.queryByText(/do not sum/)).toBeNull();
  });

  it("survives a partial signal rather than printing undefined", () => {
    const thin = {
      as_of: "2026-07-01", level_bn: 3773.1, share_pct: null, private_bn: null,
      twelve_month_pct: null, share_move_12m_points: null,
      bills_share_of_official_pct: null, components_reconcile: null,
      sustained: false, note: "x",
    };
    const { container } = render(<ForeignOfficialStrip signal={thin} />);
    expect(container.textContent).not.toMatch(/undefined|NaN/);
  });
});
