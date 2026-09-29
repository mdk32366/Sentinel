import { describe, expect, it } from "vitest";

import { describeCrossAsset } from "./crossAssetNarrative";

const row = (over) => ({
  country_iso: "XXX",
  signal_tier: "T-ONLY",
  tic_mom_pct: -1.2,
  tic_consecutive_months: 1,
  gold_mom_pct: null,
  gold_consecutive_months: 0,
  gold_tonnes: null,
  no_tic_holdings: false,
  spot_gold_rising: false,
  spot_gold_3m_pct: null,
  treseg_signal: "NO_DATA",
  treseg_trend_pct: null,
  multiplier: 1,
  ...over,
});

describe("describeCrossAsset: the headline names the mechanism", () => {
  it("divergence is described as raising cash, not rebalancing", () => {
    // The distinction the whole table exists to draw: selling an asset whose
    // price is rising is a liquidity need, not portfolio management.
    const { headline } = describeCrossAsset(row({
      signal_tier: "DIVERGENCE", spot_gold_rising: true, spot_gold_3m_pct: 12.4,
      gold_mom_pct: -3.1, multiplier: 2,
    }));
    expect(headline).toMatch(/raising cash, not rebalancing/);
    expect(headline).toMatch(/\+12\.4%/);
    expect(headline).toMatch(/2× applied/);
  });

  it("divergence still reads sensibly without a 3M figure", () => {
    const { headline } = describeCrossAsset(row({
      signal_tier: "DIVERGENCE", spot_gold_rising: true, spot_gold_3m_pct: null,
    }));
    expect(headline).toMatch(/rising price/);
    expect(headline).not.toMatch(/NaN|undefined|null/);
  });

  it("an exited country with gold reads as restructuring, not distress alone", () => {
    const { headline } = describeCrossAsset(row({
      signal_tier: "EXITED", no_tic_holdings: true, gold_tonnes: 2332.7,
    }));
    expect(headline).toMatch(/retaining gold/);
  });

  it("an exited country with no gold makes no claim about intent", () => {
    const { headline } = describeCrossAsset(row({
      signal_tier: "EXITED", no_tic_holdings: true, gold_tonnes: null,
    }));
    expect(headline).toBe("Fully out of US Treasuries");
  });

  it("distinguishes sustained Treasury selling from a single month", () => {
    expect(describeCrossAsset(row({ tic_consecutive_months: 5 })).headline)
      .toMatch(/structural, not tactical/);
    expect(describeCrossAsset(row({ tic_consecutive_months: 1 })).headline)
      .toBe("Reducing Treasury holdings");
  });

  it("notes the multiplier only when one applied", () => {
    expect(describeCrossAsset(row({ multiplier: 1 })).headline).not.toMatch(/applied/);
    expect(describeCrossAsset(row({ multiplier: 1.5 })).headline).toMatch(/1.5× applied/);
  });
});

describe("describeCrossAsset: the detail is the evidence", () => {
  it("carries the figures behind the headline", () => {
    const { detail } = describeCrossAsset(row({
      tic_mom_pct: -4.25, tic_consecutive_months: 3,
      gold_mom_pct: -2.5, gold_consecutive_months: 2, gold_tonnes: 510,
    }));
    expect(detail).toMatch(/Treasuries -4\.25% for 3mo/);
    expect(detail).toMatch(/gold -2\.50% for 2mo/);
    expect(detail).toMatch(/510t held/);
  });

  it("omits a consecutive count of one rather than writing 'for 1mo'", () => {
    const { detail } = describeCrossAsset(row({ tic_mom_pct: -1.2, tic_consecutive_months: 1 }));
    expect(detail).toMatch(/Treasuries -1\.20%/);
    expect(detail).not.toMatch(/1mo/);
  });

  it("reports rising non-dollar reserves, which is the de-dollarisation tell", () => {
    const { detail } = describeCrossAsset(row({
      treseg_signal: "REBUILDING", treseg_trend_pct: 8.3,
    }));
    expect(detail).toMatch(/non-\$ reserves \+8\.3% YoY/);
  });

  it("does not claim selling when a figure is positive", () => {
    // Buying is not evidence for a stress table and must not be listed as if
    // it were.
    const { detail } = describeCrossAsset(row({ tic_mom_pct: 2.0, gold_mom_pct: 1.0 }));
    expect(detail).not.toMatch(/Treasuries \+/);
    expect(detail).not.toMatch(/gold \+/);
  });

  it("says 'holds zero US Treasuries' instead of a percentage when exited", () => {
    const { detail } = describeCrossAsset(row({ no_tic_holdings: true, tic_mom_pct: -100 }));
    expect(detail).toMatch(/holds zero US Treasuries/);
    expect(detail).not.toMatch(/-100/);
  });
});

describe("describeCrossAsset: it never renders junk", () => {
  it("survives a missing row", () => {
    expect(describeCrossAsset(null)).toEqual({ headline: "", detail: "" });
    expect(describeCrossAsset(undefined)).toEqual({ headline: "", detail: "" });
  });

  it("survives a row with nothing but an iso", () => {
    const out = describeCrossAsset({ country_iso: "XXX" });
    expect(out.headline).toBeTruthy();
    expect(out.detail).toBe("");
  });

  it("never emits NaN, undefined or null in either field", () => {
    const cases = [
      row({}),
      row({ signal_tier: "DIVERGENCE" }),
      row({ signal_tier: "CROSS-ASSET", gold_mom_pct: null }),
      row({ signal_tier: "EXITED", no_tic_holdings: true }),
      row({ signal_tier: "AU-ONLY", gold_mom_pct: -1 }),
      row({ tic_mom_pct: null, gold_mom_pct: null, gold_tonnes: null }),
    ];
    for (const c of cases) {
      const { headline, detail } = describeCrossAsset(c);
      expect(`${headline} ${detail}`, JSON.stringify(c.signal_tier)).not.toMatch(/NaN|undefined|null/);
    }
  });
});
